"""Score settled bets against what the model claimed AND what the market said.

`ledger.summarize` answers "how did we do". It cannot answer the question this
project actually exists to ask, which is "did the model know something the
closing line did not". For that you need three numbers on the same population:
what the model expected, what the market expected, and what happened.

The market's number is the control. A win rate below the model's claim proves
nothing on its own -- the model bets longshots, so a low win rate is the
expected outcome of a *correct* model. The test is whether the model's
probabilities beat the market's on the bets the model chose, which is the
narrowest place the two ever disagree and the only place the money moves.

Two things this deliberately refuses to do:

* **Report row counts as sample size.** Until 2026-09-13 the ledger held each
  wager twice (see `ledger.void_superseded_rows`), and a duplicate always
  shares its twin's outcome. Fourteen such rows are seven trials, and a CI
  over fourteen is narrow by ~sqrt(2) for no reason. `effective_n` counts
  distinct (contract, selection) wagers and every interval here uses it.
* **Hand back a p-value without the expected count next to it.** P(X <= k)
  under the model's own probabilities is the honest form of "is this worse
  than the model said", and at these sample sizes it is almost always
  unremarkable. Printing it beside the expectation makes that visible instead
  of inviting a story about whichever direction the point estimate fell.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from sportsedge.betting.ledger import SETTLED_STATUSES, _load


def _poisson_binomial_pmf(probs: np.ndarray) -> np.ndarray:
    """Exact distribution of the number of wins among independent, unequal p.

    The bets in a cohort have wildly different probabilities (0.14 to 0.63 in
    the first EPL cohort), so a binomial on the mean is the wrong null.
    """
    dist = np.array([1.0])
    for p in probs:
        dist = np.convolve(dist, [1.0 - p, p])
    return dist


def _log_loss(p: np.ndarray, y: np.ndarray) -> float:
    p = np.clip(p.astype(float), 1e-9, 1 - 1e-9)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def _brier(p: np.ndarray, y: np.ndarray) -> float:
    return float(np.mean((p.astype(float) - y) ** 2))


def score(df: pd.DataFrame | None = None, *, sport: str | None = None) -> dict:
    """Model vs market vs reality on settled, non-void bets."""
    if df is None:
        df = _load()
    if df.empty:
        return {"n": 0}
    d = df[df["status"].isin(SETTLED_STATUSES) & (df["status"] != "void")].copy()
    if sport is not None:
        d = d[d["sport"] == sport]
    d = d[d["status"] != "push"]
    if d.empty:
        return {"n": 0, "sport": sport}

    y = (d["status"] == "won").to_numpy().astype(int)
    model = d["model_prob"].to_numpy(dtype=float)
    market = d["market_fair_prob"].to_numpy(dtype=float)
    odds = d["market_odds_decimal"].to_numpy(dtype=float)
    wins = int(y.sum())

    # A wager logged twice is one trial, not two. Void rows are already gone,
    # but the guard stays: this is the number every interval below divides by.
    effective_n = int(len(d.groupby(["market_ticker", "selection"], dropna=False)))

    ret = np.where(y == 1, odds - 1.0, -1.0)
    out = {
        "sport": sport or "all",
        "rows": len(d),
        "effective_n": effective_n,
        "wins": wins,
        "win_rate_pct": 100.0 * wins / len(d),
        "model_expected_wins": float(model.sum()),
        "market_expected_wins": float(market.sum()),
        "roi_pct": 100.0 * float(ret.sum()) / len(d),
        "profit_units": float(ret.sum()),
        "model_log_loss": _log_loss(model, y),
        "market_log_loss": _log_loss(market, y),
        "model_brier": _brier(model, y),
        "market_brier": _brier(market, y),
        "mean_model_prob": float(model.mean()),
        "mean_market_prob": float(market.mean()),
    }
    # Positive means the model is WORSE than the closing line on the bets it
    # chose. That is the number the deployment gate is about.
    out["log_loss_gap_vs_market"] = out["model_log_loss"] - out["market_log_loss"]
    out["model_overstatement_pp"] = 100.0 * (out["mean_model_prob"] - wins / len(d))
    out["market_overstatement_pp"] = 100.0 * (out["mean_market_prob"] - wins / len(d))

    for label, probs in (("model", model), ("market", market)):
        pmf = _poisson_binomial_pmf(probs)
        out[f"p_at_most_{label}"] = float(pmf[: wins + 1].sum())
    if len(d) != effective_n:
        out["warning"] = (
            f"{len(d)} rows cover only {effective_n} distinct wagers; "
            "treat row count as bookkeeping, not sample size"
        )
    return out


def summarize(sports: tuple[str, ...] = ("nfl", "soccer")) -> dict:
    return {"all": score(), **{s: score(sport=s) for s in sports}}
