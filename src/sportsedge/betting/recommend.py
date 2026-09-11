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


def _decimal_odds(ask: float) -> float | None:
    if ask is None or ask < MIN_ASK:
        return None
    return 1.0 / ask


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
        # Divergence from the de-vigged market price is the honest description
        # of what we are claiming: "the market is wrong by this much".
        "disagreement_pp": (model_prob - fair_prob) * 100,
        "kelly_fraction": kelly_fraction(model_prob, dec, kelly_multiplier),
        "book": "kalshi",
    }]


def to_frame(recs: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(recs) if recs else pd.DataFrame()
