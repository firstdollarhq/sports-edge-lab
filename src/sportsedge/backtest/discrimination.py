"""Is the model's problem calibration, or discrimination?

Every model change this project has proposed and rejected -- the blend sweep
(run 1, revisited since), the fee-inclusive threshold p3 (run 10), the edge
threshold grid (runs 5, 9) -- is a *recalibration*: it changes the number
attached to a game, or which numbers clear a bar, but not the ORDER the model
puts games in. Run 10 closed with "the real target is the model's
probabilities, not the bet filter" and left open which part of them was wrong.

This module answers it, and the answer bounds the whole family:

  AUC is invariant under any strictly monotone transform of the predictions.

So if the model's AUC is below the market's, then no recalibration of any
kind -- Platt, isotonic, a shrink toward the market, a different threshold, a
fee-inclusive edge -- can close the gap, because none of them reorder anything.
Only a model that ranks games better can. The Murphy decomposition of the
Brier score says the same thing in the other direction: it splits error into
reliability (calibration, fixable by recalibration) and resolution
(discrimination, not).

Measured on ALL priced games, never on `bets`. The bet list is a selected
sample by construction -- that selection is the thing run 4 found and run 9
confirmed -- so it cannot answer a question about the model's raw ranking.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

BOOTSTRAP_SEED = 11
BOOTSTRAP_DRAWS = 5000


def auc(y, p) -> float:
    """Rank-based AUC (Mann-Whitney U), ties handled by average rank."""
    y = np.asarray(y, dtype=float)
    p = np.asarray(p, dtype=float)
    n1, n0 = y.sum(), (1 - y).sum()
    if n1 == 0 or n0 == 0:
        return float("nan")
    ranks = pd.Series(p).rank().to_numpy()
    return float((ranks[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def murphy_decomposition(y, p, bins: int = 10) -> dict:
    """Brier = reliability - resolution + uncertainty, on quantile bins.

    reliability: how far each bin's predicted rate sits from its realized rate
                 (lower is better; a recalibration can drive this toward 0).
    resolution:  how far the bins' realized rates spread from the base rate
                 (HIGHER is better; recalibration cannot raise it).
    uncertainty: base-rate variance. A property of the games, not the model.
    """
    y = np.asarray(y, dtype=float)
    p = np.asarray(p, dtype=float)
    base = y.mean()
    edges = np.quantile(p, np.linspace(0, 1, bins + 1))
    edges[0] -= 1e-9
    edges[-1] += 1e-9
    idx = np.clip(np.digitize(p, edges) - 1, 0, bins - 1)

    reliability = resolution = 0.0
    for b in range(bins):
        mask = idx == b
        if not mask.any():
            continue
        nb = mask.sum()
        reliability += nb * (p[mask].mean() - y[mask].mean()) ** 2
        resolution += nb * (y[mask].mean() - base) ** 2

    n = len(y)
    return {
        "brier": float(np.mean((p - y) ** 2)),
        "reliability": reliability / n,
        "resolution": resolution / n,
        "uncertainty": float(base * (1 - base)),
    }


def _log_loss(y, p) -> float:
    y = np.asarray(y, dtype=float)
    p = np.clip(np.asarray(p, dtype=float), 1e-12, 1 - 1e-12)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def oracle_recalibrated_log_loss(y, p) -> float:
    """Best case for recalibration: isotonic fit on the very outcomes it scores.

    Deliberately cheating -- the calibrator sees the answers -- so it is an
    upper bound on what ANY monotone recalibration of these predictions could
    achieve, not a score the model could earn. If even this does not reach the
    market, recalibration is not the missing piece.
    """
    from sklearn.isotonic import IsotonicRegression

    iso = IsotonicRegression(out_of_bounds="clip").fit(np.asarray(p), np.asarray(y))
    return _log_loss(y, np.clip(iso.predict(np.asarray(p)), 1e-6, 1 - 1e-6))


def auc_gap_bootstrap(y, p_model, p_market, draws: int = BOOTSTRAP_DRAWS,
                      seed: int = BOOTSTRAP_SEED) -> dict:
    """Paired bootstrap on AUC(model) - AUC(market). Seeded, so it reproduces."""
    y = np.asarray(y)
    p_model = np.asarray(p_model)
    p_market = np.asarray(p_market)
    observed = auc(y, p_model) - auc(y, p_market)

    rng = np.random.default_rng(seed)
    diffs = []
    for _ in range(draws):
        i = rng.integers(0, len(y), len(y))
        ys = y[i]
        if ys.sum() == 0 or ys.sum() == len(ys):
            continue
        diffs.append(auc(ys, p_model[i]) - auc(ys, p_market[i]))
    diffs = np.array(diffs)
    lo, hi = np.percentile(diffs, [2.5, 97.5])
    return {
        "auc_model": auc(y, p_model),
        "auc_market": auc(y, p_market),
        "gap": observed,
        "ci95": [float(lo), float(hi)],
        "share_model_ranks_better": float((diffs > 0).mean()),
        "draws_used": int(len(diffs)),
    }


def discrimination_report(predictions: list[dict]) -> dict:
    """`predictions` is the per-game list the backtest engines now return."""
    df = pd.DataFrame(predictions).dropna(subset=["p_model", "p_market"])
    if df.empty:
        return {"n": 0, "note": "no game carried both a model and a market price"}

    y = df["y"].to_numpy()
    pm, pk = df["p_model"].to_numpy(), df["p_market"].to_numpy()

    model_d = murphy_decomposition(y, pm)
    market_d = murphy_decomposition(y, pk)
    boot = auc_gap_bootstrap(y, pm, pk)
    oracle = oracle_recalibrated_log_loss(y, pm)

    return {
        "n_games": int(len(df)),
        "model": {**model_d, "log_loss": _log_loss(y, pm), "auc": boot["auc_model"]},
        "market": {**market_d, "log_loss": _log_loss(y, pk), "auc": boot["auc_market"]},
        "auc_gap": {k: boot[k] for k in
                    ("gap", "ci95", "share_model_ranks_better", "draws_used")},
        "oracle_recalibrated_model_log_loss": oracle,
        # Deliberately not named "recalibration_can_close_the_gap": this is a
        # one-sided test. False is conclusive; True is the expected behaviour of
        # an in-sample isotonic fit and means nothing. See _verdict.
        "recalibration_ruled_out": bool(oracle > _log_loss(y, pk)),
        "verdict": _verdict(boot, oracle, _log_loss(y, pk)),
    }


def _verdict(boot: dict, oracle: float, market_ll: float) -> str:
    """The oracle bound is a ONE-SIDED test, and the asymmetry matters.

    In-sample isotonic can only ever improve on the input, and the thinner the
    sample the more of that improvement is fitting noise. So:

      oracle FAILS to reach the market -> conclusive. Not even a cheating
        recalibration gets there, therefore no honest one does either.
      oracle REACHES the market -> says nothing. It is the expected result of
        letting a flexible monotone fit see the answers, and must not be read
        as "recalibration would fix this leg".

    Encoded here because the EPL leg lands in exactly the second case (n=380,
    oracle 0.576 vs market 0.590) and reads as encouraging until you notice it
    is unfalsifiable.
    """
    lo, hi = boot["ci95"]
    if lo > 0:
        return "model ranks games significantly BETTER than the market."
    if hi < 0:
        if oracle > market_ll:
            return ("model ranks games significantly WORSE than the market, and even "
                    "an oracle recalibration does not reach the market's log-loss. "
                    "Conclusive: recalibration-shaped changes cannot fix this leg.")
        return ("model ranks games significantly WORSE than the market. The oracle "
                "recalibration does reach the market's log-loss, but that is "
                "in-sample and proves nothing -- treat the ranking gap as the "
                "binding constraint until an out-of-sample recalibration beats it.")
    return "no significant ranking difference between model and market."
