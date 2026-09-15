"""Walk-forward backtests: ratings are only ever updated using games that have
already been predicted, so there is no lookahead leakage. Games are processed
in chronological order within each season; ratings partially regress to the
mean between seasons (standard Elo practice).

PRICING: by default these two backtests run against SPORTSBOOK odds (nflverse
moneylines, football-data.co.uk bookmaker averages). A sportsbook quote is
already the price you get -- the vig is baked into it -- so there is no
mid-vs-ask adjustment to make here. The mid-vs-ask problem is specific to
the exchange (Kalshi), where a two-sided book tempts you to price off the
mid; see backtest.kalshi_engine for that venue.

Both venues run through THIS loop, via the `pricer` argument. That is
deliberate: the alternative was a second copy of the walk-forward loop, and
this file's own history is a catalogue of what a subtly divergent copy costs
(the week-ordering bug lived in the backtest and the live model separately and
had to be fixed twice). A pricer maps the de-vigged fair probability and the
raw book quote to the decimal odds actually available at that venue;
`SportsbookPricer` returns the book quote unchanged, so the default path is
byte-identical to the pre-pricer behaviour and `test_pricer_default_matches_book`
pins that."""
from __future__ import annotations

from typing import Protocol

import pandas as pd

from sportsedge.betting.edge import devig_two_way, devig_three_way, edge_fraction
from sportsedge.models.elo import NflEloModel
from sportsedge.models.calibration import SoccerOutcomeCalibrator
from sportsedge.models.elo import SoccerEloModel
from sportsedge.backtest.metrics import log_loss, brier_score, simulate_flat_stake_roi


class Pricer(Protocol):
    """Maps a market fair probability to the decimal odds a venue will give you.

    `fair_prob` is the de-vigged market probability for the side in question;
    `book_decimal_odds` is the raw sportsbook quote. Return None when the side
    is not tradeable at this venue (e.g. a synthesised exchange price that
    lands outside (0, 1)), and the bet rule will skip it.
    """

    def decimal_odds(self, fair_prob: float, book_decimal_odds: float) -> float | None: ...


class SportsbookPricer:
    """You get the book's quote, vig included. The historical default."""

    name = "sportsbook"

    def decimal_odds(self, fair_prob: float, book_decimal_odds: float) -> float | None:
        return book_decimal_odds


