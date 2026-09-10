"""Walk-forward backtests: ratings are only ever updated using games that have
already been predicted, so there is no lookahead leakage. Games are processed
in chronological order within each season; ratings partially regress to the
mean between seasons (standard Elo practice).

PRICING: these two backtests run against SPORTSBOOK odds (nflverse
moneylines, football-data.co.uk bookmaker averages). A sportsbook quote is
already the price you get -- the vig is baked into it -- so there is no
mid-vs-ask adjustment to make here. The mid-vs-ask problem is specific to
the exchange (Kalshi), where a two-sided book tempts you to price off the
mid; see backtest.kalshi_engine for that venue."""
from __future__ import annotations

import pandas as pd

from sportsedge.betting.edge import devig_two_way, devig_three_way, edge_fraction
from sportsedge.models.elo import NflEloModel
from sportsedge.models.calibration import SoccerOutcomeCalibrator
from sportsedge.models.elo import SoccerEloModel
from sportsedge.backtest.metrics import log_loss, brier_score, simulate_flat_stake_roi


def backtest_nfl(games: pd.DataFrame, model: NflEloModel, edge_threshold: float = 0.03,
                  season_regression: float = 0.33) -> dict:
    # Sort on a numeric week, never the raw column. A string "10" sorts before
    # "2", which silently scrambles the within-season order and lets ratings
    # from late in the season inform predictions made early in it. This was
    # live for every NFL backtest through 2026-09-10 and flattered ROI by ~3.6
    # points (-4.65% reported vs -8.21% actual, 2018-2024).
    games = games.assign(_week_num=pd.to_numeric(games["week"], errors="coerce"))
    games = games.sort_values(["season", "_week_num", "game_date"]).drop(columns=["_week_num"])
    games = games.reset_index(drop=True)
    games = games.dropna(subset=["home_score", "away_score"])

    y_true, p_pred, bets = [], [], []
    prev_season = None

    for _, g in games.iterrows():
        if prev_season is not None and g["season"] != prev_season:
            model.book.regress_to_mean(season_regression)
        prev_season = g["season"]

        p_home = model.win_prob_home(g["home_team"], g["away_team"])
        actual_home = 1 if g["result"] == "H" else 0
        y_true.append(actual_home)
        p_pred.append(p_home)

        if pd.notna(g.get("home_odds_decimal")) and pd.notna(g.get("away_odds_decimal")):
            imp_home = 1 / g["home_odds_decimal"]
            imp_away = 1 / g["away_odds_decimal"]
            fair_home, _ = devig_two_way(imp_home, imp_away)
            model_edge = edge_fraction(p_home, g["home_odds_decimal"])
            if model_edge >= edge_threshold:
                bets.append({"model_prob": p_home, "decimal_odds": g["home_odds_decimal"],
                              "won": g["result"] == "H", "fair_market_prob": fair_home,
                              "edge_frac": model_edge, "game_id": g["game_id"]})
            away_edge = edge_fraction(1 - p_home, g["away_odds_decimal"])
            if away_edge >= edge_threshold:
                bets.append({"model_prob": 1 - p_home, "decimal_odds": g["away_odds_decimal"],
                              "won": g["result"] == "A", "fair_market_prob": 1 - fair_home,
                              "edge_frac": away_edge, "game_id": g["game_id"]})

        model.update(g["home_team"], g["away_team"], g["home_score"], g["away_score"])

    return {
        "n_games": len(games),
        "log_loss": log_loss(y_true, p_pred),
        "brier_score": brier_score(y_true, p_pred),
        "roi": simulate_flat_stake_roi(bets),
        "bets": bets,
    }


def backtest_soccer(games: pd.DataFrame, model: SoccerEloModel, edge_threshold: float = 0.03) -> dict:
    """Splits by season: fits the outcome calibrator on all seasons except the
    last, then evaluates walk-forward on the final season only (true
    out-of-sample test), while Elo ratings themselves update game-by-game
    across the whole history."""
    games = games.sort_values(["season", "game_date"]).reset_index(drop=True)
    games = games.dropna(subset=["home_score", "away_score"])
    seasons = sorted(games["season"].unique())
    if len(seasons) < 2:
        raise ValueError("Need at least 2 seasons: one to calibrate, one to test")
    test_season = seasons[-1]
    calib_seasons = seasons[:-1]

    calib_diffs, calib_outcomes = [], []
    for _, g in games[games["season"].isin(calib_seasons)].iterrows():
        calib_diffs.append(model.elo_diff(g["home_team"], g["away_team"]))
        calib_outcomes.append(g["result"])
        model.update(g["home_team"], g["away_team"], g["home_score"], g["away_score"])

    calibrator = SoccerOutcomeCalibrator()
    calibrator.fit(calib_diffs, calib_outcomes)

    y_true_h, p_pred_h, bets = [], [], []
    for _, g in games[games["season"] == test_season].iterrows():
        diff = model.elo_diff(g["home_team"], g["away_team"])
        probs = calibrator.predict_proba(diff)
        p_h, p_d, p_a = probs.get("H", 0), probs.get("D", 0), probs.get("A", 0)

        y_true_h.append(1 if g["result"] == "H" else 0)
        p_pred_h.append(p_h)

        odds = {
            "H": (p_h, g.get("home_odds_decimal"), g["result"] == "H"),
            "D": (p_d, g.get("draw_odds_decimal"), g["result"] == "D"),
            "A": (p_a, g.get("away_odds_decimal"), g["result"] == "A"),
        }
        if all(pd.notna(v[1]) for v in odds.values()):
            imp = {k: 1 / v[1] for k, v in odds.items()}
            fair_h, fair_d, fair_a = devig_three_way(imp["H"], imp["D"], imp["A"])
            fair = {"H": fair_h, "D": fair_d, "A": fair_a}
            for outcome, (p_model, dec_odds, won) in odds.items():
                e = edge_fraction(p_model, dec_odds)
                if e >= edge_threshold:
                    bets.append({"model_prob": p_model, "decimal_odds": dec_odds, "won": won,
                                  "fair_market_prob": fair[outcome], "edge_frac": e,
                                  "game_id": g["game_id"], "selection": outcome})

        model.update(g["home_team"], g["away_team"], g["home_score"], g["away_score"])

    return {
        "test_season": test_season,
        "calib_seasons": calib_seasons,
        "n_games": len(games[games["season"] == test_season]),
        "log_loss": log_loss(y_true_h, p_pred_h),
        "brier_score": brier_score(y_true_h, p_pred_h),
        "roi": simulate_flat_stake_roi(bets),
        "bets": bets,
    }
