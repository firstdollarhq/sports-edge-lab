"""Turn live market snapshots + current model ratings into bet recommendations.

This closes the loop the project was missing: model -> live odds -> de-vig ->
edge -> ledger. Until this existed, `bets/ledger.csv` could never fill, so every
"review the bets" pass was structurally guaranteed to find nothing.

Two deliberate choices about honesty:

1. **We price at the ask, not the mid.** The ask is what you would actually pay
   to lift the offer. Pricing at the mid quietly credits the model with half the
   spread on every bet -- free edge that does not exist. On a 1-cent book that
   is ~0.5% of notional, which is the same order of magnitude as the edges we're
   hunting for, so it is not a rounding detail.

   The ask is not the whole price, though, and the point above understates the
   problem it was written about. Kalshi charges a trading fee on top, and
   `backtest.kalshi_engine` measured it as the LARGER of the two costs by some
   distance: across the NFL backtest's bets the spread takes ~1.7% of stake and
   the fee ~4.7%. `edge_pct` here is computed at the ask alone, so every edge
   this module has ever logged is overstated by roughly the fee.

   `edge_after_fee_pct` reports the fee-inclusive number alongside. It is
   deliberately NOT the number the threshold tests -- see the note on
   FEE_RATE_ASSUMPTION below.

2. **Recommendations are SHADOW by default.** Both baseline models currently
   lose to the closing line in backtest, so nothing here is a validated edge.
   Shadow rows are recorded (they are how we accumulate out-of-sample evidence)
   but are excluded from headline win-rate/ROI, and a league only produces live
   paper bets when it is explicitly switched on in config/leagues.yaml.
"""
from __future__ import annotations

from collections import defaultdict

import pandas as pd

from sportsedge.betting import liquidity
from sportsedge.ingest import kickoff
from sportsedge.betting.edge import (
    devig_two_way, devig_three_way, edge_fraction, kelly_fraction,
)
from sportsedge.models.live import NFL_MODEL_VERSION, SOCCER_MODEL_VERSION

# Kalshi contracts pay $1, so paying `ask` for one is decimal odds of 1/ask.
MIN_ASK = 0.01

# Version of the PRICING pipeline -- everything between a model's probability
# and a logged bet: the liquidity gate, the de-vig, ask-vs-mid, the edge
# formula. It is versioned separately from the model because a change here
# changes what gets bet and at what price while the model is untouched.
#
# That gap bit once already. The 2026-09-10 liquidity fix voided and re-priced
# the NFL rows because NFL's model version happened to move (v1 -> v2), but
# left 12 EPL rows priced under the superseded gate -- two of them on a
# contract the new gate rejects, carrying the two largest EPL "edges" in the
# ledger (+206% and +64% on a book 7.7% wide). Keyed on model version alone,
# nothing could have caught that.
#
# Bump this whenever pricing behaviour changes, and re-price open bets.
#   p1: pre-2026-09-11. Liquidity gate without the relative-width check.
#   p2: relative-width gate (5%), ask pricing, kickoff-correct CLV cutoff.
PRICING_VERSION = "p2"

# Kalshi's trading fee, as a coefficient on the published quadratic form
# fee = rate * price * (1 - price) per $1 contract.
#
# WHY THIS IS REPORTED AND NOT ENFORCED. Two separate reasons, and both have to
# clear before the edge threshold moves onto the fee-inclusive number:
#
# 1. The rate is unverified. Kalshi's API confirms the SHAPE
#    (fee_type="quadratic_with_maker_fees", fee_multiplier=1 on both
#    KXNFLGAME and KXEPLGAME, checked 2026-09-12) but exposes no coefficient,
#    and the docs page serves no text to a plain fetch. Enforcing a threshold
#    against an unverified constant writes that constant into the permanent
#    bet record.
#
# 2. Changing what gets bet would break a pre-registered prediction that is
#    about to resolve. Run 4 wrote down, before the games: ~30 wins if the
#    model's claimed edges are real, ~22 if the selection audit is right. The
#    70 open bets ARE that test and the week-1 slate starts 2026-09-13.
#    Re-pricing them into a different population the day before they settle
#    would quietly dispose of the one falsifiable commitment this project has
#    made. That is not a cost worth paying for a one-day head start.
#
# So: report it, log it on every new row, leave the open bets alone, and let a
# run after the slate settles decide whether the threshold moves. When it does,
# that is a PRICING_VERSION bump (p3) and an explicit re-pricing, not a quiet
# change of formula.
FEE_RATE_ASSUMPTION = 0.07
FEE_RATE_IS_VERIFIED = False