def backtest_nfl(games: pd.DataFrame, model: NflEloModel, edge_threshold: float = 0.03,
                  season_regression: float = 0.33, pricer: Pricer | None = None,
                  context_model=None) -> dict:
    """`context_model` is optional and purely observational: when supplied it
    rides THIS loop (see the module docstring on why there is only one), sees
    the same walk-forward Elo diff, and writes a `p_context` alongside
    `p_model` in `predictions`. It never influences Elo, the bet rule, or any
    returned metric, so the baseline path is unchanged -- `test_features.py`
    pins that the canonical numbers reproduce with a context model attached."""
    # Sort on a numeric week, never the raw column. A string "10" sorts before
    # "2", which silently scrambles the within-season order and lets ratings
    # from late in the season inform predictions made early in it. This was
    # live for every NFL backtest through 2026-09-10 and flattered ROI by ~3.6
    # points (-4.65% reported vs -8.21% actual, 2018-2024).
    pricer = pricer or SportsbookPricer()
    games = games.assign(_week_num=pd.to_numeric(games["week"], errors="coerce"))
    games = games.sort_values(["season", "_week_num", "game_date"]).drop(columns=["_week_num"])
    games = games.reset_index(drop=True)
    games = games.dropna(subset=["home_score", "away_score"])

    y_true, p_pred, bets, predictions = [], [], [], []
    prev_season = None

    for _, g in games.iterrows():
        if prev_season is not None and g["season"] != prev_season:
            model.book.regress_to_mean(season_regression)
            # Refit the context model on completed seasons only. Placed on the
            # season boundary, before this season's first prediction, so the
            # coefficients pricing a game are never fit on that game.
            if context_model is not None:
                context_model.start_season()
        prev_season = g["season"]

        p_home = model.win_prob_home(g["home_team"], g["away_team"])
        actual_home = 1 if g["result"] == "H" else 0
        y_true.append(actual_home)
        p_pred.append(p_home)
        # Every priced game, bet or not. `bets` is a selected sample by
        # construction, so it cannot answer whether the model ranks games as
        # well as the market does; this can. See backtest.discrimination.
        # `season` rides along because a per-season refit is only a monotone
        # transform WITHIN a season; pooled across seasons it can reorder, and
        # separating those two effects needs the label. See backtest.context.
        predictions.append({"game_id": g["game_id"], "y": actual_home,
                            "season": str(g["season"]), "p_model": p_home,
                            "p_market": None})

        # Elo's own view of the matchup, home advantage included, taken BEFORE
        # this game updates the book. Including the advantage is deliberate: it
        # is what lets `neutral_site` express "no, nobody is home here" rather
        # than the context fit having to rediscover home field from scratch.
        elo_diff = None
        if context_model is not None:
            elo_diff = (model.book.get(g["home_team"]) + model.home_advantage
                        - model.book.get(g["away_team"]))
            predictions[-1]["p_context"] = context_model.predict(g, elo_diff)

        if pd.notna(g.get("home_odds_decimal")) and pd.notna(g.get("away_odds_decimal")):
            imp_home = 1 / g["home_odds_decimal"]
            imp_away = 1 / g["away_odds_decimal"]
            fair_home, fair_away = devig_two_way(imp_home, imp_away)
            predictions[-1]["p_market"] = fair_home

            odds_home = pricer.decimal_odds(fair_home, g["home_odds_decimal"])
            if odds_home is not None:
                model_edge = edge_fraction(p_home, odds_home)
                if model_edge >= edge_threshold:
                    bets.append({"model_prob": p_home, "decimal_odds": odds_home,
                                  "won": g["result"] == "H", "fair_market_prob": fair_home,
                                  "edge_frac": model_edge, "game_id": g["game_id"]})

            odds_away = pricer.decimal_odds(fair_away, g["away_odds_decimal"])
            if odds_away is not None:
                away_edge = edge_fraction(1 - p_home, odds_away)
                if away_edge >= edge_threshold:
                    bets.append({"model_prob": 1 - p_home, "decimal_odds": odds_away,
                                  "won": g["result"] == "A", "fair_market_prob": fair_away,
                                  "edge_frac": away_edge, "game_id": g["game_id"]})

        # Observed only after the game has been predicted and scored, so the
        # training set is always strictly in this game's past.
        if context_model is not None:
            context_model.observe(g, elo_diff, actual_home)

        model.update(g["home_team"], g["away_team"], g["home_score"], g["away_score"])

    return {
        "n_games": len(games),
        "log_loss": log_loss(y_true, p_pred),
        "brier_score": brier_score(y_true, p_pred),
        "roi": simulate_flat_stake_roi(bets),
        "bets": bets,
        "predictions": predictions,
    }


def backtest_soccer(games: pd.DataFrame, model: SoccerEloModel, edge_threshold: float = 0.03,
                    pricer: Pricer | None = None) -> dict:
    """Splits by season: fits the outcome calibrator on all seasons except the
    last, then evaluates walk-forward on the final season only (true
    out-of-sample test), while Elo ratings themselves update game-by-game
    across the whole history."""
    pricer = pricer or SportsbookPricer()
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

    y_true_h, p_pred_h, bets, predictions = [], [], [], []
    for _, g in games[games["season"] == test_season].iterrows():
        diff = model.elo_diff(g["home_team"], g["away_team"])
        probs = calibrator.predict_proba(diff)
        p_h, p_d, p_a = probs.get("H", 0), probs.get("D", 0), probs.get("A", 0)

        y_true_h.append(1 if g["result"] == "H" else 0)
        p_pred_h.append(p_h)
        # Home-win only: it is the one outcome both the model and a de-vigged
        # 1X2 market price directly, so it is the only apples-to-apples ranking
        # comparison available on this leg.
        predictions.append({"game_id": g["game_id"], "y": 1 if g["result"] == "H" else 0,
                            "p_model": p_h, "p_market": None})

        odds = {
            "H": (p_h, g.get("home_odds_decimal"), g["result"] == "H"),
            "D": (p_d, g.get("draw_odds_decimal"), g["result"] == "D"),
            "A": (p_a, g.get("away_odds_decimal"), g["result"] == "A"),
        }
        if all(pd.notna(v[1]) for v in odds.values()):
            imp = {k: 1 / v[1] for k, v in odds.items()}
            fair_h, fair_d, fair_a = devig_three_way(imp["H"], imp["D"], imp["A"])
            fair = {"H": fair_h, "D": fair_d, "A": fair_a}
            predictions[-1]["p_market"] = fair_h
            for outcome, (p_model, dec_odds, won) in odds.items():
                traded_odds = pricer.decimal_odds(fair[outcome], dec_odds)
                if traded_odds is None:
                    continue
                e = edge_fraction(p_model, traded_odds)
                if e >= edge_threshold:
                    bets.append({"model_prob": p_model, "decimal_odds": traded_odds, "won": won,
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
        "predictions": predictions,
    }
