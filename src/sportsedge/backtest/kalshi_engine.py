"""What the model would have done at the venue we would actually trade on.

Why this file exists
--------------------
Every ROI number this project has published is model-vs-SPORTSBOOK: nflverse
moneylines and football-data.co.uk bookmaker averages. We would not trade at a
sportsbook. We would trade on Kalshi, an exchange with a two-sided book, a
different cost structure, and a trading fee a sportsbook does not charge. Runs
3 and 4 both carried "build the Kalshi-venue backtest" forward as the highest-
value work left, and `engine.py`'s docstring has pointed at this module since
before it existed.

What this module can and cannot claim
-------------------------------------
It CANNOT be a real Kalshi backtest. Kalshi's public REST API serves the
current board, not a price history reaching back to 2018, and this project has
been capturing snapshots since 2026-09-10. There are three days of exchange
prices and zero settled games. A "Kalshi backtest of 2018-2024" does not exist
and cannot be manufactured.

What it CAN do is substitute a *measured* Kalshi microstructure into the
historical sample, and the substitution is licensed by a measurement rather
than assumed:

  1. `measure_agreement` joins the captured Kalshi board to the sportsbook
     lines on the SAME games and asks whether the two venues make the same
     forecast. If Kalshi's de-vigged mid is the sportsbook's de-vigged fair
     probability, then "the model loses to the de-vigged closing line" is a
     statement about both venues, and the historical sample is usable.
  2. `measure_half_spread` takes the cost of crossing from the captured books
     rather than from a guess.
  3. `KalshiPricer` rebuilds a synthetic exchange book around each historical
     de-vigged fair probability and re-runs the SAME walk-forward loop in
     `engine.py` through it.

So the output is a simulation with a measured venue, not a backtest. It is
labelled `simulated_at_venue` in every result dict so nothing downstream can
quote it as an observed exchange return. The honest reading: it bounds how
much of the model's historical loss is the sportsbook's toll and how much is
the forecast being worse than the market's. Those two have very different
implications and no number this project has produced so far separates them.

The join trap, again
--------------------
The first version of `measure_agreement` joined the Kalshi board to the stats
table on (home_team, away_team). That pair is not unique -- the same fixture
recurs every season -- so 30 Kalshi events fanned out to 131 rows, matching
today's contracts against games from 2020, 2021 and 2024, and reported a
correlation of 0.4572 with a maximum disagreement of 53 percentage points. The
correct join disambiguates by kickoff (`ingest.kickoff.resolve_kickoff`, which
exists for precisely this reason) and gives 28 rows at a correlation of 0.9955.
That is the fifth bug of this exact shape in five runs: a key that was not as
unique as the surrounding code assumed. It is pinned by
`test_agreement_join_is_kickoff_disambiguated`.

Fees
----
Kalshi charges a trading fee; a sportsbook's vig is baked into its quote
instead. The fee's SHAPE is verified from the API -- `series/KXNFLGAME` and
`series/KXEPLGAME` both report `fee_type="quadratic_with_maker_fees"` and
`fee_multiplier=1` (checked 2026-09-12) -- which is the published quadratic
form, fee = rate * price * (1 - price) per $1 contract.

The RATE is not verifiable from the API: no market, series or exchange
endpoint exposes the coefficient, and the documentation page is a JavaScript
shell that serves no text to a plain fetch (the PDF fetch returned HTTP 429).
`DEFAULT_FEE_RATE` below is Kalshi's published taker rate as of training, and
it is NOT confirmed by anything this run could read. So it is a parameter, and
`fee_sensitivity` reports the result across a range including zero, so that no
conclusion drawn here depends on the unverified number. If a future run can
read the schedule, replace the constant and delete this paragraph.

Fees are modelled continuously. Kalshi rounds them up to the cent, which makes
the real cost slightly worse than what is reported here, never better.
"""
from __future__ import annotations

import glob
import math
import os
from dataclasses import dataclass

import pandas as pd

from sportsedge.betting.edge import devig_two_way
from sportsedge.ingest import kickoff
from sportsedge.storage import snapshots

# See the "Fees" note above: shape verified, coefficient not.
DEFAULT_FEE_RATE = 0.07
FEE_RATE_IS_VERIFIED = False

