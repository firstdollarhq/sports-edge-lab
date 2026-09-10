"""Odds conversion, de-vig, edge, and Kelly staking math."""
from __future__ import annotations


def american_to_decimal(american: float) -> float:
    if american > 0:
        return 1 + american / 100
    return 1 + 100 / abs(american)


def decimal_to_implied_prob(decimal_odds: float) -> float:
    return 1 / decimal_odds


def devig_two_way(prob_a: float, prob_b: float) -> tuple[float, float]:
    """Normalize two implied probabilities that sum to >1 (vig) back to 1."""
    total = prob_a + prob_b
    return prob_a / total, prob_b / total


def devig_three_way(prob_h: float, prob_d: float, prob_a: float) -> tuple[float, float, float]:
    total = prob_h + prob_d + prob_a
    return prob_h / total, prob_d / total, prob_a / total


def edge_pct(model_prob: float, decimal_odds: float) -> float:
    """Expected value per $1 staked: model_prob * decimal_odds - 1."""
    return model_prob * decimal_odds - 1


def kelly_fraction(model_prob: float, decimal_odds: float, kelly_multiplier: float = 0.25) -> float:
    """Fractional Kelly stake as a fraction of bankroll. Returns 0 if no edge."""
    b = decimal_odds - 1
    if b <= 0:
        return 0.0
    p = model_prob
    q = 1 - p
    f_star = (b * p - q) / b
    return max(0.0, f_star * kelly_multiplier)
