"""Is a quoted price actually fillable, or is it a stale/illiquid artifact?

Kalshi order-book depth varies enormously by market: a marquee NFL game and an
obscure midweek fixture can both print a "price", but only one of them is a
price you could actually trade at. Treating a wide, empty book as a real market
quote manufactures fake edges -- the model looks brilliant against a price
nobody is offering.

The thresholds below are deliberately conservative defaults, not tuned values.
They exist so that "we filtered for liquidity" is a concrete, auditable rule
rather than a vibe. Every rejection is recorded with a reason so the filter's
own selectivity can be reviewed later.
"""
from __future__ import annotations

from dataclasses import dataclass

from sportsedge.betting.edge import spread_cost_fraction

# A 1-cent-wide book on a $1 contract is 1% of notional; 5c is where the
# round-trip cost starts to swamp any edge we could plausibly detect.
MAX_SPREAD = 0.05
# ...and an absolute cap is the wrong SHAPE for a book's width. The same 2c
# spread is 1.0% of a $1.00-ish contract and 14.3% of a $0.07 one, so a single
# cent threshold is strict on favourites and nearly meaningless on longshots.
# Measured on the live board 2026-09-10: relative width (ask/mid - 1) runs to a
# median of 1.23% on NFL and 1.89% on EPL, with a long tail -- worst observed
# was Sunderland at Man City, bid 0.06 / ask 0.08, at 14.3%, which passes every
# absolute check above.
#
# NOTE ON WHAT THIS IS NOT. Because recommend.py already prices edges at the
# ask, the cost of crossing is paid inside the edge number itself; this gate is
# not a second deduction for it and must not be described as one. Its actual
# job is as a proxy for two things a wide relative book implies: the de-vigged
# "fair probability" we measure disagreement against is unreliable, and size is
# unlikely to fill near the touch. So it is set to catch the pathological tail
# only -- 0.40/0.42 (2.4%) is an ordinary market and must pass.
MAX_SPREAD_COST = 0.05
# Contracts resting on the side we would hit.
MIN_SIZE = 50.0
# Total traded interest in the market's lifetime.
MIN_VOLUME = 500.0
# Prices at the extremes are dominated by fee/rounding effects and have almost
# no room for a real mispricing.
MIN_PRICE = 0.03
MAX_PRICE = 0.97


@dataclass(frozen=True)
class LiquidityVerdict:
    ok: bool
    reason: str = ""


def check(row: dict, *, max_spread: float = MAX_SPREAD, min_size: float = MIN_SIZE,
          min_volume: float = MIN_VOLUME, min_price: float = MIN_PRICE,
          max_price: float = MAX_PRICE,
          max_spread_cost: float = MAX_SPREAD_COST) -> LiquidityVerdict:
    """Decide whether a snapshot row represents a tradeable price.

    `row` is a dict as produced by ingest.kalshi.snapshot_moneylines.
    """
    bid, ask = row.get("yes_bid"), row.get("yes_ask")
    if bid is None or ask is None:
        return LiquidityVerdict(False, "no two-sided quote")
    if bid <= 0 or ask <= 0:
        return LiquidityVerdict(False, "one-sided book")

    spread = ask - bid
    if spread > max_spread:
        return LiquidityVerdict(False, f"spread {spread:.3f} > {max_spread}")

    mid = row.get("implied_prob_mid")
    if mid is None:
        return LiquidityVerdict(False, "no mid price")
    if not (min_price <= mid <= max_price):
        return LiquidityVerdict(False, f"mid {mid:.3f} outside [{min_price}, {max_price}]")

    # We buy the 'yes' side, so the ask is the side we would lift.
    ask_size = row.get("yes_ask_size") or 0.0
    if ask_size < min_size:
        return LiquidityVerdict(False, f"ask size {ask_size:.0f} < {min_size:.0f}")

    volume = row.get("volume") or 0.0
    if volume < min_volume:
        return LiquidityVerdict(False, f"volume {volume:.0f} < {min_volume:.0f}")

    # Relative cost of lifting the ask instead of trading at the mid. Checked
    # last so the reason string reports the specific, quantified objection.
    cost = spread_cost_fraction(bid, ask)
    if cost is None or cost > max_spread_cost:
        return LiquidityVerdict(
            False, f"crossing the spread costs {cost:.1%} > {max_spread_cost:.1%}")

    return LiquidityVerdict(True)


def partition(rows: list[dict], **kwargs) -> tuple[list[dict], list[dict]]:
    """Split snapshot rows into (fillable, rejected); rejected rows get a reason."""
    keep, drop = [], []
    for row in rows:
        verdict = check(row, **kwargs)
        if verdict.ok:
            keep.append(row)
        else:
            drop.append({**row, "reject_reason": verdict.reason})
    return keep, drop