# Fallback half-spread, in dollars, used only when no captured snapshot covers
# a sport. The measured value from the live boards is ~0.005-0.007 for both.
DEFAULT_HALF_SPREAD = 0.006

_SNAPSHOT_DIR = {"nfl": "nfl", "soccer": "soccer"}
_TABLE = {"nfl": "nfl_games", "soccer": "epl_games"}


# -- the venue ----------------------------------------------------------------


@dataclass(frozen=True)
class KalshiPricer:
    """A synthetic Kalshi book built around a market fair probability.

    You buy YES by lifting the ask, so you pay `fair + half_spread`, then the
    exchange takes a quadratic fee on top. Flat-stake ROI downstream works in
    decimal odds, so the whole cost stack collapses into one effective price:

        price_paid = fair + half_spread + fee(price)
        decimal_odds = 1 / price_paid

    Returns None when that price leaves (0, 1) -- an untradeable synthetic
    quote must not silently become a bet.
    """

    half_spread: float = DEFAULT_HALF_SPREAD
    fee_rate: float = DEFAULT_FEE_RATE
    name: str = "kalshi"

    def buy_price(self, fair_prob: float) -> float | None:
        ask = float(fair_prob) + self.half_spread
        if not 0 < ask < 1:
            return None
        total = ask + self.fee_rate * ask * (1 - ask)
        if not 0 < total < 1:
            return None
        return total

    def decimal_odds(self, fair_prob: float, book_decimal_odds: float) -> float | None:
        # book_decimal_odds is deliberately ignored: on an exchange the price
        # is the book's own, and the sportsbook quote enters only through the
        # de-vigged fair probability the caller already derived from it.
        price = self.buy_price(fair_prob)
        return None if price is None else 1 / price


# -- measurement 1: do the two venues make the same forecast? ------------------


def _load_snapshots(sport: str, root: str | None = None) -> pd.DataFrame:
    root = root or str(snapshots.SNAPSHOT_ROOT)
    paths = sorted(glob.glob(os.path.join(root, _SNAPSHOT_DIR[sport], "*.csv")))
    if not paths:
        return pd.DataFrame()
    df = pd.concat([pd.read_csv(p, float_precision="round_trip") for p in paths],
                   ignore_index=True)
    return df


def _latest_book(sport: str, root: str | None = None) -> pd.DataFrame:
    """One row per event: the most recent two-sided quote captured for it."""
    snap = _load_snapshots(sport, root)
    if snap.empty:
        return snap
    snap = snap.assign(_ts=pd.to_datetime(snap["fetched_at"], utc=True, errors="coerce"))
    snap = snap.sort_values("_ts").groupby("market_ticker", as_index=False).last()
    wide = snap.pivot_table(
        index=["event_ticker", "home_team", "away_team", "expiration_time"],
        columns="selection", values=["yes_bid", "yes_ask"], aggfunc="last").reset_index()
    wide.columns = ["_".join([c for c in col if c]).strip() for col in wide.columns.values]
    return wide


