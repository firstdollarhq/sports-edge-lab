"""Odds conversion, de-vig, edge, and Kelly staking math.

UNITS -- read this before touching anything here.

`edge_fraction()` returns a FRACTION (0.03 == a 3% edge). Everything
human-facing -- `config/leagues.yaml`, CLI flags, the ledger CSV, journal
entries -- is in PERCENT. Convert at the boundary, never in the middle.

This function used to be called `edge_pct`, which collided with the
ledger's `edge_pct` column (percent) and with `summarize()["avg_edge_pct"]`
(percent). Same name, two different units, one of which would have been
silently written into the permanent bet record. Renamed rather than
documented.

EXECUTABLE PRICE -- on an exchange (Kalshi) you do not trade at the mid.
You lift the ask to buy. Edge computed off the mid is edge you cannot
capture; see `spread_cost_fraction()` for how much that costs.
"""
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


def edge_fraction(model_prob: float, decimal_odds: float) -> float:
    """Expected value per $1 staked, as a fraction: model_prob * decimal_odds - 1."""
    return model_prob * decimal_odds - 1


def edge_percent(model_prob: float, decimal_odds: float) -> float:
    """Same as `edge_fraction` but in percent, for ledger/journal/CLI use."""
    return edge_fraction(model_prob, decimal_odds) * 100


# -- exchange (Kalshi) pricing -------------------------------------------------
#
# A Kalshi binary contract settles at $1. Its dollar price IS the implied
# probability, so decimal odds are simply 1/price.


def decimal_odds_from_price(price: float) -> float:
    """Decimal odds for a $1-settling binary contract bought at `price` dollars."""
    if not 0 < price < 1:
        raise ValueError(f"contract price must be in (0, 1), got {price}")
    return 1 / price


def executable_price(yes_bid: float, yes_ask: float, side: str = "yes") -> float | None:
    """The price you actually pay, not the mid.

    Buying YES means lifting the ask. Buying NO means hitting the YES bid
    (a NO contract costs 1 - yes_bid). Returns None if the book is not
    two-sided, because a one-sided book is not a tradeable price.
    """
    if yes_bid is None or yes_ask is None:
        return None
    yes_bid, yes_ask = float(yes_bid), float(yes_ask)
    if yes_bid <= 0 or yes_ask <= 0 or yes_ask <= yes_bid:
        return None
    if side == "yes":
        return yes_ask
    if side == "no":
        return 1 - yes_bid
    raise ValueError(f"side must be 'yes' or 'no', got {side!r}")


def mid_price(yes_bid: float, yes_ask: float) -> float | None:
    """Midpoint of the book -- a fair-value estimate, NOT a tradeable price."""
    if yes_bid is None or yes_ask is None:
        return None
    yes_bid, yes_ask = float(yes_bid), float(yes_ask)
    if yes_bid <= 0 and yes_ask <= 0:
        return None
    return (yes_bid + yes_ask) / 2


def spread_cost_fraction(yes_bid: float, yes_ask: float) -> float | None:
    """How much apparent edge evaporates when you price at the ask, not the mid.

    edge = p/price - 1, so switching the denominator from mid to ask costs
    exactly ask/mid - 1. On thin longshot contracts this routinely exceeds
    the entire edge threshold.
    """
    mid = mid_price(yes_bid, yes_ask)
    if mid is None or mid <= 0:
        return None
    return float(yes_ask) / mid - 1


def kelly_fraction(model_prob: float, decimal_odds: float, kelly_multiplier: float = 0.25) -> float:
    """Fractional Kelly stake as a fraction of bankroll. Returns 0 if no edge."""
    b = decimal_odds - 1
    if b <= 0:
        return 0.0
    p = model_prob
    q = 1 - p
    f_star = (b * p - q) / b
    return max(0.0, f_star * kelly_multiplier)
