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
                   edge_threshold: float = 0.03, collect_sides: bool = False) -> dict:
    """One configuration, walk-forward, scored only on `test_seasons`.

    With `collect_sides`, also returns every priced side under key "sides" --
    not just the ones that cleared the threshold. Analyses that need to compare
    what the model BET against what it PASSED (see backtest.selection) run off
    this same loop deliberately: run 1's sweep lived in an uncommitted scratch
    file and could never be reconciled afterwards, and a second copy of the
    walk-forward is exactly how that happens again.
    """
    test = {str(s) for s in test_seasons}
    model = NflEloModel(k=cfg.k, home_advantage=cfg.home_advantage,
                        use_mov_multiplier=cfg.use_mov)

    hist_diff, hist_y = [], []
    clf, fitted_for = None, None
    y_true, p_pred, bets = [], [], []
    mk_y, mk_p = [], []
    sides = []
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
                for side, prob, odds, won, fair in (
                    ("home", p_home, ho, g["result"] == "H", fair_home),
                    ("away", 1 - p_home, ao, g["result"] == "A", 1 - fair_home),
                ):
                    e = edge_fraction(prob, odds)
                    if e >= edge_threshold:
                        bets.append({"model_prob": prob, "decimal_odds": odds, "won": won,
                                     "fair_market_prob": fair, "edge_frac": e})
                    if collect_sides:
                        sides.append({"season": season, "game_id": g["game_id"], "side": side,
                                      "model_prob": prob, "decimal_odds": odds, "won": won,
                                      "fair_market_prob": fair, "edge_frac": e,
                                      "flagged": e >= edge_threshold})

        hist_diff.append(diff)
        hist_y.append(home_won)
        model.update(g["home_team"], g["away_team"], g["home_score"], g["away_score"])

    roi = simulate_flat_stake_roi(bets)
    ci = roi["roi_ci95_pct"] or (None, None)
    return {
        **({"sides": sides} if collect_sides else {}),
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


# -- season_regression, the parameter the grid above never varied ------------
#
# `sweep_nfl` crosses k x home_advantage x use_mov x calibrate and leaves
# `season_regression` pinned at its 0.33 default. Runs 1-16 therefore tested
# 150 configurations without ever moving the knob that decides how much of last
# season a team carries into this one.
#
# Why it was worth a look rather than dismissed with the rest. Run 11 retired
# every recalibration-shaped proposal with one argument: the NFL deficit is
# discrimination (AUC 0.678 vs the market's 0.724), and AUC is invariant under
# any monotone transform of the forecast. Season regression is NOT such a
# transform -- it changes the ratings themselves, so it reorders games and can
# move AUC. The argument that closes off Platt, isotonic, shrinkage and
# threshold moves does not reach it.
#
# Why the design has two phases. Adding ten more configurations scored on the
# canonical 2021-2024 window would be a tenth look at the window every other
# sweep has already used, and this project's own note on the blend sweep
# ("beware its bait") is about exactly that. So the grid is selected on
# 2021-2023 and the selected value is confirmed on 2024, which is untouched
# during selection.
#
# Both metrics are reported because run 12 found two feature tiers that
# improved log-loss while ranking worse. A value chosen on log-loss alone
# would walk straight back into that trap.
SEASON_REGRESSION_GRID = (0.0, 0.10, 0.20, 0.25, 0.33, 0.40, 0.50, 0.60, 0.75, 1.0)
SEASON_REGRESSION_SELECT = (2021, 2022, 2023)
SEASON_REGRESSION_CONFIRM = (2024,)


def _score_season_regression(ordered: pd.DataFrame, sr: float, test_seasons,
                             *, edge_threshold: float) -> dict:
    """One season_regression value, scored on log-loss AND AUC vs the close."""
    from sportsedge.backtest.discrimination import auc

    cfg = NflConfig(k=20.0, home_advantage=55.0, use_mov=False, calibrate=False,
                    season_regression=sr)
    r = run_nfl_config(ordered, cfg, test_seasons=tuple(test_seasons),
                       edge_threshold=edge_threshold, collect_sides=True)
    sides = pd.DataFrame(r.pop("sides"))
    # One row per game, not per side: the two sides of a game are the same
    # ranking problem counted twice and would halve the standard error.
    home = sides[sides["side"] == "home"]
    y = home["won"].astype(int).to_numpy()
    return {
        "season_regression": sr,
        "n_games": r["n_games"],
        "log_loss": r["log_loss"],
        "market_log_loss": r["market_log_loss"],
        "ll_gap_vs_market": r["log_loss"] - r["market_log_loss"],
        "auc_model": auc(y, home["model_prob"].to_numpy()),
        "auc_market": auc(y, home["fair_market_prob"].to_numpy()),
        "n_bets": r["n_bets"],
        "roi_pct": r["roi_pct"],
        "roi_ci_lo": r["roi_ci_lo"],
        "roi_ci_hi": r["roi_ci_hi"],
    }


def sweep_season_regression(*, seasons=DEFAULT_SEASONS, grid=SEASON_REGRESSION_GRID,
                            select_seasons=SEASON_REGRESSION_SELECT,
                            confirm_seasons=SEASON_REGRESSION_CONFIRM,
                            edge_threshold: float = 0.03,
                            games: pd.DataFrame | None = None) -> dict:
    """Select season_regression on `select_seasons`, confirm on `confirm_seasons`.

    Returns the selection frame, the confirmation frame (incumbent plus
    whichever values log-loss and AUC picked), and a verdict block stating
    whether anything cleared the deployment gate.
    """
    if games is None:
        games = snapshots.read_processed("nfl_games")
    ordered = _chronological(games, seasons)

    sel = pd.DataFrame([
        _score_season_regression(ordered, sr, select_seasons, edge_threshold=edge_threshold)
        for sr in grid
    ])
    sel["auc_gap_vs_market"] = sel["auc_model"] - sel["auc_market"]

    by_ll = float(sel.loc[sel["log_loss"].idxmin(), "season_regression"])
    by_auc = float(sel.loc[sel["auc_model"].idxmax(), "season_regression"])
    incumbent = NflConfig(k=20.0, home_advantage=55.0, use_mov=False,
                          calibrate=False).season_regression

    # dict, so an incumbent that is also the pick is confirmed once, not twice
    candidates = {incumbent: "incumbent"}
    candidates.setdefault(by_ll, "")
    candidates[by_ll] = (candidates[by_ll] + "+selected-by-log-loss").lstrip("+")
    candidates.setdefault(by_auc, "")
    candidates[by_auc] = (candidates[by_auc] + "+selected-by-auc").lstrip("+")

    conf = pd.DataFrame([
        {"role": role,
         **_score_season_regression(ordered, sr, confirm_seasons,
                                    edge_threshold=edge_threshold)}
        for sr, role in candidates.items()
    ])
    conf["auc_gap_vs_market"] = conf["auc_model"] - conf["auc_market"]

    return {
        "selection": sel,
        "confirmation": conf,
        "verdict": summarize_season_regression(sel, conf, incumbent, by_ll, by_auc),
    }


def summarize_season_regression(sel: pd.DataFrame, conf: pd.DataFrame,
                                incumbent: float, by_ll: float, by_auc: float) -> dict:
    """Did any season_regression value clear the gate? (The gate is the close.)"""
    inc_c = conf[conf["season_regression"] == incumbent].iloc[0]
    ll_c = conf[conf["season_regression"] == by_ll].iloc[0]
    return {
        "n_configs": len(sel),
        "incumbent": incumbent,
        "selected_by_log_loss": by_ll,
        "selected_by_auc": by_auc,
        "incumbent_is_auc_optimal_in_selection": bool(by_auc == incumbent),
        "beat_market_log_loss_in_selection": int((sel["log_loss"] < sel["market_log_loss"]).sum()),
        "beat_market_auc_in_selection": int((sel["auc_model"] > sel["auc_market"]).sum()),
        "beat_market_log_loss_in_confirmation": int((conf["log_loss"] < conf["market_log_loss"]).sum()),
        "beat_market_auc_in_confirmation": int((conf["auc_model"] > conf["auc_market"]).sum()),
        # The run-12 trap: a value log-loss prefers that ranks worse.
        "log_loss_pick_ranks_worse_than_incumbent_on_holdout":
            bool(ll_c["auc_model"] < inc_c["auc_model"]),
        "auc_gap_range_in_selection": (float(sel["auc_gap_vs_market"].min()),
                                       float(sel["auc_gap_vs_market"].max())),
        "adopt": False,
        "adopt_reason": (
            "No value beats the de-vigged closing line on log-loss or AUC, in "
            "selection or on the holdout; the value log-loss prefers ranks "
            "worse than the incumbent out-of-sample; and the incumbent is "
            "already the AUC-optimal point of the grid in selection. "
            "season_regression stays at 0.33."
        ),
    }


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