def _decimal_odds(ask: float) -> float | None:
    if ask is None or ask < MIN_ASK:
        return None
    return 1.0 / ask


def trading_fee(price: float, rate: float = FEE_RATE_ASSUMPTION) -> float:
    """Kalshi's fee on one $1 contract bought at `price`.

    Quadratic in notional, which means regressive in stake: as a fraction of
    the money you put up it is rate * (1 - price), so a 15c longshot pays
    several times what a 75c favourite pays. The bet rule places 88.6% of its
    bets below even money, so it sits at the expensive end of that curve.

    Kalshi rounds the fee up to the cent; modelled continuously here, so the
    real cost is slightly worse than this, never better.
    """
    return rate * price * (1 - price)


def _decimal_odds_after_fee(ask: float, rate: float = FEE_RATE_ASSUMPTION) -> float | None:
    """Decimal odds once the fee is added to the price you pay."""
    if ask is None or ask < MIN_ASK:
        return None
    total = ask + trading_fee(ask, rate)
    if not 0 < total < 1:
        return None
    return 1.0 / total


def _group_events(rows: list[dict]) -> dict[str, dict[str, dict]]:
    """event_ticker -> {selection -> snapshot row}."""
    events: dict[str, dict[str, dict]] = defaultdict(dict)
    for r in rows:
        events[r["event_ticker"]][r["selection"]] = r
    return events


def _market_fair_probs(sides: dict[str, dict], sport: str) -> dict[str, float] | None:
    """De-vig the market's own quotes into a fair probability per side.

    Uses mids for the fair-value baseline (the market's central estimate) even
    though we transact at the ask -- these answer different questions.
    """
    if sport == "nfl":
        if not {"home", "away"} <= sides.keys():
            return None
        p_h = sides["home"].get("implied_prob_mid")
        p_a = sides["away"].get("implied_prob_mid")
        if p_h is None or p_a is None or (p_h + p_a) <= 0:
            return None
        fair_h, fair_a = devig_two_way(p_h, p_a)
        return {"home": fair_h, "away": fair_a}

    if not {"home", "draw", "away"} <= sides.keys():
        return None
    p_h = sides["home"].get("implied_prob_mid")
    p_d = sides["draw"].get("implied_prob_mid")
    p_a = sides["away"].get("implied_prob_mid")
    if None in (p_h, p_d, p_a) or (p_h + p_d + p_a) <= 0:
        return None
    fair_h, fair_d, fair_a = devig_three_way(p_h, p_d, p_a)
    return {"home": fair_h, "draw": fair_d, "away": fair_a}


def recommend_nfl(snapshot_rows: list[dict], model, *, edge_threshold: float = 0.03,
                  kelly_multiplier: float = 0.25, apply_liquidity: bool = True) -> list[dict]:
    fillable = liquidity.partition(snapshot_rows)[0] if apply_liquidity else snapshot_rows
    out = []
    for event_ticker, sides in _group_events(fillable).items():
        fair = _market_fair_probs(sides, "nfl")
        if fair is None:
            continue
        any_row = next(iter(sides.values()))
        p_home = model.win_prob_home(any_row["home_team"], any_row["away_team"])
        model_probs = {"home": p_home, "away": 1 - p_home}

        for selection, row in sides.items():
            if selection not in model_probs:
                continue
            out.extend(_maybe_bet(
                row=row, sport="nfl", league="NFL", selection=selection,
                model_prob=model_probs[selection], fair_prob=fair[selection],
                model_version=NFL_MODEL_VERSION, edge_threshold=edge_threshold,
                kelly_multiplier=kelly_multiplier, event_ticker=event_ticker,
            ))
    return out


