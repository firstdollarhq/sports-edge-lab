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
    """bets: [{model_prob, decimal_odds, won: bool}]. Flat $1 stake per bet."""
    if not bets:
        return {"n_bets": 0, "roi_pct": None, "win_rate": None, "total_staked": 0, "total_return": 0}
    staked = len(bets)
    returned = sum(b["decimal_odds"] if b["won"] else 0.0 for b in bets)
    wins = sum(1 for b in bets if b["won"])
    return {
        "n_bets": len(bets),
        "roi_pct": (returned - staked) / staked * 100,
        "win_rate": wins / len(bets) * 100,
        "total_staked": staked,
        "total_return": returned,
    }
