"""What to do when a free upstream stats source is down.

WHY THIS EXISTS. On 2026-09-17 football-data.co.uk -- the EPL results and
closing-odds source, and the only one this project has for that league --
started answering every request with a redirect to `http://127.0.0.1/`. That
is an upstream misconfiguration, not a rate limit and not something a key
would fix, and it took two things down with it:

  * `refresh-history` raised in the middle of its EPL step, so the ESPN
    cross-check tables and the SQLite cache after it were never rebuilt. One
    dead source stopped the refresh of three live ones.
  * `recommend --sports soccer` raised before pricing anything, because
    `_load_games_for` fetched the rating seasons live on every invocation even
    though a committed table of exactly those seasons sits in
    `data/processed/`.

The committed table is the obvious fallback and it is also the dangerous one.
Pricing today's board off a table that is missing last night's results is how
a model quietly prices a league it no longer knows the state of -- and it
would look, in the output, exactly like a normal run. So the fallback here is
allowed but never silent, and it is gated on an *independent* source rather
than on a timestamp:

    a committed table is usable if and only if it is missing no game that
    ESPN reports as already played.

ESPN is already in this repo as the settlement cross-check, its agreement with
both primary sources is measured every run by `espn-audit`, and it carries no
odds -- so it cannot be the thing that decides a price, only the thing that
says whether the table we are about to price from has fallen behind reality.
`only_espn` from `espn.audit_against_primary` is that count, already written
and already tested.

A staleness check against the table's own `ingested_at` would have passed
here: the table was 15 hours old and complete, because no EPL fixture falls
between 09-14 and 09-19. Age is not the question. Missing games are.
"""
from __future__ import annotations

import pandas as pd

from sportsedge.ingest import espn
from sportsedge.storage import snapshots

# The committed table and the ESPN cross-check table, per sport key used
# throughout the CLI ("nfl", "soccer").
PRIMARY_TABLE = {"nfl": "nfl_games", "soccer": "epl_games"}
ESPN_TABLE = {"nfl": "espn_nfl_games", "soccer": "espn_epl_games"}


def _last_changed_at(df: pd.DataFrame) -> str | None:
    """Max `ingested_at` -- when a row last CHANGED, not when we last looked.

    `snapshots.write_processed` runs every merge through `_keep_unchanged_rows`,
    which holds back rows whose content is identical so the git diff stays
    readable. A row that was re-fetched today and came back the same keeps its
    old `ingested_at`. So this column reads 2026-09-15 on a table refreshed at
    06:08 on 2026-09-17, and anything that treated it as a fetch time would
    call a perfectly current table two days stale.

    It is reported because it is genuinely informative -- it dates the last
    real change -- and it is named for what it is. It is emphatically NOT what
    decides `usable`; see the module docstring.
    """
    if "ingested_at" not in df.columns or df.empty:
        return None
    vals = df["ingested_at"].dropna()
    return None if vals.empty else str(vals.max())


def _missing_played_games(sport: str, games: pd.DataFrame) -> dict:
    """How many games ESPN reports played that `games` does not have at all.

    Returns the gap count plus enough context to tell "the table is complete"
    apart from "there was nothing to check it against", which are very
    different licences to price on it.
    """
    try:
        ref = snapshots.read_processed(ESPN_TABLE[sport])
    except (FileNotFoundError, KeyError):
        return {"checked": False, "reason": "no committed ESPN table",
                "missing_played": None, "espn_played": None}

    played = ref.dropna(subset=["home_score", "away_score"])
    if played.empty:
        return {"checked": False, "reason": "ESPN table has no played games",
                "missing_played": None, "espn_played": 0}

    audit = espn.audit_against_primary(played, games)
    return {"checked": True, "reason": None,
            "missing_played": int(audit["only_espn"]),
            "espn_played": int(len(played)),
            "espn_table_last_changed_at": _last_changed_at(ref)}


