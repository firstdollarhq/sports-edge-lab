"""Build current-strength models from all completed history.

The backtester deliberately walks forward and throws its ratings away. To price
*today's* games we need the opposite: consume every completed game up to now and
keep the resulting ratings. The update rule is identical to the backtest's, so a
model priced here is the same model that was measured there -- if these two ever
diverge, backtest numbers stop describing live behaviour.
"""
from __future__ import annotations

import pandas as pd

from sportsedge.models.calibration import SoccerOutcomeCalibrator
from sportsedge.models.elo import NflEloModel, SoccerEloModel

NFL_MODEL_VERSION = "nfl-elo-v1"
SOCCER_MODEL_VERSION = "epl-elo-logit-v1"


def build_nfl_model(games: pd.DataFrame, *, use_mov: bool = False,
                    season_regression: float = 0.33) -> NflEloModel:
    """Run Elo through every completed game, chronologically, and keep ratings."""
    model = NflEloModel(use_mov_multiplier=use_mov)
    played = games.dropna(subset=["home_score", "away_score"])
    # Numeric week, matching backtest.engine exactly. Sorting the raw column
    # puts "10" before "2" when the ingest hands over strings, which builds
    # today's ratings from a scrambled season -- and silently breaks the
    # promise in this module's docstring that the live model is the same model
    # the backtest measured.
    played = played.assign(_week_num=pd.to_numeric(played["week"], errors="coerce"))
    played = played.sort_values(["season", "_week_num", "game_date"]).drop(columns=["_week_num"])

    prev_season = None
    for _, g in played.iterrows():
        if prev_season is not None and g["season"] != prev_season:
            model.book.regress_to_mean(season_regression)
        prev_season = g["season"]
        model.update(g["home_team"], g["away_team"], g["home_score"], g["away_score"])
    return model


def build_soccer_model(games: pd.DataFrame) -> tuple[SoccerEloModel, SoccerOutcomeCalibrator]:
    """Elo ratings through all completed games + an outcome calibrator.

    The calibrator is fit on (elo_diff -> outcome) pairs collected *as the
    ratings were at the time*, which keeps it consistent with how the backtest
    fits it. Ratings continue updating through the whole history.
    """
    model = SoccerEloModel()
    played = games.dropna(subset=["home_score", "away_score"]).sort_values(["season", "game_date"])

    diffs, outcomes = [], []
    for _, g in played.iterrows():
        diffs.append(model.elo_diff(g["home_team"], g["away_team"]))
        outcomes.append(g["result"])
        model.update(g["home_team"], g["away_team"], g["home_score"], g["away_score"])

    if len(set(outcomes)) < 3:
        raise ValueError("Need H/D/A all present to fit the outcome calibrator")

    calibrator = SoccerOutcomeCalibrator()
    calibrator.fit(diffs, outcomes)
    return model, calibrator
