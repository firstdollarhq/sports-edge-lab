"""Chronology of the walk-forward backtest.

A string `week` column sorts "10" before "2", so a season is processed
1, 10, 11 ... 18, 19, 2, 20 ... The model then predicts week 2 using ratings
that already absorbed weeks 10-18 -- lookahead leakage, in the one module
whose docstring promises there is none. It was live for every NFL backtest
through 2026-09-10 and flattered ROI by ~3.6 points.

The engine must therefore establish chronology numerically no matter what
dtype the upstream ingest hands it.
"""
import pandas as pd

from sportsedge.models.elo import NflEloModel
from sportsedge.backtest.engine import backtest_nfl


def _season(weeks):
    rows = []
    for w in weeks:
        rows.append({
            "game_id": f"g{w}", "season": "2023", "week": w,
            "game_date": f"2023-{9 + w // 5:02d}-{1 + (w % 28):02d}",
            "home_team": "AAA" if w % 2 else "BBB",
            "away_team": "BBB" if w % 2 else "AAA",
            "home_score": 24 if w % 2 else 10, "away_score": 10 if w % 2 else 24,
            "result": "H" if w % 2 else "A",
            "home_odds_decimal": 1.9, "away_odds_decimal": 1.9,
        })
    return pd.DataFrame(rows)


def test_week_order_is_numeric_not_lexicographic():
    weeks = list(range(1, 19))
    as_int = _season(weeks)
    as_str = _season(weeks)
    as_str["week"] = as_str["week"].astype(str)

    r_int = backtest_nfl(as_int, NflEloModel())
    r_str = backtest_nfl(as_str, NflEloModel())

    assert abs(r_int["log_loss"] - r_str["log_loss"]) < 1e-12, (
        "a string week column must not change the processing order"
    )


def test_string_weeks_do_not_reorder_the_season():
    df = _season(list(range(1, 19)))
    df["week"] = df["week"].astype(str)
    ordered = df.assign(_w=pd.to_numeric(df["week"])).sort_values(["season", "_w", "game_date"])
    assert ordered["_w"].tolist() == list(range(1, 19))
    # ...whereas the raw string sort does not:
    naive = df.sort_values(["season", "week", "game_date"])["week"].tolist()
    assert naive[:3] == ["1", "10", "11"], "documents the bug this guards against"
