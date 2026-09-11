"""Two questions about the bet-selection rule, asked of the backtest.

Both exist because of what the 2026-09-11 board looked like: the NFL model
flagged 25 of 57 fillable contracts (43.9%) as +EV, with claimed edges up to
+52.8%, and 29 of the 35 open shadow bets were on sides the market priced
below even money. A model finding a 3% edge on two contracts in five of a
regulated exchange is not finding edge. It is describing itself.


1. selection_audit -- is the model wrong, or is the RULE picking its errors?
--------------------------------------------------------------------------
Compare the model's calibration on the sides it bets against the sides it
passes, within the same predicted-probability buckets. Unconditional
calibration can be fine while conditional calibration is terrible, and that
gap has a name: the winner's curse. You bet precisely where your estimate
most exceeds the market's, so you bet precisely where your own error is most
likely to be positive. The bets are a biased sample of the forecasts.

This distinction matters for what you do next. If the ratings were badly
calibrated, retuning Elo would help. If the ratings are fine and the
SELECTION is biased, no amount of retuning touches it -- which is the
difference between "keep sweeping parameters" and "stop sweeping parameters".


2. blend_sweep -- does the model know anything the closing line doesn't?
-----------------------------------------------------------------------
Score w*model + (1-w)*market for w over [0, 1]. The market price is a
forecast too, and a better one; the only interesting question is whether the
model carries any information the price has NOT already absorbed.

    w* = 0    the model adds nothing. Any weight makes the forecast worse.
    w* > 0    there is residual information, and its size is w*.

This is a sharper test than a parameter sweep, because it cannot be passed by
accident. A config can luck into a good log-loss; a blend weight cannot luck
into being positive across a whole grid -- the curve is smooth in w, and w=0
is always available as the do-nothing baseline.

The baseline is always the de-vigged closing line, never a previous version
of the model, per the deployment gate in config/leagues.yaml.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from sportsedge.backtest.metrics import log_loss, simulate_flat_stake_roi
from sportsedge.backtest.sweep import (DEFAULT_SEASONS, DEFAULT_TEST_SEASONS, NflConfig,
                                       _chronological, run_nfl_config)
from sportsedge.betting.edge import devig_three_way, edge_fraction
from sportsedge.models.calibration import SoccerOutcomeCalibrator
from sportsedge.models.elo import SoccerEloModel
from sportsedge.storage import snapshots

BLEND_WEIGHTS = (0.0, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50, 0.75, 1.0)
PROB_BUCKETS = (0.0, 0.20, 0.30, 0.40, 0.50, 0.60, 1.01)


# -- side collection ---------------------------------------------------------
#
# Both sports produce the same frame: one row per priced side, carrying the
# model probability, the de-vigged market probability, the price, whether it
# won, and whether the rule flagged it.

def nfl_sides(*, seasons=DEFAULT_SEASONS, test_seasons=DEFAULT_TEST_SEASONS,
              cfg: NflConfig | None = None, edge_threshold: float = 0.03,
              games: pd.DataFrame | None = None) -> pd.DataFrame:
    """Every priced NFL side over the test seasons, flagged or not."""
    games = snapshots.read_processed("nfl_games") if games is None else games
    cfg = cfg or NflConfig(k=20.0, home_advantage=55.0, use_mov=False, calibrate=False)
    res = run_nfl_config(_chronological(games, seasons), cfg,
                         test_seasons=test_seasons, edge_threshold=edge_threshold,
                         collect_sides=True)
    return pd.DataFrame(res["sides"])


# An EPL season is 380 games. A season with far fewer is in progress, and
# holding one out produces a tiny, early-season sample whose noise dwarfs
# anything being measured.
MIN_HOLDOUT_GAMES = 200


def epl_sides(*, edge_threshold: float = 0.03, min_holdout_games: int = MIN_HOLDOUT_GAMES,
              games: pd.DataFrame | None = None) -> pd.DataFrame:
    """Every priced EPL side over the holdout season, flagged or not.

    Mirrors backtest.engine.backtest_soccer: the outcome calibrator is fit on
    every season before the holdout and the holdout is scored, while Elo itself
    walks forward game by game throughout.

    The holdout is the last COMPLETE season, not simply the last one. Written
    without that guard, this function held out the 30 games of 2026-27 played
    so far and reported `model_adds_information: true` with w* = 0.75 -- a
    conclusion that reverses to w* = 0 on a full season. `cli._load_games`
    carries a docstring warning about this exact failure, which is what it
    cost to rediscover it.
    """
    games = snapshots.read_processed("epl_games") if games is None else games
    games = games.sort_values(["season", "game_date"]).dropna(subset=["home_score", "away_score"])
    played = games.groupby(games["season"].astype(str)).size()
    complete = sorted(played[played >= min_holdout_games].index)
    if not complete:
        raise ValueError(
            f"No season has {min_holdout_games}+ played games; "
            f"largest is {played.max() if len(played) else 0}")
    test_season = complete[-1]
    seasons = sorted(s for s in games["season"].astype(str).unique() if s <= test_season)
    if len(seasons) < 2:
        raise ValueError("Need at least 2 seasons: one to calibrate, one to test")
    games = games[games["season"].astype(str).isin(seasons)]

    model = SoccerEloModel()
    diffs, outcomes = [], []
    for _, g in games[games["season"].astype(str) != test_season].iterrows():
        diffs.append(model.elo_diff(g["home_team"], g["away_team"]))
        outcomes.append(g["result"])
        model.update(g["home_team"], g["away_team"], g["home_score"], g["away_score"])
    calibrator = SoccerOutcomeCalibrator()
    calibrator.fit(diffs, outcomes)

    rows = []
    for _, g in games[games["season"].astype(str) == test_season].iterrows():
        probs = calibrator.predict_proba(model.elo_diff(g["home_team"], g["away_team"]))
        ho, do, ao = (g.get("home_odds_decimal"), g.get("draw_odds_decimal"),
                      g.get("away_odds_decimal"))
        if pd.notna(ho) and pd.notna(do) and pd.notna(ao):
            fair_h, fair_d, fair_a = devig_three_way(1 / ho, 1 / do, 1 / ao)
            for outcome, odds, fair in (("H", ho, fair_h), ("D", do, fair_d), ("A", ao, fair_a)):
                p = float(probs.get(outcome, 0.0))
                e = edge_fraction(p, odds)
                rows.append({"season": test_season, "game_id": g["game_id"], "side": outcome,
                             "model_prob": p, "decimal_odds": odds,
                             "won": g["result"] == outcome, "fair_market_prob": fair,
                             "edge_frac": e, "flagged": e >= edge_threshold})
        model.update(g["home_team"], g["away_team"], g["home_score"], g["away_score"])
    return pd.DataFrame(rows)


# -- 1. the selection audit --------------------------------------------------

def _bucket_rows(sides: pd.DataFrame) -> list[dict]:
    out = []
    for lo, hi in zip(PROB_BUCKETS[:-1], PROB_BUCKETS[1:]):
        sub = sides[(sides["model_prob"] >= lo) & (sides["model_prob"] < hi)]
        if sub.empty:
            continue
        out.append({"bucket": f"{lo:.2f}-{hi:.2f}", "n": len(sub),
                    "claimed": float(sub["model_prob"].mean()),
                    "actual": float(sub["won"].mean()),
                    "gap": float(sub["won"].mean() - sub["model_prob"].mean())})
    return out


def selection_audit(sides: pd.DataFrame) -> dict:
    """Calibration of the sides the rule bets vs the sides it passes.

    `overall_gap` on the full frame is close to meaningless and is not
    reported: the model's probabilities sum to 1 across a game's sides and so
    do the realized outcomes, so it is pinned near zero by construction. The
    per-bucket gaps are not, and neither is the flagged/passed split.
    """
    flagged, passed = sides[sides["flagged"]], sides[~sides["flagged"]]

    def summarize(sub):
        if sub.empty:
            return {"n": 0}
        return {"n": len(sub), "claimed": float(sub["model_prob"].mean()),
                "actual": float(sub["won"].mean()),
                "gap": float(sub["won"].mean() - sub["model_prob"].mean()),
                "by_bucket": _bucket_rows(sub)}

    return {
        "n_sides": len(sides),
        "n_flagged": int(len(flagged)),
        "flagged_rate_pct": 100.0 * len(flagged) / len(sides) if len(sides) else float("nan"),
        "all": {"by_bucket": _bucket_rows(sides)},
        "flagged": summarize(flagged),
        "passed": summarize(passed),
        # The headline: how far the bet sides and the passed sides pull apart.
        # Driven by selection, not by the ratings -- see the module docstring.
        "selection_gap": (float(flagged["won"].mean() - flagged["model_prob"].mean())
                          - float(passed["won"].mean() - passed["model_prob"].mean()))
        if len(flagged) and len(passed) else float("nan"),
    }


# -- 2. the blend sweep ------------------------------------------------------

def _blend_log_loss(sides: pd.DataFrame, blended: pd.Series) -> float:
    """Log-loss over outcomes, one term per realized winner.

    Scored on the winning side of each game rather than per-side, so NFL
    (2 sides) and EPL (3 sides) are measured the same way and neither
    double-counts a game.

    This is NOT identical to the `market_log_loss` the sweep reports, and the
    two should not be quoted against each other. The sweep scores NFL as a
    binary home-win question, which files a tie as a home loss; this drops the
    game, since a tie leaves the moneyline with no winning side at all. Over
    2021-24 that is 3 games of 1,139 and it moves the market baseline from
    0.6116 to 0.6111.

    Harmless for what this module asks -- every w is scored on the same games,
    so w* is unaffected -- but a 0.0005 discrepancy between two numbers both
    called "log-loss" is exactly the sort of thing this project has twice found
    at the bottom of a wrong conclusion.
    """
    won = blended[sides["won"].to_numpy(dtype=bool)]
    return float(-np.log(np.clip(won.to_numpy(dtype=float), 1e-15, 1.0)).mean())


def blend_sweep(sides: pd.DataFrame, *, weights=BLEND_WEIGHTS,
                edge_threshold: float = 0.03) -> pd.DataFrame:
    """Score w*model + (1-w)*market across `weights`. w=0 is the market alone."""
    rows = []
    for w in weights:
        blended = w * sides["model_prob"] + (1 - w) * sides["fair_market_prob"]
        edges = [edge_fraction(p, o) for p, o in zip(blended, sides["decimal_odds"])]
        bets = [{"model_prob": p, "decimal_odds": o, "won": bool(won)}
                for p, o, won, e in zip(blended, sides["decimal_odds"], sides["won"], edges)
                if e >= edge_threshold]
        roi = simulate_flat_stake_roi(bets) if bets else {}
        ci = roi.get("roi_ci95_pct") or (None, None)
        rows.append({"w": w, "log_loss": _blend_log_loss(sides, blended),
                     "n_bets": len(bets), "roi_pct": roi.get("roi_pct"),
                     "roi_ci_lo": ci[0], "roi_ci_hi": ci[1]})
    df = pd.DataFrame(rows)
    df["vs_market"] = df["log_loss"] - df.loc[df["w"] == 0.0, "log_loss"].iloc[0]
    return df


def bootstrap_ll_delta(sides: pd.DataFrame, w: float, *, n_boot: int = 2000,
                       seed: int = 0) -> tuple[float, float]:
    """95% interval for (blend log-loss - market log-loss) at weight `w`.

    Resampled over GAMES, not sides, since a game's sides are one observation.

    The project's own standard is that a bare ROI is not a result; a bare
    log-loss difference is not either. EPL's best weight improved on the market
    by 0.0002 -- a number that reads as "the model knows something" and is
    inside its own noise.
    """
    blended = w * sides["model_prob"] + (1 - w) * sides["fair_market_prob"]
    won = sides["won"].to_numpy(dtype=bool)
    per_side = -np.log(np.clip(blended.to_numpy(dtype=float), 1e-15, 1.0))
    mkt_side = -np.log(np.clip(sides["fair_market_prob"].to_numpy(dtype=float), 1e-15, 1.0))

    games = sides["game_id"].to_numpy()
    order = pd.unique(games)
    idx = {g: np.flatnonzero((games == g) & won) for g in order}
    deltas = np.array([
        (per_side[i].sum() - mkt_side[i].sum()) / max(len(i), 1) if len(i) else 0.0
        for g in order for i in (idx[g],)
    ])
    counted = np.array([len(idx[g]) > 0 for g in order])
    pool = deltas[counted]
    if not len(pool):
        return (float("nan"), float("nan"))

    rng = np.random.default_rng(seed)
    draws = rng.integers(0, len(pool), size=(n_boot, len(pool)))
    means = pool[draws].mean(axis=1)
    return (float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5)))


def summarize_blend(df: pd.DataFrame, sides: pd.DataFrame | None = None) -> dict:
    """The one question the blend asks, and the trap sitting next to it.

    `model_adds_information` is a raw sign test on log-loss with no
    significance attached; pass `sides` to get a bootstrap interval on the best
    weight's improvement, which is the number that should actually decide
    anything.
    """
    best = df.loc[df["log_loss"].idxmin()]
    positive = df[(df["w"] > 0) & (df["vs_market"] < 0)]
    # Small-w rows bet a handful of times and can post a spectacular ROI on
    # noise. Reporting it next to its own interval is the point: the 2026-09-11
    # NFL sweep produced +10.19% at w=0.05 on 32 bets, CI [-73.9, +94.3], from
    # a weight that log-loss says is strictly worse than betting nothing.
    tempting = df[(df["roi_pct"].notna()) & (df["roi_pct"] > 0)]
    ci = (bootstrap_ll_delta(sides, float(best["w"]))
          if sides is not None and float(best["w"]) > 0 else (None, None))
    return {
        "best_w": float(best["w"]),
        "best_log_loss": float(best["log_loss"]),
        "market_log_loss": float(df.loc[df["w"] == 0.0, "log_loss"].iloc[0]),
        "best_improvement": float(-best["vs_market"]),
        "best_improvement_ci95": list(ci) if ci[0] is not None else None,
        # True only if the interval excludes zero. Without `sides` this falls
        # back to the bare sign test, which fires on a 0.0002 difference.
        "improvement_significant": (bool(ci[1] is not None and ci[1] < 0)
                                    if ci[0] is not None else None),
        "weights_beating_market": int(len(positive)),
        "model_adds_information": bool(len(positive) > 0),
        "monotone_in_w": bool(df.sort_values("w")["log_loss"].is_monotonic_increasing),
        "positive_roi_weights": [
            {"w": float(r.w), "roi_pct": float(r.roi_pct), "n_bets": int(r.n_bets),
             "ci": [r.roi_ci_lo, r.roi_ci_hi], "log_loss_vs_market": float(r.vs_market)}
            for r in tempting.itertuples()
        ],
    }