def measure_agreement(sport: str = "nfl", root: str | None = None) -> dict:
    """Kalshi's de-vigged mid vs the sportsbook's de-vigged fair, same games.

    This is the measurement that licenses running the historical sample
    through `KalshiPricer` at all. Two-way only, so NFL: the EPL board is
    three-way and the draw contract is thin enough that the same comparison
    would be measuring the liquidity gate rather than the venue.
    """
    if sport != "nfl":
        raise ValueError("agreement is measured two-way; only 'nfl' is supported")

    board = _latest_book(sport, root)
    if board.empty:
        return {"n": 0, "note": "no captured snapshots"}

    sched = snapshots.read_processed(_TABLE[sport])
    sched = sched.assign(_kick=pd.to_datetime(sched["kickoff_utc"], utc=True, errors="coerce"))

    rows, unmatched, no_line = [], 0, 0
    for _, r in board.iterrows():
        # Kickoff-disambiguated, NOT a bare (home, away) join. See module note.
        ko = kickoff.resolve_kickoff(sport, r["home_team"], r["away_team"],
                                     near=r["expiration_time"])
        if ko is None:
            unmatched += 1
            continue
        hit = sched[(sched["home_team"] == r["home_team"])
                    & (sched["away_team"] == r["away_team"])
                    & (sched["_kick"] == pd.Timestamp(ko))]
        if hit.empty:
            unmatched += 1
            continue
        g = hit.iloc[0]
        if pd.isna(g["home_odds_decimal"]) or pd.isna(g["away_odds_decimal"]):
            no_line += 1
            continue
        quotes = [r.get("yes_ask_home"), r.get("yes_ask_away"),
                  r.get("yes_bid_home"), r.get("yes_bid_away")]
        if any(q is None or pd.isna(q) for q in quotes):
            no_line += 1
            continue
        ask_h, ask_a, bid_h, bid_a = (float(q) for q in quotes)

        k_fair_h, _ = devig_two_way((ask_h + bid_h) / 2, (ask_a + bid_a) / 2)
        imp_h, imp_a = 1 / g["home_odds_decimal"], 1 / g["away_odds_decimal"]
        b_fair_h, _ = devig_two_way(imp_h, imp_a)

        rows.append({"game_id": g["game_id"], "kalshi_fair_home": k_fair_h,
                     "book_fair_home": b_fair_h, "diff": k_fair_h - b_fair_h,
                     "kalshi_overround_ask": (ask_h + ask_a) - 1,
                     "book_overround": (imp_h + imp_a) - 1})

    if not rows:
        return {"n": 0, "unmatched_events": unmatched, "matched_without_book_line": no_line}

    d = pd.DataFrame(rows)
    return {
        "n": len(d),
        "unmatched_events": unmatched,
        "matched_without_book_line": no_line,
        "correlation": float(d["kalshi_fair_home"].corr(d["book_fair_home"])),
        "mean_diff": float(d["diff"].mean()),
        "mean_abs_diff": float(d["diff"].abs().mean()),
        "p90_abs_diff": float(d["diff"].abs().quantile(0.9)),
        "max_abs_diff": float(d["diff"].abs().max()),
        "kalshi_overround_at_ask": float(d["kalshi_overround_ask"].mean()),
        "book_overround": float(d["book_overround"].mean()),
        "venues_agree": bool(d["diff"].abs().mean() < 0.02
                             and d["kalshi_fair_home"].corr(d["book_fair_home"]) > 0.95),
        "detail": d,
    }


# -- measurement 2: what does crossing actually cost? -------------------------


def measure_half_spread(sport: str = "nfl", root: str | None = None) -> dict:
    """Empirical half-spread of the captured Kalshi books, in dollars.

    Reported in dollars rather than as a fraction of price because that is how
    it behaves: measured on the live boards the half-spread is flat at roughly
    half a cent across every price bucket, which makes it cheap on favourites
    and punitively expensive in relative terms on longshots. A single relative
    number would hide that.
    """
    snap = _load_snapshots(sport, root)
    if snap.empty:
        return {"n": 0, "median": DEFAULT_HALF_SPREAD, "mean": DEFAULT_HALF_SPREAD,
                "note": "no captured snapshots; using the default"}
    snap = snap[(snap["yes_bid"] > 0) & (snap["yes_ask"] > 0)
                & (snap["yes_ask"] > snap["yes_bid"])]
    if snap.empty:
        return {"n": 0, "median": DEFAULT_HALF_SPREAD, "mean": DEFAULT_HALF_SPREAD,
                "note": "no two-sided quotes; using the default"}
    half = (snap["yes_ask"] - snap["yes_bid"]) / 2
    mid = (snap["yes_ask"] + snap["yes_bid"]) / 2
    buckets = pd.cut(mid, [0, 0.1, 0.2, 0.35, 0.5, 0.65, 0.8, 0.9, 1.0])
    by_bucket = [
        {"bucket": str(b), "n": int(grp.size), "half_spread_median": float(grp.median()),
         "relative_median": float((grp / mid[grp.index]).median())}
        for b, grp in half.groupby(buckets, observed=True)
    ]
    return {
        "n": int(half.size),
        "mean": float(half.mean()),
        "median": float(half.median()),
        "p90": float(half.quantile(0.9)),
        "by_price_bucket": by_bucket,
    }


# -- the simulation -----------------------------------------------------------


def venue_from_snapshots(sport: str = "nfl", fee_rate: float = DEFAULT_FEE_RATE,
                         root: str | None = None) -> KalshiPricer:
    """A `KalshiPricer` whose spread comes from the captured books, not a guess."""
    measured = measure_half_spread(sport, root)
    return KalshiPricer(half_spread=measured.get("median") or DEFAULT_HALF_SPREAD,
                        fee_rate=fee_rate)