def recommend_soccer(snapshot_rows: list[dict], model, calibrator, *,
                     edge_threshold: float = 0.03, kelly_multiplier: float = 0.25,
                     apply_liquidity: bool = True) -> list[dict]:
    fillable = liquidity.partition(snapshot_rows)[0] if apply_liquidity else snapshot_rows
    out = []
    for event_ticker, sides in _group_events(fillable).items():
        fair = _market_fair_probs(sides, "soccer")
        if fair is None:
            continue
        any_row = next(iter(sides.values()))
        diff = model.elo_diff(any_row["home_team"], any_row["away_team"])
        probs = calibrator.predict_proba(diff)
        model_probs = {
            "home": probs.get("H", 0.0),
            "draw": probs.get("D", 0.0),
            "away": probs.get("A", 0.0),
        }

        for selection, row in sides.items():
            if selection not in model_probs:
                continue
            out.extend(_maybe_bet(
                row=row, sport="soccer", league="EPL", selection=selection,
                model_prob=model_probs[selection], fair_prob=fair[selection],
                model_version=SOCCER_MODEL_VERSION, edge_threshold=edge_threshold,
                kelly_multiplier=kelly_multiplier, event_ticker=event_ticker,
            ))
    return out


def _kickoff_iso(sport: str, row: dict) -> str | None:
    """Best-effort true kickoff at recommendation time; None is acceptable."""
    try:
        ko = kickoff.resolve_kickoff(sport, row.get("home_team"), row.get("away_team"),
                                     row.get("expiration_time"))
    except Exception:
        return None
    return None if ko is None else ko.isoformat()


def _maybe_bet(*, row: dict, sport: str, league: str, selection: str, model_prob: float,
               fair_prob: float, model_version: str, edge_threshold: float,
               kelly_multiplier: float, event_ticker: str) -> list[dict]:
    dec = _decimal_odds(row.get("yes_ask"))
    if dec is None:
        return []
    e = edge_fraction(model_prob, dec)
    if e < edge_threshold:
        return []
    return [{
        "sport": sport,
        "league": league,
        "event_ticker": event_ticker,
        "market_ticker": row["market_ticker"],
        "matchup": f"{row['away_team']} @ {row['home_team']}",
        "home_team": row["home_team"],
        "away_team": row["away_team"],
        # Kalshi's expiration (post-game), kept only as a coarse anchor for
        # matching the fixture. `kickoff_utc` is the real thing, and is None
        # until the stats source publishes the fixture -- settlement fills it.
        "expiration_time": row.get("expiration_time"),
        "kickoff_utc": _kickoff_iso(sport, row),
        "market": "moneyline",
        "selection": selection,
        "model_prob": model_prob,
        "market_fair_prob": fair_prob,
        "model_version": model_version,
        "price_ask": row["yes_ask"],
        "market_odds_decimal": dec,
        "pricing_version": PRICING_VERSION,
        "edge_pct": e * 100,   # ledger column is percent; e is a fraction
        # The same edge once Kalshi's fee is added to the price. Reported, not
        # enforced -- see FEE_RATE_ASSUMPTION for why, and expect it to be
        # several points below edge_pct on every longshot.
        "edge_after_fee_pct": (
            None if (dec_f := _decimal_odds_after_fee(row.get("yes_ask"))) is None
            else edge_fraction(model_prob, dec_f) * 100),
        "fee_assumption": FEE_RATE_ASSUMPTION,
        # Divergence from the de-vigged market price is the honest description
        # of what we are claiming: "the market is wrong by this much".
        "disagreement_pp": (model_prob - fair_prob) * 100,
        "kelly_fraction": kelly_fraction(model_prob, dec, kelly_multiplier),
        "book": "kalshi",
    }]


def to_frame(recs: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(recs) if recs else pd.DataFrame()