def _supplement_from_espn(sport: str, games: pd.DataFrame,
                          wanted) -> tuple[pd.DataFrame, dict]:
    """Fill a results gap in the committed table with ESPN's played games.

    WHY. The gate above refuses to price a league whose committed table is
    behind reality. That is the right refusal when there is nothing to be done
    about it, but from 2026-09-19 it would have silenced EPL pricing entirely
    on a table that is missing only SCORES -- and scores are the one thing the
    live rating path actually consumes. `models/live.build_soccer_model` reads
    season, game_date, home_team, away_team, home_score, away_score, result.
    Not one odds column. ESPN carries every one of those fields, has agreed
    with the primary source on 40/40 EPL and 16/16 NFL games this run, and is
    already trusted to decide settlement (`cli._verification_games` fills the
    same kind of gap the same way).

    WHAT THIS COSTS, stated plainly because it is a real weakening. Before
    this, ESPN was an INDEPENDENT check on a table built by someone else: it
    could only ever say "you are behind", never supply the number. For rows
    added here it is both the filler and the checker, so `usable` after a
    supplement means "the table agrees with ESPN", which is trivially true of
    rows that came from ESPN. The check retains its force for the primary
    table's own rows and loses it for these. Two things keep that honest:

      * `freshness` (the gap BEFORE) is kept next to `freshness_after_supplement`,
        so the provenance shows what was filled rather than a clean zero, and
        `describe()` prints the supplemented count in the run log.
      * A supplemented row is tagged `source='espn'` and carries NaN in every
        odds column, so anything that prices or backtests from odds drops it
        rather than reading a blank as a number.

    WHAT IT MUST NOT REACH. Backtests train on closing odds and go through
    `cli._load_games`, which reads the committed table directly and never
    calls this module -- so odds-free rows cannot enter a backtest sample.
    That separation is the whole reason the supplement is in-memory and this
    function never writes to `data/processed/`. Pinned by
    `test_supplement_does_not_reach_backtest_loader`.
    """
    info = {"available": False, "rows": 0, "games": [], "no_odds": True}
    try:
        ref = snapshots.read_processed(ESPN_TABLE[sport])
    except (FileNotFoundError, KeyError):
        return games, info

    info["available"] = True
    ref = ref[ref["season"].astype(str).isin(wanted)]
    extra = espn.unmatched_played(ref, games)
    if extra.empty:
        return games, info

    # A team name this table has never seen is a naming mismatch, not a new
    # fixture, and importing it is worse than importing nothing: Elo would
    # open a SECOND entity for that club at the default rating, leave the real
    # one to go stale, and price both as if nothing had happened. That is this
    # project's recurring failure -- a value that is not what the surrounding
    # code assumed -- and it is exactly what an upstream rename of
    # "Nott'm Forest" would produce, the day it happened, with no other
    # symptom. Such rows are left out, which leaves the residual gap standing,
    # which takes the league dark loudly. A club whose very first appearance
    # is on ESPN alone is refused by the same rule; the cost of being wrong
    # there is one dark league, against a corrupted rating book.
    known = set(games["home_team"]).union(games["away_team"])
    unknown = sorted({t for t in set(extra["home_team"]).union(extra["away_team"])
                      if t not in known})
    if unknown:
        info["unknown_teams"] = unknown
        extra = extra[extra["home_team"].isin(known) & extra["away_team"].isin(known)]
        if extra.empty:
            return games, info

    # Reindex onto the primary table's columns: every column ESPN does not
    # carry -- which is every odds column -- becomes NaN rather than absent,
    # so the concat cannot silently reshape the frame.
    aligned = extra.reindex(columns=games.columns)
    aligned["source"] = "espn"

    info["rows"] = int(len(aligned))
    info["games"] = [f"{r['away_team']} @ {r['home_team']} {str(r['game_date'])[:10]}"
                     for _, r in aligned.iterrows()]
    return pd.concat([games, aligned], ignore_index=True), info


def load_games(sport: str, seasons, label_fn, fetch, *fetch_args) -> tuple[pd.DataFrame, dict]:
    """Rating-season games for `sport`, live if possible, committed if not.

    Always returns a frame filtered to `seasons` and a provenance dict. The
    caller decides what to do with `usable`; this function never decides for
    it, because "price anyway" and "skip this league" are different calls in
    `recommend` and in `verify-settlements` and both are legitimate.

    `usable` is False only when the fallback is demonstrably behind reality.
    An upstream that is merely down, with a complete committed table behind
    it, is a degraded run -- not a stopped one.
    """
    wanted = label_fn(seasons)
    prov: dict = {"sport": sport, "source": "upstream", "error": None,
                  "usable": True, "degraded": False}
    try:
        games = fetch(*fetch_args)
    except Exception as exc:  # noqa: BLE001 -- any upstream failure, incl. HTTP
        prov.update(source="committed_table", degraded=True,
                    error=f"{type(exc).__name__}: {exc}")
        try:
            games = snapshots.read_processed(PRIMARY_TABLE[sport])
        except (FileNotFoundError, KeyError) as read_exc:
            prov.update(usable=False,
                        fallback_error=f"{type(read_exc).__name__}: {read_exc}")
            return pd.DataFrame(), prov

    filtered = games[games["season"].astype(str).isin(wanted)]
    prov["rows"] = int(len(filtered))
    prov["played"] = int(filtered["home_score"].notna().sum()) if len(filtered) else 0
    prov["table_last_changed_at"] = _last_changed_at(filtered)
    missing = {s for s in wanted} - set(filtered["season"].astype(str))
    prov["missing_seasons"] = sorted(missing)

    if prov["degraded"]:
        gap = _missing_played_games(sport, filtered)
        prov["freshness"] = gap
        # An unchecked table is not a verified table. Refuse to price on a
        # fallback nothing independent has confirmed, rather than treating
        # "could not check" as "fine".
        prov["usable"] = bool(gap["checked"]) and gap["missing_played"] == 0

        if gap["checked"] and gap["missing_played"]:
            filtered, supp = _supplement_from_espn(sport, filtered, wanted)
            prov["espn_supplement"] = supp
            after = _missing_played_games(sport, filtered)
            prov["freshness_after_supplement"] = after
            prov["rows"] = int(len(filtered))
            prov["played"] = int(filtered["home_score"].notna().sum())
            prov["usable"] = bool(after["checked"]) and after["missing_played"] == 0

        if filtered.empty:
            prov["usable"] = False

    return filtered, prov


def describe(prov: dict) -> str:
    """One line for a human reading the run log."""
    if not prov.get("degraded"):
        return f"{prov['sport']}: upstream live ({prov.get('rows', 0)} rows)"
    gap = prov.get("freshness") or {}
    state = "USABLE" if prov.get("usable") else "NOT USABLE"
    detail = (f"ESPN gap {gap.get('missing_played')} of {gap.get('espn_played')} played"
              if gap.get("checked") else f"unverified ({gap.get('reason')})")
    # A supplemented run must never read like a run that needed no supplement:
    # the gap it reports was closed with rows from the checker itself.
    supp = prov.get("espn_supplement") or {}
    if supp.get("rows"):
        after = prov.get("freshness_after_supplement") or {}
        detail += (f", {supp['rows']} filled from ESPN (no odds), "
                   f"residual gap {after.get('missing_played')}")
    return (f"{prov['sport']}: upstream DOWN ({prov.get('error')}); "
            f"committed table {state}, {prov.get('rows', 0)} rows, {detail}")
