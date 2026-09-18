"""Does capping the claimed edge help? The last untested lever in the bet rule.

WHY THIS EXISTS
---------------
The most consistently replicating observation in this project is that the
model's overstatement grows with the size of its own claim. Run 4 found it in
backtest (the selection audit: conditional on being bet, Elo overstates by
13.7 points); runs 9, 11 and 17 found it in the realized ledger, splitting the
settled rows at the median claimed edge and watching the high half fall
further below its claim every time (-0.55/-2.89 wins at n=11/12, -1.33/-3.37
at n=13/13).

The obvious inference is that the rule should stop taking its own biggest
claims -- an UPPER cap on `edge_frac` to sit above the 3% floor. That
inference has never been tested, and it is not covered by the two arguments
that retired everything else:

* Run 11's AUC bound retires any monotone transform of the forecast. A cap is
  not a transform of the forecast at all -- the probabilities are untouched
  and the ranking is identical. It changes which subset gets bet.
* Run 11 did list "threshold moves" as retired, but that argument is about
  closing the DISCRIMINATION gap, which a selection rule cannot do. It says
  nothing about whether a bounded subset of the model's bets is profitable,
  which is a different question with a different answer available.

THE GATE, FOR A SELECTION RULE
------------------------------
`config/leagues.yaml` says the baseline is the de-vigged closing line, never a
previous version of the model. For a rule that changes *which* sides get bet
rather than what they are priced at, that cashes out as ROI at DE-VIGGED FAIR
ODDS: stake $1 per selected side and settle it at `1 / fair_market_prob`.

    fair ROI == 0    the selection knows exactly what the closing line knows
    fair ROI  > 0    the selection carries information the closing line lacks

Book ROI is reported beside it because that is what would actually be earned,
but it cannot be the gate: it is fair ROI minus the vig, so it is negative for
a rule with no information at all, and a rule that merely loses less vig has
discovered nothing.

THE TWO GAPS, WHICH ARE NOT THE SAME NUMBER
-------------------------------------------
Every band reports both, because conflating them is the trap this module was
written to walk into:

    claim_gap_pp   = realized - claimed        the model vs its own claim
    market_gap_pp  = realized - fair_market    the model vs the closing line

The replicating ledger result is about `claim_gap_pp`. Only `market_gap_pp`
pays. A cap can only help if the second one orders with claimed edge, and
whether it does is an empirical question this module asks directly
(`market_gap_trend`) rather than assuming from the first.

DISCIPLINE
----------
Caps are selected on `selection_seasons` and the pick is confirmed on
`holdout_seasons`, which selection never touches -- the protocol run 17 used
for `season_regression`, for the same reason: the canonical 2021-2024 window
has been looked at by every other sweep in the repo.

A band must hold at least `MIN_SELECTION_BETS` bets in the selection phase to
be eligible. This is pre-specified, not fitted, and it exists because the
tightest caps put 15-30 bets in a band and post spectacular ROIs with
intervals ninety points wide. Selecting a betting rule on 29 bets is how this
project would manufacture an edge out of nothing, and the eligibility floor is
cheaper than the journal entry retracting it.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from sportsedge.backtest.metrics import simulate_flat_stake_roi

# Cumulative bands [floor, cap). `inf` is the incumbent rule -- no cap at all --
# and is always present so every table carries its own do-nothing baseline.
DEFAULT_CAPS: tuple[float, ...] = (0.05, 0.10, 0.15, 0.20, 0.25, 0.30,
                                   0.40, 0.50, 0.75, 1.00, math.inf)
DEFAULT_FLOOR = 0.03
MIN_SELECTION_BETS = 100

DEFAULT_SELECTION_SEASONS = (2021, 2022, 2023)
DEFAULT_HOLDOUT_SEASONS = (2024,)
DEFAULT_BURN_IN = (2018, 2019, 2020)


def _fair_bets(sub: pd.DataFrame) -> list[dict]:
    """The same wagers, settled at the de-vigged closing price."""
    return [{"model_prob": float(p), "decimal_odds": 1.0 / float(f), "won": bool(w)}
            for p, f, w in zip(sub["model_prob"], sub["fair_market_prob"], sub["won"])]


def _book_bets(sub: pd.DataFrame) -> list[dict]:
    return [{"model_prob": float(p), "decimal_odds": float(o), "won": bool(w)}
            for p, o, w in zip(sub["model_prob"], sub["decimal_odds"], sub["won"])]


def band_stats(sides: pd.DataFrame, *, floor: float = DEFAULT_FLOOR,
               cap: float = math.inf) -> dict:
    """One cumulative band [floor, cap) of claimed edge.

    Both ROIs come from `simulate_flat_stake_roi`, which is the function every
    other ROI in this repo is computed with -- the fair-odds variant is the
    same wagers with the price swapped, not a second implementation of the
    arithmetic.
    """
    sub = sides[(sides["edge_frac"] >= floor) & (sides["edge_frac"] < cap)]
    if sub.empty:
        return {"cap": cap, "n_bets": 0, "book_roi_pct": None, "fair_roi_pct": None,
                "fair_ci95_pct": None, "beats_market": False}

    book = simulate_flat_stake_roi(_book_bets(sub))
    fair = simulate_flat_stake_roi(_fair_bets(sub))
    ci = fair["roi_ci95_pct"] or (None, None)
    realized = float(sub["won"].mean())
    return {
        "cap": cap,
        "n_bets": int(len(sub)),
        "n_games": int(sub["game_id"].nunique()),
        "mean_claimed_edge_pct": float(sub["edge_frac"].mean()) * 100,
        "claimed": float(sub["model_prob"].mean()),
        "realized": realized,
        "market": float(sub["fair_market_prob"].mean()),
        # The model against its own claim. This is the number the ledger's
        # high-edge/low-edge split measures, and it is not the one that pays.
        "claim_gap_pp": (realized - float(sub["model_prob"].mean())) * 100,
        # The model against the closing line. This one pays.
        "market_gap_pp": (realized - float(sub["fair_market_prob"].mean())) * 100,
        "book_roi_pct": book["roi_pct"],
        "book_ci95_pct": list(book["roi_ci95_pct"]) if book["roi_ci95_pct"] else None,
        "fair_roi_pct": fair["roi_pct"],
        "fair_ci95_pct": list(ci) if ci[0] is not None else None,
        # The gate: beating the de-vigged closing line means an interval that
        # sits entirely above zero, not a positive point estimate.
        "beats_market": bool(ci[0] is not None and ci[0] > 0),
    }


def market_gap_trend(sides: pd.DataFrame, *, floor: float = DEFAULT_FLOOR,
                     n_boot: int = 2000, seed: int = 0) -> dict:
    """Does error-against-the-market order with claimed edge? OLS slope + CI.

    Regresses `won - fair_market_prob` on `edge_frac` over the flagged sides.
    A cap can only pay if this slope is negative: that is what "the bigger the
    claim, the worse the bet" would have to mean in the currency that settles.

    Resampled over GAMES, not sides, matching `selection.bootstrap_ll_delta` --
    a game's two sides are one observation, and treating them as two would
    halve an interval that has not earned it.
    """
    sub = sides[sides["edge_frac"] >= floor]
    if len(sub) < 3:
        return {"n": int(len(sub)), "slope_pp_per_10pp": None, "ci95": None,
                "orders_with_edge": None}

    x = sub["edge_frac"].to_numpy(dtype=float)
    y = (sub["won"].to_numpy(dtype=float) - sub["fair_market_prob"].to_numpy(dtype=float))
    games = sub["game_id"].to_numpy()
    order = pd.unique(games)
    idx = [np.flatnonzero(games == g) for g in order]

    def slope(xs, ys):
        if len(xs) < 2 or np.ptp(xs) == 0:
            return float("nan")
        return float(np.polyfit(xs, ys, 1)[0])

    point = slope(x, y)
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, len(idx), size=(n_boot, len(idx)))
    boots = []
    for row in draws:
        sel = np.concatenate([idx[i] for i in row])
        s = slope(x[sel], y[sel])
        if s == s:
            boots.append(s)
    lo, hi = (float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))) \
        if boots else (float("nan"), float("nan"))

    # Reported per 10 percentage points of claimed edge, which is the scale a
    # cap would actually be set on. A raw per-unit slope reads as a big number
    # for an effect nobody would notice.
    return {
        "n": int(len(sub)),
        "n_games": int(len(order)),
        "slope_pp_per_10pp": point * 100 / 10,
        "ci95": [lo * 100 / 10, hi * 100 / 10],
        # True only when the interval sits entirely below zero: bigger claims
        # really are worse bets against the market.
        "orders_with_edge": bool(hi < 0),
    }


def median_split(sides: pd.DataFrame, *, floor: float = DEFAULT_FLOOR) -> dict:
    """The ledger's own headline split, run on the backtest, and decomposed.

    Runs 9, 11 and 17 split the settled rows at the median claimed edge and
    report `realized - claimed` for each half, which separates and keeps
    separating. Part of that separation is an IDENTITY, not a measurement:

        claim_gap - market_gap  ==  market - claimed

    and `claimed - market` is, at de-vigged odds, exactly the claimed edge
    scaled by the market price. So the high half is GUARANTEED a larger
    claim gap than the low half whatever the outcomes are -- that is what
    sorting on claimed edge does. The only part carrying information is
    `market_gap`, the model against the price.

    `mechanical_share` is how much of the headline separation comes from the
    identity. The rest is empirical and is the thing worth replicating.
    """
    sub = sides[sides["edge_frac"] >= floor]
    if len(sub) < 2:
        return {"n": int(len(sub))}
    med = float(sub["edge_frac"].median())
    halves = {"low": sub[sub["edge_frac"] <= med], "high": sub[sub["edge_frac"] > med]}

    out = {"n": int(len(sub)), "median_claimed_edge_pct": med * 100}
    for name, h in halves.items():
        if h.empty:
            out[name] = {"n": 0}
            continue
        claimed, market = float(h["model_prob"].mean()), float(h["fair_market_prob"].mean())
        realized = float(h["won"].mean())
        fair = simulate_flat_stake_roi(_fair_bets(h))
        out[name] = {
            "n": int(len(h)),
            "mean_claimed_edge_pct": float(h["edge_frac"].mean()) * 100,
            "claim_gap_pp": (realized - claimed) * 100,
            "market_gap_pp": (realized - market) * 100,
            "identity_pp": (market - claimed) * 100,
            "fair_roi_pct": fair["roi_pct"],
        }
    if out["low"].get("n") and out["high"].get("n"):
        sep = out["low"]["claim_gap_pp"] - out["high"]["claim_gap_pp"]
        mech = out["low"]["identity_pp"] - out["high"]["identity_pp"]
        out["separation_pp"] = sep
        out["mechanical_pp"] = mech
        out["empirical_pp"] = sep - mech
        out["mechanical_share"] = mech / sep if sep else None
    return out


SETTLED_STATUSES = ("won", "lost")


def sides_from_ledger(ledger: pd.DataFrame) -> pd.DataFrame:
    """The settled ledger, in the same shape as a backtest `sides` frame.

    So `median_split` can be run on the real bets and on the backtest with one
    function rather than two derivations that might differ. The ledger is what
    runs 9, 11 and 17 measured; the backtest is the same question at 27x the
    sample, and the point of this adapter is that the two are then answering
    it in identical arithmetic.

    Pushes are dropped rather than scored as half a win: there are none in the
    book, and inventing a convention for a case that has never occurred is how
    a number nobody checked gets into a journal entry.
    """
    df = ledger[ledger["status"].isin(SETTLED_STATUSES)].copy()
    return pd.DataFrame({
        "game_id": df["bet_id"].astype(str),
        "model_prob": df["model_prob"].astype(float),
        "fair_market_prob": df["market_fair_prob"].astype(float),
        "decimal_odds": df["market_odds_decimal"].astype(float),
        "won": df["status"] == "won",
        # The ledger stores edge in PERCENT and everything here is a fraction.
        # See betting/edge.py on why that boundary is converted and never
        # papered over.
        "edge_frac": df["edge_pct"].astype(float) / 100.0,
    }).reset_index(drop=True)


def sweep_edge_cap(selection_sides: pd.DataFrame, holdout_sides: pd.DataFrame, *,
                   caps=DEFAULT_CAPS, floor: float = DEFAULT_FLOOR,
                   min_selection_bets: int = MIN_SELECTION_BETS,
                   n_boot: int = 2000, seed: int = 0) -> dict:
    """Select a cap on one window, confirm it on another it never saw."""
    selection = [band_stats(selection_sides, floor=floor, cap=c) for c in caps]
    holdout = [band_stats(holdout_sides, floor=floor, cap=c) for c in caps]

    eligible = [r for r in selection
                if r["n_bets"] >= min_selection_bets and math.isfinite(r["cap"])]
    incumbent_sel = next(r for r in selection if math.isinf(r["cap"]))
    incumbent_hold = next(r for r in holdout if math.isinf(r["cap"]))

    # Argmax over fair ROI among eligible finite caps. The incumbent is scored
    # separately rather than entered in this contest, so "the best cap" always
    # means "the best ALTERNATIVE to doing nothing" and can never be the
    # do-nothing row wearing a different label.
    pick = max(eligible, key=lambda r: r["fair_roi_pct"]) if eligible else None
    pick_hold = (next(r for r in holdout if r["cap"] == pick["cap"])
                 if pick is not None else None)

    reasons = []
    if pick is None:
        reasons.append(f"no cap holds {min_selection_bets}+ selection bets")
    else:
        if pick["fair_roi_pct"] <= incumbent_sel["fair_roi_pct"]:
            reasons.append("best eligible cap does not beat the uncapped rule in selection")
        if not pick_hold["beats_market"]:
            reasons.append("pick does not beat the de-vigged closing line out-of-sample")
        if pick_hold["fair_roi_pct"] is None or \
                pick_hold["fair_roi_pct"] <= incumbent_hold["fair_roi_pct"]:
            reasons.append("pick ranks at or below the uncapped rule out-of-sample")

    return {
        "floor": floor,
        "min_selection_bets": min_selection_bets,
        "selection": selection,
        "holdout": holdout,
        "incumbent": {"selection": incumbent_sel, "holdout": incumbent_hold},
        "pick": pick,
        "pick_holdout": pick_hold,
        "n_eligible": len(eligible),
        "beats_market_selection": sum(1 for r in selection if r["beats_market"]),
        "beats_market_holdout": sum(1 for r in holdout if r["beats_market"]),
        "market_gap_trend": {
            "selection": market_gap_trend(selection_sides, floor=floor,
                                          n_boot=n_boot, seed=seed),
            "holdout": market_gap_trend(holdout_sides, floor=floor,
                                        n_boot=n_boot, seed=seed),
        },
        "median_split": {
            "selection": median_split(selection_sides, floor=floor),
            "holdout": median_split(holdout_sides, floor=floor),
        },
        # Adoption requires all three: beat the incumbent where it was chosen,
        # beat the MARKET where it was confirmed, and still beat the incumbent
        # there. Run 12's trap was a change that won on the selection metric
        # and ranked worse out of sample; the third clause is what catches it.
        "adopt": bool(pick is not None and not reasons),
        "reasons": reasons,
    }
