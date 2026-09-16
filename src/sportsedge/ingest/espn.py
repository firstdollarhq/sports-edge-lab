"""Free schedules + results for both leagues via ESPN's public scoreboard API.

Why this module exists
----------------------
Three items sat blocked across runs 6, 7 and 8 on the same external event --
football-data.co.uk publishing the 2026-09-12 EPL fixtures:

  * the project's first and only result cohort (7 EPL wagers) was settled from
    Kalshi alone, with no independent cross-check;
  * `backfill_clv` could fill nothing, because CLV needs a kickoff and
    `ingest.kickoff` reads kickoffs out of the committed stats table;
  * the EPL expiration lag stayed an *assumed* 3h.

football-data.co.uk publishes in batches, on its own cadence, days after the
matches. It is the right source for what it is uniquely good at -- historical
closing odds, which is what the model trains against -- and the wrong thing to
block settlement verification on. So this is a second, independent source for
the two fields that were actually missing: **kickoff time and final score.**

What this source is, and is not
-------------------------------
ESPN is a SCHEDULE AND RESULTS source here. It carries no odds, it never feeds
the model's training data, and nothing derived from it enters a price. It is
consumed in exactly two places:

  * `verify-settlements`, as a third opinion against Kalshi's own resolution;
  * `ingest.kickoff`, as a *fallback* when the primary table has no kickoff for
    a fixture -- which is the CLV blocker above.

Free, unauthenticated, no account. `site.api.espn.com` is the undocumented
endpoint behind espn.com's own scoreboard and needs no key. Undocumented means
it can change without notice, which is exactly why it is a cross-check and a
fallback rather than a primary: if it disappears, verification gets louder and
nothing that was already correct becomes wrong.

That is not hypothetical any more -- see `_months_covering` below. Run 13
found the `YYYYMMDD-YYYYMMDD` range form this module was built on returning
HTTP 400 for every range, with single-day requests still fine. The fetch now
walks whole months instead.

Per CLAUDE.md the bar for a new source is "free, no human-created account, and
verified against something we already hold before any number derived from it
is published". `cli espn-audit` is that verification, and it is a command
rather than a one-off script so the agreement can be re-measured every run.

The trap this module exists to avoid
------------------------------------
A SCHEDULED ESPN event reports `score: "0"` for both sides, not null. Reading
the score without checking `status.type.completed` records every future game
as a 0-0 draw -- which for EPL is a *plausible* scoreline, so it would settle
bets, feed the audit, and never look wrong. Scores are therefore taken ONLY
from events ESPN marks completed, and a non-completed event contributes a
schedule row with null scores.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests

SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/{path}/scoreboard"

# ESPN's league path per sport we cover.
_LEAGUE_PATH = {
    "nfl": "football/nfl",
    "soccer": "soccer/eng.1",
}

_LEAGUE_NAME = {"nfl": "NFL", "soccer": "EPL"}

# --- ESPN abbreviation -> this project's canonical team naming ---------------
# Canonical naming is the stats source each sport already uses: nflverse
# abbreviations for NFL, football-data.co.uk names for EPL (see ingest.teams).
#
# NFL: ESPN matches nflverse except for two clubs.
ESPN_NFL_TO_NFLVERSE = {
    "LAR": "LA",
    "WSH": "WAS",
}

# EPL: written out in full rather than derived, because ESPN's abbreviations
# are NOT Kalshi's and two pairs are a coin-flip if guessed.
#   ESPN MAN = Manchester UNITED, MNC = Manchester CITY
#        (Kalshi uses MUN / MCI, i.e. the letters do not line up)
#   ESPN CHE / LIV vs Kalshi CFC / LFC
# Getting either backwards inverts a result silently, so tests/test_espn.py
# pins both pairs.
ESPN_EPL_TO_FOOTBALL_DATA = {
    "ARS": "Arsenal",
    "AVL": "Aston Villa",
    "BHA": "Brighton",
    "BOU": "Bournemouth",
    "BRE": "Brentford",
    "CHE": "Chelsea",
    "COV": "Coventry",
    "CRY": "Crystal Palace",
    "EVE": "Everton",
    "FUL": "Fulham",
    "HUL": "Hull",
    "IPS": "Ipswich",
    "LEE": "Leeds",
    "LIV": "Liverpool",
    "MAN": "Man United",
    "MNC": "Man City",
    "NEW": "Newcastle",
    "NFO": "Nott'm Forest",
    "SUN": "Sunderland",
    "TOT": "Tottenham",
}


class EspnTeamUnknown(ValueError):
    """An ESPN abbreviation we have no canonical mapping for.

    Loud, not skipped, for the same reason `teams.TeamResolutionError` is: a
    new abbreviation means promotion, relocation or an upstream rename, and
    quietly dropping the fixture would make a *missing* game look like an
    agreeing one in the audit.
    """


def canonical_team(sport: str, abbr: str) -> str:
    if sport == "nfl":
        from sportsedge.ingest.teams import NFLVERSE_TEAMS
        team = ESPN_NFL_TO_NFLVERSE.get(abbr, abbr)
        if team not in NFLVERSE_TEAMS:
            raise EspnTeamUnknown(f"Unknown ESPN NFL abbreviation: {abbr!r}")
        return team
    if sport == "soccer":
        try:
            return ESPN_EPL_TO_FOOTBALL_DATA[abbr]
        except KeyError:
            raise EspnTeamUnknown(
                f"Unknown ESPN EPL abbreviation: {abbr!r} "
                "(promoted club? add it to ESPN_EPL_TO_FOOTBALL_DATA)"
            ) from None
    raise ValueError(f"Unsupported sport: {sport!r}")


_SEASON_SLUG_RE = re.compile(r"^(\d{4}-\d{2})")

# ESPN's NFL `season.type`: 1 preseason, 2 regular, 3 postseason, 4 all-star.
# Only 2 and 3 are kept. Two reasons, and the second is the dangerous one:
#
#   * nflverse's table contains no preseason, so every preseason game would be
#     permanently "only in ESPN" -- 49 rows of noise in an audit whose entire
#     job is to make a real one-game gap visible.
#   * **preseason restarts the week numbering.** An August game is week 1..4
#     exactly like September's. This project has already shipped one bug from
#     `week` not meaning what the surrounding code assumed (run 2, sorted as a
#     string, which invalidated every NFL ROI number). Committing a table
#     where `week` silently means two different things is that bug's next
#     draft.
#
# Applied to NFL only. `eng.1` returns league fixtures and its `season.type`
# is a league-specific id (14308), not this pre/regular/post scheme -- so
# filtering soccer on these numbers would drop everything.
_NFL_SEASON_TYPES_KEPT = {2, 3}


def _season_label(sport: str, event: dict) -> str | None:
    """Season label in the SAME vocabulary the primary table already uses.

    Taken from ESPN's own payload rather than inferred from the date, because
    inferring it means picking a cutover month and being wrong about fixtures
    either side of it.

    - soccer: `season.slug` is '2026-27-english-premier-league'; its prefix is
      exactly football-data.co.uk's '2026-27'.
    - nfl: `season.year` is 2026, which is nflverse's season integer as a str.

    Matters because `storage.write_processed` sorts on `season`, and a column
    that disagreed with the primary table's vocabulary would make the two
    tables silently un-joinable on the one key a reader would try first.
    """
    season = event.get("season") or {}
    if sport == "soccer":
        m = _SEASON_SLUG_RE.match(str(season.get("slug") or ""))
        if m:
            return m.group(1)
        year = season.get("year")
        return None if year is None else f"{year}-{str(int(year) + 1)[2:]}"
    year = season.get("year")
    return None if year is None else str(int(year))


def _date_param(start: str, end: str | None) -> str:
    """'2026-09-12' -> '20260912'; a range when `end` is given.

    RETAINED BUT NO LONGER USED FOR FETCHING. ESPN rejects the range form it
    builds (see `_months_covering`). Kept because it is the exact string that
    stopped working, and a future run wondering whether the range is back can
    call it rather than reconstructing the format from this comment.
    """
    a = start.replace("-", "")
    if end is None:
        return a
    return f"{a}-{end.replace('-', '')}"


def _months_covering(start: str, end: str) -> list[str]:
    """Every 'YYYYMM' month touched by the inclusive window [start, end].

    WHY MONTHS, AND NOT THE RANGE THIS MODULE WAS WRITTEN AGAINST.
    On 2026-09-16 `refresh-history` began warning for both sports:

        400 Client Error: Bad Request ... dates=20260801-20261007

    The body reads `{"code":400,"message":"Failed to get events endpoint."}`.
    Measured rather than guessed, because "undocumented endpoint returned 400"
    has several plausible causes and they imply different fixes:

      * every range fails, down to a ten-day one, on both sports -- so it is
        the range SYNTAX, not the window width and not a rate limit;
      * `dates=20260914` (single day) returns 200;
      * `dates=202609` (month) returns 200;
      * `dates=2026` (year) returns 200;
      * `dates=20260914,20260915` (comma list) returns 400.

    So the day-range form is simply gone. Both survivors could work. Months
    win on request count: the default window is ~67 days, which is 3 requests
    by month against 67 by day, and this runs twice per refresh.

    The risk in fetching coarser than you filter is that the coarse call
    silently returns less -- a `limit` truncation would look exactly like a
    quiet league. So month-vs-day equivalence was CHECKED, not assumed, over
    2026-09 for both sports: 48 NFL events and 30 EPL events by month, the
    same 48 and 30 by union of thirty day-requests, zero ids in one and not
    the other. `test_months_covering_*` pins the arithmetic here; the network
    equivalence is recorded in run 13's journal entry, since a test cannot
    assert it without hitting ESPN.
    """
    lo = datetime.strptime(start, "%Y-%m-%d")
    hi = datetime.strptime(end, "%Y-%m-%d")
    if hi < lo:
        raise ValueError(f"end {end!r} precedes start {start!r}")
    months, y, m = [], lo.year, lo.month
    while (y, m) <= (hi.year, hi.month):
        months.append(f"{y}{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return months


def fetch_espn_scoreboard(sport: str, dates: str,
                          *, session: requests.Session | None = None,
                          timeout: int = 30) -> dict:
    """Raw scoreboard payload for one `dates` value ('YYYYMMDD' or 'YYYYMM')."""
    if sport not in _LEAGUE_PATH:
        raise ValueError(f"Unsupported sport: {sport!r}")
    get = (session or requests).get
    resp = get(
        SCOREBOARD_URL.format(path=_LEAGUE_PATH[sport]),
        params={"dates": dates, "limit": 400},
        timeout=timeout,
        headers={"Accept": "application/json"},
    )
    resp.raise_for_status()
    return resp.json()


def parse_scoreboard(sport: str, payload: dict) -> pd.DataFrame:
    """Normalise an ESPN payload into the project's game-table schema.

    Scores are populated only for events ESPN marks completed; everything else
    is a schedule row with null scores. See the module docstring -- a scheduled
    ESPN event reports 0-0 rather than null, and 0-0 is a real EPL scoreline.
    """
    now = datetime.now(timezone.utc).isoformat()
    rows = []

    for event in payload.get("events", []):
        comps = event.get("competitions") or []
        if not comps:
            continue
        comp = comps[0]
        sides = {c.get("homeAway"): c for c in comp.get("competitors", [])}
        if "home" not in sides or "away" not in sides:
            continue

        home = canonical_team(sport, sides["home"]["team"]["abbreviation"])
        away = canonical_team(sport, sides["away"]["team"]["abbreviation"])

        kickoff = pd.to_datetime(event.get("date"), utc=True, errors="coerce")
        if pd.isna(kickoff):
            continue

        season_type = (event.get("season") or {}).get("type")
        if sport == "nfl" and season_type not in _NFL_SEASON_TYPES_KEPT:
            continue

        status = ((comp.get("status") or {}).get("type") or {})
        completed = bool(status.get("completed"))

        if completed:
            try:
                hs = int(sides["home"].get("score"))
                as_ = int(sides["away"].get("score"))
            except (TypeError, ValueError):
                hs = as_ = None
        else:
            hs = as_ = None

        if hs is None or as_ is None:
            result = None
        elif hs > as_:
            result = "H"
        elif as_ > hs:
            result = "A"
        else:
            result = "D"

        game_date = kickoff.strftime("%Y-%m-%d")
        rows.append({
            "game_id": f"espn_{sport}_{event.get('id')}",
            "sport": sport,
            "league": _LEAGUE_NAME[sport],
            "season": _season_label(sport, event),
            "season_type": season_type,
            "week": ((event.get("week") or {}).get("number")),
            "game_date": game_date,
            "kickoff_utc": kickoff.isoformat(),
            "home_team": home,
            "away_team": away,
            "home_score": hs,
            "away_score": as_,
            "result": result,
            "completed": completed,
            "status": status.get("name"),
            "source": "espn",
            "ingested_at": now,
        })

    df = pd.DataFrame(rows, columns=[
        "game_id", "sport", "league", "season", "season_type", "week",
        "game_date", "kickoff_utc", "home_team", "away_team", "home_score",
        "away_score", "result", "completed", "status", "source", "ingested_at",
    ])
    # Sort on real timestamps, not their string forms. Run 6 shipped a bug of
    # exactly that shape (`week` sorted as a string); ISO-8601 happens to sort
    # correctly as text, but relying on that is how the next one gets written.
    if not df.empty:
        df = (df.assign(_k=pd.to_datetime(df["kickoff_utc"], utc=True))
                .sort_values(["_k", "home_team"])
                .drop(columns="_k")
                .reset_index(drop=True))
    return df


def fetch_espn_games(sport: str, start: str, end: str | None = None,
                     *, session: requests.Session | None = None,
                     **kwargs) -> pd.DataFrame:
    """Fetch + normalise the inclusive window [start, end] in one call.

    Walks whole months (see `_months_covering`) and trims back to the window,
    so the returned frame is what the old day-range call returned rather than
    whole calendar months.

    Two deliberate choices in that trim:

      * **The window is widened by a day at each end before trimming.** ESPN
        dates an event by US local date; this table's `game_date` is derived
        from the UTC kickoff, and a Sunday-night NFL kickoff is Monday in UTC.
        Trimming hard on the UTC date would drop exactly the late games at
        each boundary. A day of slack cannot drop a fixture the old call
        returned, and the worst it adds is a boundary day of *schedule* rows,
        which the audit ignores because it only compares games both sources
        report as played.
      * **A month that fails is fatal, not skipped.** This module's standing
        rule is that a missing fixture must never be able to look like an
        agreeing one; a silently dropped month would remove games from the
        audit's denominator rather than showing up in it. The CLI already
        catches this and keeps the previously committed table, which is the
        loud-but-safe behaviour we want.
    """
    end = end or start
    own_session = session is None
    session = session or requests.Session()
    try:
        frames = [
            parse_scoreboard(sport, fetch_espn_scoreboard(sport, month,
                                                          session=session, **kwargs))
            for month in _months_covering(start, end)
        ]
    finally:
        if own_session:
            session.close()

    df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if df.empty:
        return df

    # Months overlap nothing, but a fixture rescheduled across a month
    # boundary can appear twice under one id. Keep the first.
    df = df.drop_duplicates(subset="game_id", keep="first")

    lo = (datetime.strptime(start, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
    hi = (datetime.strptime(end, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
    df = df[(df["game_date"] >= lo) & (df["game_date"] <= hi)]

    return (df.assign(_k=pd.to_datetime(df["kickoff_utc"], utc=True))
              .sort_values(["_k", "home_team"])
              .drop(columns="_k")
              .reset_index(drop=True))


# --- Verification against the source we already hold ------------------------

def audit_against_primary(espn: pd.DataFrame, primary: pd.DataFrame,
                          *, tolerance_days: int = 2) -> dict:
    """Compare ESPN's scores and kickoffs to the primary stats table.

    CLAUDE.md's bar for a new source is that it be "verified against something
    we already hold before any number derived from it is published". This is
    that check, and it is deliberately a reusable function rather than a
    throwaway script: agreement measured once, on the day a source is added,
    says nothing about the day upstream renames a team.

    Fixtures are matched on (home_team, away_team) with the kickoff dates
    required to be within `tolerance_days` -- enough to absorb a local-date vs
    UTC-date disagreement on a late kickoff, tight enough not to collide with
    the reverse fixture, which no league schedules inside a week.

    Only games BOTH sources report as played are compared; a game one side has
    not published yet is reported as `only_*`, not as a disagreement.
    """
    out = {
        "compared": 0, "score_agree": 0, "score_disagree": 0,
        "kickoff_compared": 0, "kickoff_agree": 0, "kickoff_disagree": 0,
        "only_espn": 0, "only_primary": 0, "disagreements": [],
    }
    if espn.empty or primary.empty:
        out["only_espn"] = int(len(espn))
        out["only_primary"] = int(len(primary))
        return out

    e = espn.copy()
    e["_k"] = pd.to_datetime(e["kickoff_utc"], utc=True, errors="coerce")
    p = primary.copy()
    p["_k"] = pd.to_datetime(p.get("kickoff_utc"), utc=True, errors="coerce")
    p["_d"] = pd.to_datetime(p["game_date"], utc=True, errors="coerce")
    # Prefer a real kickoff for matching, fall back to the calendar date.
    p["_anchor"] = p["_k"].fillna(p["_d"])

    tol = pd.Timedelta(days=tolerance_days)

    # Restrict the primary table to ESPN's own window before counting anything
    # as "only in primary". The committed tables hold every season ever
    # ingested, so skipping this reports ~2,600 historical fixtures as games
    # ESPN is missing -- a number that is both true and completely useless,
    # and which would bury a real one-game gap.
    lo, hi = e["_k"].min() - tol, e["_k"].max() + tol
    p = p[(p["_anchor"] >= lo) & (p["_anchor"] <= hi)]
    if p.empty:
        out["only_espn"] = int(len(e))
        return out

    matched_primary = set()

    for _, row in e.iterrows():
        cand = p[(p["home_team"] == row["home_team"])
                 & (p["away_team"] == row["away_team"])]
        cand = cand[(cand["_anchor"] - row["_k"]).abs() <= tol]
        if cand.empty:
            out["only_espn"] += 1
            continue
        hit = cand.iloc[0]
        matched_primary.add(hit.name)

        e_played = pd.notna(row["home_score"]) and pd.notna(row["away_score"])
        p_played = pd.notna(hit.get("home_score")) and pd.notna(hit.get("away_score"))
        if not (e_played and p_played):
            continue

        out["compared"] += 1
        same = (int(row["home_score"]) == int(hit["home_score"])
                and int(row["away_score"]) == int(hit["away_score"]))
        if same:
            out["score_agree"] += 1
        else:
            out["score_disagree"] += 1
            out["disagreements"].append({
                "matchup": f"{row['away_team']} @ {row['home_team']}",
                "field": "score",
                "espn": f"{int(row['home_score'])}-{int(row['away_score'])}",
                "primary": f"{int(hit['home_score'])}-{int(hit['away_score'])}",
            })

        if pd.notna(hit["_k"]):
            out["kickoff_compared"] += 1
            delta = abs((hit["_k"] - row["_k"]).total_seconds())
            if delta <= 60:
                out["kickoff_agree"] += 1
            else:
                out["kickoff_disagree"] += 1
                out["disagreements"].append({
                    "matchup": f"{row['away_team']} @ {row['home_team']}",
                    "field": "kickoff",
                    "espn": row["_k"].isoformat(),
                    "primary": hit["_k"].isoformat(),
                    "delta_minutes": round(delta / 60, 1),
                })

    played_primary = p[p["home_score"].notna()] if "home_score" in p else p
    out["only_primary"] = int(sum(1 for i in played_primary.index
                                  if i not in matched_primary))
    return out
