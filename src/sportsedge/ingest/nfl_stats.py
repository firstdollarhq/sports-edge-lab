"""Free NFL schedules + closing betting lines via nflverse (nfl_data_py)."""
from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import nfl_data_py as nfl
import pandas as pd

from sportsedge.betting.edge import american_to_decimal

# nflverse publishes `gametime` as a wall clock in US Eastern, not UTC.
_NFLVERSE_TZ = ZoneInfo("America/New_York")


def _kickoff_utc(gameday: pd.Series, gametime: pd.Series) -> pd.Series:
    """True kickoff in UTC, from nflverse's Eastern-local date + time.

    This is the ONLY trustworthy kickoff in the project. Kalshi's market
    payload has no kickoff field at all: `expected_expiration_time` and
    `occurrence_datetime` are identical to each other and land 3-6 hours
    AFTER the ball is snapped (measured across all 31 events on the
    2026-09-10 board: 27 at +3h, 4 at +6h, none at +0h). Anything that
    needs "before the game started" has to come here, not there.
    """
    naive = pd.to_datetime(
        gameday.astype(str) + " " + gametime.astype(str), errors="coerce")
    return (naive.dt.tz_localize(_NFLVERSE_TZ, ambiguous=True, nonexistent="shift_forward")
                 .dt.tz_convert(timezone.utc))


def _neutral_site(location: pd.Series) -> pd.Series:
    """nflverse `location` is 'Home' for a normal game and 'Neutral' otherwise.

    Elo applies a flat home advantage to the nominal home team on every game,
    including London/Munich/Super Bowl games where nobody is home. That is a
    real ranking error the schedule discloses in advance, which is exactly the
    kind of thing run 11's AUC bound says is worth testing.
    """
    return (location.astype(str).str.strip().str.lower() != "home").astype(int)


def fetch_nfl_games(seasons: list[int]) -> pd.DataFrame:
    """Returns one row per game with result + closing moneyline/spread/total,
    for completed games only (rows with no score are future/unplayed).

    Also carries the pre-kickoff CONTEXT columns nflverse ships and this ingest
    discarded until run 12: rest days, divisional flag, neutral site, roof,
    surface, weather, and the starting QB ids. None of these feed Elo -- Elo
    sees team identity and nothing else -- they exist so that
    `models.features` can test whether information the rating engine cannot
    see improves the ORDER games are ranked in. See backtest/discrimination.py
    for why ranking is the only thing left worth testing.

    Provenance note, because two of these are not equally trustworthy:
      * rest / div_game / location / roof / surface are SCHEDULE facts, known
        weeks ahead. No lookahead risk at all.
      * temp / wind are the conditions nflverse RECORDS for the game, i.e.
        roughly what happened, where a model pricing at T-8h would only have a
        forecast. Usable, but optimistic; `features.py` tiers them separately
        and the journal reports the tiers apart.
      * qb ids are the QBs who actually STARTED. Inactives post ~90 minutes
        before kickoff, so this is close to knowable, but it is not knowable
        at the time this project actually prices a game. Same treatment.
    """
    df = nfl.import_schedules(seasons)
    now = datetime.now(timezone.utc).isoformat()

    out = pd.DataFrame({
        "game_id": df["game_id"],
        "sport": "nfl",
        "league": "NFL",
        "season": df["season"].astype(str),
        # Nullable int, NOT str. The backtest sorts on this column to
        # establish chronology; as a string, "10" sorts before "2" and the
        # season is processed 1, 10, 11 ... 18, 19, 2, 20 -- i.e. the model
        # predicts week 2 using ratings that already absorbed weeks 10-18.
        "week": df["week"].astype("Int64"),
        "game_date": df["gameday"],
        # Real kickoff, used as the cutoff for every closing-price lookup.
        "kickoff_utc": _kickoff_utc(df["gameday"], df["gametime"]).apply(
            lambda t: None if pd.isna(t) else t.isoformat()),
        "home_team": df["home_team"],
        "away_team": df["away_team"],
        "home_score": df["home_score"],
        "away_score": df["away_score"],
        "home_odds_decimal": df["home_moneyline"].apply(lambda x: american_to_decimal(x) if pd.notna(x) else None),
        "away_odds_decimal": df["away_moneyline"].apply(lambda x: american_to_decimal(x) if pd.notna(x) else None),
        "draw_odds_decimal": None,
        "spread_line": df["spread_line"],
        "total_line": df["total_line"],
        # --- pre-kickoff context (never read by Elo; see docstring) ---
        "home_rest": df["home_rest"].astype("Int64"),
        "away_rest": df["away_rest"].astype("Int64"),
        "div_game": df["div_game"].astype("Int64"),
        "neutral_site": _neutral_site(df["location"]),
        "roof": df["roof"],
        "surface": df["surface"],
        "temp": df["temp"],
        "wind": df["wind"],
        "home_qb_id": df["home_qb_id"],
        "away_qb_id": df["away_qb_id"],
        "source": "nflverse",
        "ingested_at": now,
    })
    out["result"] = out.apply(
        lambda r: None if pd.isna(r["home_score"]) else (
            "H" if r["home_score"] > r["away_score"] else ("A" if r["home_score"] < r["away_score"] else "D")
        ),
        axis=1,
    )
    return out
