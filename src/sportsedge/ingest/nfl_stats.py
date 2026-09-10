"""Free NFL schedules + closing betting lines via nflverse (nfl_data_py)."""
from __future__ import annotations

from datetime import datetime, timezone

import nfl_data_py as nfl
import pandas as pd

from sportsedge.betting.edge import american_to_decimal


def fetch_nfl_games(seasons: list[int]) -> pd.DataFrame:
    """Returns one row per game with result + closing moneyline/spread/total,
    for completed games only (rows with no score are future/unplayed)."""
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
        "home_team": df["home_team"],
        "away_team": df["away_team"],
        "home_score": df["home_score"],
        "away_score": df["away_score"],
        "home_odds_decimal": df["home_moneyline"].apply(lambda x: american_to_decimal(x) if pd.notna(x) else None),
        "away_odds_decimal": df["away_moneyline"].apply(lambda x: american_to_decimal(x) if pd.notna(x) else None),
        "draw_odds_decimal": None,
        "spread_line": df["spread_line"],
        "total_line": df["total_line"],
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