def compare_venues(backtest_fn, *args, sport: str = "nfl",
                   fee_rate: float = DEFAULT_FEE_RATE, root: str | None = None,
                   **kwargs) -> dict:
    """Run one backtest at both venues and report the delta.

    `backtest_fn` is `engine.backtest_nfl` or `engine.backtest_soccer`; every
    other argument is forwarded untouched, so the two runs differ in the
    pricer and nothing else.
    """
    venue = venue_from_snapshots(sport, fee_rate=fee_rate, root=root)
    book = backtest_fn(*args, **kwargs)
    exch = backtest_fn(*args, pricer=venue, **kwargs)

    book_roi, exch_roi = book["roi"], exch["roi"]
    return {
        "simulated_at_venue": True,
        "half_spread": venue.half_spread,
        "fee_rate": venue.fee_rate,
        "fee_rate_verified": FEE_RATE_IS_VERIFIED,
        "log_loss": book["log_loss"],          # the forecast is venue-independent
        "sportsbook": book_roi,
        "kalshi_simulated": exch_roi,
        "roi_delta_pp": (None if book_roi["roi_pct"] is None or exch_roi["roi_pct"] is None
                         else exch_roi["roi_pct"] - book_roi["roi_pct"]),
        "bets_delta": exch_roi["n_bets"] - book_roi["n_bets"],
    }


def fee_sensitivity(backtest_fn, *args, sport: str = "nfl",
                    fee_rates=(0.0, 0.01, 0.035, 0.07, 0.10),
                    root: str | None = None, **kwargs) -> pd.DataFrame:
    """ROI across a range of fee rates, including zero.

    The point is that no conclusion should rest on `DEFAULT_FEE_RATE`, which
    this run could not verify. If the sign of the result is the same at fee=0
    and fee=0.10, the unverified coefficient does not matter.
    """
    measured = measure_half_spread(sport, root)
    half = measured.get("median") or DEFAULT_HALF_SPREAD
    out = []
    for rate in fee_rates:
        res = backtest_fn(*args, pricer=KalshiPricer(half_spread=half, fee_rate=rate), **kwargs)
        roi = res["roi"]
        out.append({"fee_rate": rate, "n_bets": roi["n_bets"], "roi_pct": roi["roi_pct"],
                    "win_rate": roi["win_rate"],
                    "roi_ci_lo": roi["roi_ci95_pct"][0] if roi["roi_ci95_pct"] else None,
                    "roi_ci_hi": roi["roi_ci95_pct"][1] if roi["roi_ci95_pct"] else None,
                    "significant": roi["significant_at_95"]})
    return pd.DataFrame(out)


def breakeven_edge(fair_prob: float, half_spread: float = DEFAULT_HALF_SPREAD,
                   fee_rate: float = DEFAULT_FEE_RATE) -> float | None:
    """How far above fair the model must be, in probability points, to break even.

    This is the venue's toll expressed in the units the edge threshold uses.
    `config/leagues.yaml` sets `edge_threshold_pct: 3.0` for both leagues and
    both venues, which is a number chosen before anyone measured what either
    venue costs.
    """
    price = KalshiPricer(half_spread, fee_rate).buy_price(fair_prob)
    if price is None:
        return None
    return price - fair_prob


def summarize(sport: str = "nfl", root: str | None = None) -> dict:
    """Everything measurable about the venue, without touching a backtest."""
    agree = measure_agreement("nfl", root) if sport == "nfl" else {"n": 0, "note": "two-way only"}
    agree = {k: v for k, v in agree.items() if k != "detail"}
    spread = measure_half_spread(sport, root)
    half = spread.get("median") or DEFAULT_HALF_SPREAD
    return {
        "sport": sport,
        "agreement": agree,
        "half_spread": spread,
        "breakeven_edge_pp_by_price": {
            f"{p:.2f}": (None if (b := breakeven_edge(p, half)) is None else round(b * 100, 3))
            for p in (0.10, 0.25, 0.50, 0.75, 0.90)
        },
        "fee_rate_verified": FEE_RATE_IS_VERIFIED,
    }
