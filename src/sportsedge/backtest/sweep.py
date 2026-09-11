"""Parameter sweeps, committed so their numbers can be reproduced.

Run 1 swept 102 configurations and reported a best NFL log-loss of 0.6459. The
script was never committed, so when run 3 re-ran the sweep to recompute the ROI
column that run 2's chronology fix had withdrawn, the two could not be
reconciled: the same nominal config scored 0.6412 here, and the best scored
0.6396. Neither number is provably wrong, which is the problem.

A project whose central discipline is "no model change goes live without a
backtest, and the backtest goes in the journal even if it's bad" cannot have
its headline backtest live in a scratch file. The protocol below is therefore
explicit about every choice that moves a number.

Protocol
--------
* Ratings walk forward chronologically over all seasons, sorted on a NUMERIC
  week (the string-sorted column is what scrambled every pre-2026-09-10 NFL
  result; see backtest/engine.py).
* Metrics and bets are recorded only for `test_seasons`; earlier seasons are
  burn-in, so ratings are warm before anything is scored.
* Optional logistic calibration maps elo_diff -> P(home) and is refit before
  each test season on every completed game strictly earlier than it. Never on
  the season being scored.
* The baseline to beat is the de-vigged closing moneyline, never a previous
  version of the model.
* ROI is flat $1 per flagged side and is always returned with its 95%
  interval. A bare ROI number is not a result.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

from sportsedge.backtest.metrics import log_loss, brier_score, simulate_flat_stake_roi
from sportsedge.betting.edge import devig_two_way, edge_fraction
from sportsedge.models.elo import NflEloModel
from sportsedge.storage import snapshots

DEFAULT_TEST_SEASONS = (2021, 2022, 2023, 2024)
DEFAULT_SEASONS = (2018, 2019, 2020, 2021, 2022, 2023, 2024)


@dataclass(frozen=True)
class NflConfig:
    k: float
    home_advantage: float
    use_mov: bool
    calibrate: bool
    season_regression: float = 0.33


def _chronological(games: pd.DataFrame, seasons) -> pd.DataFrame:
    sub = games[games["season"].astype(str).isin({str(s) for s in seasons})].copy()
    sub = sub.assign(_w=pd.to_numeric(sub["week"], errors="coerce"))
    sub = sub.sort_values(["season", "_w", "game_date"]).drop(columns=["_w"])
    return sub.dropna(subset=["home_score", "away_score"]).reset_index(drop=True)


def run_nfl_config(games: pd.DataFrame, cfg: NflConfig, *, test_seasons=DEFAULT_TEST_SEASONS,
                   edge_threshold: float = 0.03) -> dict:
    """One configuration, walk-forward, scored only on `test_seasons`."""
    test = {str(s) for s in test_seasons}
    model = NflEloModel(k=cfg.k, home_advantage=cfg.home_advantage,
                        use_mov_multiplier=cfg.use_mov)

    hist_diff, hist_y = [], []
    clf, fitted_for = None, None
    y_true, p_pred, bets = [], [], []
    mk_y, mk_p = [], []
    prev_season = None

    for _, g in games.iterrows():
        season = str(g["season"])
        if prev_season is not None and season != prev_season:
            model.book.regress_to_mean(cfg.season_regression)
        prev_season = season

        diff = ((model.book.get(g["home_team"]) + cfg.home_advantage)
                - model.book.get(g["away_team"]))
        p_home = model.win_prob_home(g["home_team"], g["away_team"])

        if cfg.calibrate and season in test:
            if fitted_for != season:
                y = np.asarray(hist_y)
                clf = (LogisticRegression().fit(np.asarray(hist_diff).reshape(-1, 1), y)
                       if len(set(y.tolist())) > 1 else None)
                fitted_for = season
            if clf is not None:
                p_home = float(clf.predict_proba([[diff]])[0][1])

        home_won = 1 if g["result"] == "H" else 0
        if season in test:
            y_true.append(home_won)
            p_pred.append(p_home)
            ho, ao = g.get("home_odds_decimal"), g.get("away_odds_decimal")
            if pd.notna(ho) and pd.notna(ao):
                fair_home, _ = devig_two_way(1 / ho, 1 / ao)
                mk_y.append(home_won)
                mk_p.append(fair_home)
                for prob, odds, won, fair in (
                    (p_home, ho, g["result"] == "H", fair_home),
                    (1 - p_home, ao, g["result"] == "A", 1 - fair_home),
                ):
                    e = edge_fraction(prob, odds)
                    if e >= edge_threshold:
                        bets.append({"model_prob": prob, "decimal_odds": odds, "won": won,
                                     "fair_market_prob": fair, "edge_frac": e})

        hist_diff.append(diff)
        hist_y.append(home_won)
        model.update(g["home_team"], g["away_team"], g["home_score"], g["away_score"])

    roi = simulate_flat_stake_roi(bets)
    ci = roi["roi_ci95_pct"] or (None, None)
    return {
        **asdict(cfg),
        "n_games": len(y_true),
        "log_loss": log_loss(y_true, p_pred),
        "brier": brier_score(y_true, p_pred),
        "n_bets": roi["n_bets"],
        "roi_pct": roi["roi_pct"],
        "roi_ci_lo": ci[0],
        "roi_ci_hi": ci[1],
        "roi_t": roi["roi_t_stat"],
        "roi_significant": roi["significant_at_95"],
        "market_log_loss": log_loss(mk_y, mk_p),
        "market_brier": brier_score(mk_y, mk_p),
    }


def sweep_nfl(*, seasons=DEFAULT_SEASONS, test_seasons=DEFAULT_TEST_SEASONS,
              ks=(12, 20, 28, 36), home_advantages=(25, 40, 55),
              edge_threshold: float = 0.03, games: pd.DataFrame | None = None) -> pd.DataFrame:
    """The full NFL grid, sorted best-log-loss first."""
    if games is None:
        games = snapshots.read_processed("nfl_games")
    ordered = _chronological(games, seasons)

    rows = [
        run_nfl_config(ordered, NflConfig(k, ha, mov, cal),
                       test_seasons=test_seasons, edge_threshold=edge_threshold)
        for k in ks for ha in home_advantages
        for mov in (False, True) for cal in (False, True)
    ]
    return pd.DataFrame(rows).sort_values("log_loss").reset_index(drop=True)


def summarize_sweep(df: pd.DataFrame) -> dict:
    """The only three questions the deployment gate actually asks."""
    market = df["market_log_loss"].iloc[0]
    return {
        "n_configs": len(df),
        "market_log_loss": market,
        "beat_market_on_log_loss": int((df["log_loss"] < market).sum()),
        "positive_roi": int((df["roi_pct"] > 0).sum()),
        "significantly_positive_roi": int(((df["roi_pct"] > 0) & df["roi_significant"]).sum()),
        "best_log_loss": df["log_loss"].min(),
        "roi_range_pct": (df["roi_pct"].min(), df["roi_pct"].max()),
        # Positive means the better-calibrated configs LOSE more, which is the
        # standing argument for gating on log-loss rather than on ROI.
        "corr_log_loss_roi": df["log_loss"].corr(df["roi_pct"]),
    }
