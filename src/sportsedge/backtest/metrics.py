"""Scoring metrics for probability forecasts and simulated betting ROI."""
from __future__ import annotations

import math


def log_loss(y_true: list[int], p_pred: list[float], eps: float = 1e-12) -> float:
    total = 0.0
    for y, p in zip(y_true, p_pred):
        p = min(max(p, eps), 1 - eps)
        total += -(y * math.log(p) + (1 - y) * math.log(1 - p))
    return total / len(y_true)


def brier_score(y_true: list[int], p_pred: list[float]) -> float:
    return sum((p - y) ** 2 for y, p in zip(y_true, p_pred)) / len(y_true)


def simulate_flat_stake_roi(bets: list[dict]) -> dict:
    """bets: [{model_prob, decimal_odds, won: bool}]. Flat $1 stake per bet.

    Always reports the uncertainty alongside the point estimate. A bare ROI
    number invites exactly the bias this project exists to avoid: the EPL
    2025-26 holdout returned +8.27%, which reads like a discovery until you
    see t=+0.84 and a 95% interval of [-10.7%, +28.0%].
    """
    if not bets:
        return {"n_bets": 0, "roi_pct": None, "win_rate": None, "total_staked": 0,
                "total_return": 0, "roi_se_pp": None, "roi_t_stat": None,
                "roi_ci95_pct": None, "significant_at_95": None}
    staked = len(bets)
    returned = sum(b["decimal_odds"] if b["won"] else 0.0 for b in bets)
    wins = sum(1 for b in bets if b["won"])

    pnl = [(b["decimal_odds"] - 1) if b["won"] else -1.0 for b in bets]
    mean = sum(pnl) / len(pnl)
    if len(pnl) > 1:
        var = sum((x - mean) ** 2 for x in pnl) / (len(pnl) - 1)
        se = math.sqrt(var / len(pnl))
    else:
        se = float("nan")
    t_stat = mean / se if se and not math.isnan(se) and se > 0 else None
    # Normal approximation is adequate at these sample sizes and keeps this
    # dependency-free; the bootstrap agreed to within a few tenths of a point.
    ci = ((mean - 1.96 * se) * 100, (mean + 1.96 * se) * 100) if se == se else None

    return {
        "n_bets": len(bets),
        "roi_pct": (returned - staked) / staked * 100,
        "win_rate": wins / len(bets) * 100,
        "total_staked": staked,
        "total_return": returned,
        "roi_se_pp": se * 100 if se == se else None,
        "roi_t_stat": t_stat,
        "roi_ci95_pct": ci,
        "significant_at_95": bool(ci and not (ci[0] < 0 < ci[1])),
    }


def bets_needed_for_significance(bets: list[dict], sigma: float = 2.0) -> float | None:
    """How many bets it would take to resolve an edge of the observed size.

    Answers 'is this worth waiting out?' honestly. The EPL result needs ~1,600
    bets -- more than four full EPL seasons of betting every flagged game.
    """
    if not bets:
        return None
    pnl = [(b["decimal_odds"] - 1) if b["won"] else -1.0 for b in bets]
    mean = sum(pnl) / len(pnl)
    if mean <= 0 or len(pnl) < 2:
        return None
    var = sum((x - mean) ** 2 for x in pnl) / (len(pnl) - 1)
    return (sigma * math.sqrt(var) / mean) ** 2
