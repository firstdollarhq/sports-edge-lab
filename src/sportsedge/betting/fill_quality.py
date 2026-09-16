"""Does the liquidity gate predict anything about the quote it rejects?

Why this exists
---------------
`betting/liquidity.py` has gated every price this project has ever recommended,
and its own docstring calls its thresholds "deliberately conservative defaults,
not tuned values". They have never been checked against anything. A filter
nobody has validated is indistinguishable from a filter that removes rows at
random, except that it is more expensive: on the 2026-09-16 board it rejected
17 of 47 NFL contracts and 3 of 27 EPL ones.

The gate claims two jobs, in `liquidity.py`'s own words: a wide relative book
means "the de-vigged fair probability we measure disagreement against is
unreliable, and size is unlikely to fill near the touch."

What this module can and cannot test
------------------------------------
**It cannot test fill quality.** This project has never placed an order, so
there is no realized fill to compare a quote against, and there never will be
while `live_enabled` is false. Any claim here about "what you would have paid"
is a claim about a price nobody lifted.

**It can test quote persistence**, which is the observable shadow of the first
job: is the ask you were quoted still there at the next capture, or has it
moved against you? The 30-minute cron gives ~30 pre-kickoff captures per NFL
contract, so this is the one liquidity question the committed snapshots can
actually answer.

So the measured quantity is deliberately narrow:

    P(the ask rises by at least one tick before the next capture)

taken over consecutive captures of the same contract, 20-75 minutes apart.

Three things that decide whether the answer means anything
----------------------------------------------------------
1. **Kickoff comes from the stats source.** Reused from `line_movement.
   collect_quotes` rather than re-derived -- run 13 re-derived it in an ad-hoc
   script, filed in-play quotes as pre-game ones, and got a mean move eight
   times too large from contracts settling to 0.99.

2. **The comparison must be stratified by time-to-kickoff.** The gate turns out
   to reject almost nothing inside T-72h (1 row of 1,964 across both sports),
   because volume and depth build as a game approaches. So a raw pass/fail
   comparison is mostly a comparison of early boards against late ones, and
   early boards move more for reasons that have nothing to do with the gate.

3. **The bootstrap resamples contracts, not quotes.** ~30 captures of one
   contract are not 30 independent observations of anything. Clustering on
   `market_ticker` roughly triples the width of the NFL interval and is the
   difference between a defensible claim and an arithmetic artifact.

One tick is 0.01: Kalshi quotes whole cents, so a sub-tick mean is a number
about the venue's price grid and not about the market.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from sportsedge.betting import liquidity
from sportsedge.betting import line_movement
from sportsedge.betting.edge import spread_cost_fraction

# One cent on a $1 contract -- the smallest change Kalshi can express.
TICK = 0.01

# Wide enough to keep the far end of the NFL board, which opens ~290h out.
# See the note in `line_movement.collect_quotes`: quotes outside the widest
# edge are dropped, silently.
_ALL_HOURS = (1e9,)

# Consecutive captures are nominally 30 minutes apart. The window tolerates
# GitHub's scheduling slop (CLAUDE.md: "*/30 means about every 30-45 minutes")
# while refusing to pair across the 04:00-10:00Z capture blackout, which would
# compare quotes six hours apart and call it persistence.
MIN_GAP_MIN = 20.0
MAX_GAP_MIN = 75.0

# Strata for the pass/fail comparison. Fine enough that "the gate rejects early
# boards" cannot masquerade as "the gate rejects bad quotes".
DEFAULT_STRATA = (0.0, 72.0, 120.0, 168.0, 216.0, 264.0, 1e9)

# The book columns the gate needs, beyond the ask `collect_quotes` already
# carries. Names match `storage.snapshots.COLUMNS`.
_BOOK_COLS = ("yes_bid", "implied_prob_mid", "yes_ask_size", "volume")

# Below these, a cohort gets arm counts but no confidence interval. Both are
# judgement calls rather than derived numbers: three contracts is the fewest
# from which a cluster bootstrap can draw a sample that is not simply the
# original, and twenty quotes is a shade under one contract's worth of captures
# over a single overnight window.
MIN_ARM_QUOTES = 20
MIN_ARM_CONTRACTS = 3


def collect_pairs(sport: str, *, min_gap_min: float = MIN_GAP_MIN,
                  max_gap_min: float = MAX_GAP_MIN) -> pd.DataFrame:
    """Consecutive pre-kickoff capture pairs for each contract, gate verdict attached.

    One row per (contract, capture) that has a usable successor. `adverse_tick`
    is the outcome: did the ask rise by at least one tick by the next capture?
    """
    q = line_movement.collect_quotes(sport, buckets=_ALL_HOURS,
                                     keep_cols=_BOOK_COLS)
    if q.empty:
        return pd.DataFrame()

    q = q.sort_values(["market_ticker", "fetched_at"]).copy()

    verdicts = [liquidity.check(rec) for rec in q.to_dict("records")]
    q["gate_ok"] = [v.ok for v in verdicts]
    q["reject_reason"] = [v.reason for v in verdicts]
    q["spread_cost"] = [
        spread_cost_fraction(b, a) if pd.notna(b) and pd.notna(a) else np.nan
        for b, a in zip(q["yes_bid"], q["yes_ask"])
    ]

    grp = q.groupby("market_ticker")
    q["next_ask"] = grp["yes_ask"].shift(-1)
    q["gap_min"] = (grp["fetched_at"].shift(-1) - q["fetched_at"]).dt.total_seconds() / 60.0

    pairs = q[q["gap_min"].between(min_gap_min, max_gap_min)].copy()
    if pairs.empty:
        return pairs

    # Counted in WHOLE TICKS, not by comparing a float difference against
    # 0.01. `0.41 - 0.40` is 0.009999999999999953 in binary floating point, so
    # `delta >= TICK` is False for an exact one-tick rise -- the single most
    # common move on a venue that quotes whole cents. The draft of this module
    # did exactly that and under-counted adverse moves everywhere, unevenly,
    # because whether a one-cent difference lands above or below 0.01 depends
    # on the price: 0.33 - 0.32 rounds up and registers, 0.41 - 0.40 rounds
    # down and vanishes. Prices are integers on this venue and are compared
    # as integers here.
    pairs["move_ticks"] = ((pairs["next_ask"] - pairs["yes_ask"]) / TICK).round()
    pairs["adverse_tick"] = (pairs["move_ticks"] >= 1).astype(float)
    pairs["favourable_tick"] = (pairs["move_ticks"] <= -1).astype(float)
    pairs["unmoved"] = (pairs["move_ticks"] == 0).astype(float)
    return pairs


def _cluster_ci(df: pd.DataFrame, *, value: str, group: str,
                cluster: str = "market_ticker", draws: int = 20000,
                seed: int = 17) -> list[float] | None:
    """Percentile CI for mean(value | group) - mean(value | ~group), resampling clusters.

    Resamples whole contracts with replacement and recomputes the difference of
    the two pooled means. Draws in which either arm comes out empty are
    discarded rather than imputed; if too few survive, the answer is None and
    the caller reports the cohort as underpowered instead of printing a number.
    """
    if df.empty or df[group].nunique() < 2:
        return None
    rng = np.random.default_rng(seed)
    agg = df.groupby(cluster).apply(
        lambda d: pd.Series({
            "sum_a": d.loc[d[group], value].sum(),
            "n_a": int(d[group].sum()),
            "sum_b": d.loc[~d[group], value].sum(),
            "n_b": int((~d[group]).sum()),
        }), include_groups=False)
    k = len(agg)
    if k < 2:
        return None
    sum_a, n_a = agg["sum_a"].to_numpy(), agg["n_a"].to_numpy()
    sum_b, n_b = agg["sum_b"].to_numpy(), agg["n_b"].to_numpy()

    pick = rng.integers(0, k, (draws, k))
    tot_a, cnt_a = sum_a[pick].sum(1), n_a[pick].sum(1)
    tot_b, cnt_b = sum_b[pick].sum(1), n_b[pick].sum(1)
    usable = (cnt_a > 0) & (cnt_b > 0)
    if usable.sum() < draws * 0.5:
        return None
    diff = tot_a[usable] / cnt_a[usable] - tot_b[usable] / cnt_b[usable]
    return [round(float(x), 4) for x in np.percentile(diff, [2.5, 97.5])]


def _arm(df: pd.DataFrame) -> dict:
    return {
        "n_quotes": int(len(df)),
        "n_contracts": int(df["market_ticker"].nunique()) if len(df) else 0,
        "p_adverse_tick": round(float(df["adverse_tick"].mean()), 4) if len(df) else None,
        "p_favourable_tick": round(float(df["favourable_tick"].mean()), 4) if len(df) else None,
        "share_unmoved": round(float(df["unmoved"].mean()), 4) if len(df) else None,
        "mean_ask": round(float(df["yes_ask"].mean()), 4) if len(df) else None,
    }


def _compare(df: pd.DataFrame, flag: str) -> dict:
    a, b = df[df[flag]], df[~df[flag]]
    out = {"rejected": _arm(a), "accepted": _arm(b)}
    if not (len(a) and len(b)):
        return out
    out["diff_p_adverse_tick"] = round(
        float(a["adverse_tick"].mean() - b["adverse_tick"].mean()), 4)

    # A cluster bootstrap over one or two contracts resamples the same handful
    # of quotes and returns a tight-looking interval around whatever those
    # quotes happened to do. The first draft of this module published exactly
    # that -- a 95% CI of [-0.061, -0.025] on an arm of ONE contract, and
    # [0.000, 0.250] on an arm of eight quotes -- which reads as a result and
    # is a restatement of the input. Underpowered cohorts are reported as
    # underpowered; the arm counts stay visible so the reader can see why.
    if min(len(a), len(b)) < MIN_ARM_QUOTES or min(
            a["market_ticker"].nunique(), b["market_ticker"].nunique()) < MIN_ARM_CONTRACTS:
        out["diff_ci_cluster"] = None
        out["underpowered"] = (
            f"an arm has < {MIN_ARM_QUOTES} quotes or < {MIN_ARM_CONTRACTS} "
            f"contracts; no interval reported")
        return out
    out["diff_ci_cluster"] = _cluster_ci(df, value="adverse_tick", group=flag)
    return out


def summarize(sport: str, *, strata=DEFAULT_STRATA) -> dict:
    """Does a gate rejection predict a quote that moves against you?

    Reports the full gate and, separately, the 5% relative-width rule in
    isolation -- that rule is the one `liquidity.py` reasons about at length and
    the one run 13 named as unvalidated, and it is evaluated only on rows that
    pass every other rule so its own contribution is not credited with theirs.
    """
    pairs = collect_pairs(sport)
    if pairs.empty:
        return {"sport": sport, "pairs": 0,
                "note": "no consecutive capture pairs in the snapshot history"}

    pairs["rejected"] = ~pairs["gate_ok"]

    by_stratum = {}
    labels = pd.cut(pairs["hours_to_kickoff"], list(strata))
    for interval, grp in pairs.groupby(labels, observed=True):
        lo, hi = interval.left, interval.right
        label = f"T-{lo:g}h..T-{hi:g}h" if hi < 1e8 else f"T-{lo:g}h+"
        by_stratum[label] = _compare(grp, "rejected")

    # The 5% relative-width rule alone: rows that clear every other check, split
    # on whether crossing the spread costs more than MAX_SPREAD_COST.
    isolated = pairs[pairs["gate_ok"]
                     | pairs["reject_reason"].str.startswith("crossing")].copy()
    isolated["rejected"] = isolated["spread_cost"] > liquidity.MAX_SPREAD_COST

    return {
        "sport": sport,
        "pairs": int(len(pairs)),
        "contracts": int(pairs["market_ticker"].nunique()),
        "tick": TICK,
        "gap_window_min": [MIN_GAP_MIN, MAX_GAP_MIN],
        "note": ("P(ask rises >= 1 tick before the next capture), rejected vs "
                 "accepted by the liquidity gate. This is quote PERSISTENCE, "
                 "not realized fill quality -- no order has ever been placed. "
                 "CIs resample contracts, not quotes."),
        "rejection_lead_time": {
            "rejected_inside_T-72h": int(
                ((pairs["hours_to_kickoff"] <= 72) & pairs["rejected"]).sum()),
            "rejected_total": int(pairs["rejected"].sum()),
        },
        "overall": _compare(pairs, "rejected"),
        "by_time_to_kickoff": by_stratum,
        "width_rule_alone": _compare(isolated, "rejected"),
    }
