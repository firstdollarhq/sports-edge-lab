"""How much does the price move as kickoff approaches?

Why this exists
---------------
Run 7 recorded that `closing_odds_decimal` had never held a closing price: the
review session fired once daily at ~06:00Z against slates starting 14:00-17:00Z,
so every "closing" quote was a mid-morning one (T-7.8h for the first settled
EPL cohort, T-10.8h for NFL week 1). It measured drift across the *quiet* days
beforehand -- NFL ask moving a mean of 0.0013 over the last full day -- and was
careful to say that number bounds nothing, because the project held zero
captures inside the final 8 hours of any settled game.

The 30-minute capture cron closed that gap. This module is the measurement run
7 said had to follow: with captures inside the final hour, how much does the
line actually move there, and therefore how stale is a CLV cut at T-8h?

What it measures
----------------
For each contract, the last observed `yes_ask` in each time-to-kickoff bucket,
then the absolute move from that bucket's price to the last pre-kickoff price
observed at all. Reported in **implied-probability points**, not decimal odds:
a 0.02 move means the same thing at 0.10 and at 0.90, whereas the equivalent
decimal-odds move is 2.2 vs 0.02 and would make longshots dominate any average
purely by parameterisation.

Two rules that decide whether the answer means anything
-------------------------------------------------------
1. **Kickoff comes from the stats source, never from the expiration.** Kalshi's
   expiration sits 3h (EPL, measured 13/13) to 6h (NFL) after kickoff, so
   bucketing on it would file in-play quotes as pre-game ones -- and an in-play
   quote knows the result. That is the same contamination `ingest.kickoff`
   exists to prevent; this module reuses it rather than re-deriving it.
2. **A bucket's n is reported with it, always.** The interesting bucket is the
   final hour, and it is the newest and therefore the thinnest. A mean move
   over two contracts is not a fact about the market.
"""
from __future__ import annotations

import pandas as pd

from sportsedge.ingest import kickoff as kickoff_mod
from sportsedge.ingest.teams import parse_event_ticker, TeamResolutionError
from sportsedge.storage import snapshots

# Upper edges, in hours before kickoff. The first three exist to resolve the
# window the cron was built for; the wide tail is where every pre-cron capture
# lands and is kept so the two regimes can be compared rather than conflated.
DEFAULT_BUCKETS = (1.0, 2.0, 4.0, 8.0, 24.0, 168.0)


def _bucket_label(hours: float, edges) -> str | None:
    prev = 0.0
    for e in edges:
        if hours <= e:
            return f"T-{prev:g}h..T-{e:g}h"
        prev = e
    return None


def collect_quotes(sport: str, *, buckets=DEFAULT_BUCKETS,
                   keep_cols: tuple[str, ...] = ()) -> pd.DataFrame:
    """Every captured pre-kickoff quote, tagged with its time-to-kickoff.

    In-play captures are dropped, not bucketed as "T-0": the cron runs through
    the slate, so a large share of the raw rows are post-kickoff, and a price
    that already knows part of the result is not a line movement.

    `keep_cols` copies additional raw snapshot columns onto each row. It exists
    so that a caller needing the rest of the order book -- `betting.fill_quality`
    needs bid, sizes and volume to re-run the liquidity gate -- gets them from
    HERE rather than re-deriving kickoff for itself. Kickoff resolution is the
    one step in this project that has silently produced in-play quotes when
    re-derived (run 13), so it lives in exactly one place.

    Note on `buckets`: a quote whose time-to-kickoff falls outside the widest
    edge is DROPPED, so a caller interested in the far end of the board (the
    NFL books that open ~290h out) must widen the edges or it will silently
    lose them.
    """
    df = snapshots.load_snapshots(sport)
    if df is None or df.empty:
        return pd.DataFrame()

    kickoffs: dict[str, pd.Timestamp] = {}
    rows = []
    for rec in df.to_dict("records"):
        event = rec.get("event_ticker")
        if not event:
            continue
        if event not in kickoffs:
            try:
                teams = parse_event_ticker(event, sport)
                ko = kickoff_mod.resolve_kickoff(
                    sport, teams["home_team"], teams["away_team"],
                    rec.get("expiration_time"))
            except TeamResolutionError:
                ko = None
            kickoffs[event] = pd.Timestamp(ko) if ko is not None else pd.NaT
        ko = kickoffs[event]
        if pd.isna(ko):
            continue

        at = pd.to_datetime(rec.get("fetched_at"), utc=True, errors="coerce")
        ask = rec.get("yes_ask")
        if pd.isna(at) or ask is None or pd.isna(ask) or float(ask) <= 0:
            continue

        hours = (ko - at).total_seconds() / 3600.0
        if hours <= 0:          # in-play or later; see docstring
            continue
        label = _bucket_label(hours, buckets)
        if label is None:
            continue
        row = {
            "market_ticker": rec.get("market_ticker"),
            "event_ticker": event,
            "fetched_at": at,
            "hours_to_kickoff": hours,
            "kickoff": ko,
            "yes_ask": float(ask),
            "bucket": label,
        }
        for col in keep_cols:
            row[col] = rec.get(col)
        rows.append(row)
    return pd.DataFrame(rows)


def summarize(sport: str, *, buckets=DEFAULT_BUCKETS, now=None) -> dict:
    """Mean/median |move| to the closing quote, in implied-probability points.

    Two exclusions, both of which the first draft of this function got wrong
    and both of which manufactured a reassuring zero:

    1. **Only games that have already kicked off.** For an upcoming game the
       "last pre-kickoff quote" is just the most recent capture, which is by
       construction the newest bucket's own quote. Comparing that bucket to
       itself yields exactly 0.00, so a board full of unstarted games reports
       "the line does not move in the final hour" -- from data in which no
       final hour has happened yet. That is the same shape as every bug in
       this project's tally: a value that was not what the surrounding code
       assumed.

    2. **Only buckets strictly earlier than the reference quote.** Even after
       (1), the bucket containing the closing quote compares that quote to
       itself. It is dropped rather than counted as a zero.

    `reference_lag_h` is reported per bucket: the median time-to-kickoff of the
    closing quotes the moves were measured against. A bucket whose reference is
    itself 7h from kickoff has not measured anything about the close, and that
    number is the only way a reader can tell.
    """
    q = collect_quotes(sport, buckets=buckets)
    if q.empty:
        return {"sport": sport, "contracts": 0, "events": 0, "quotes": 0,
                "buckets": {}}

    now = pd.Timestamp(now or kickoff_mod.utcnow())
    q = q[q["kickoff"] < now]
    if q.empty:
        return {"sport": sport, "contracts": 0, "events": 0, "quotes": 0,
                "buckets": {},
                "note": "no game in the snapshot history has kicked off yet"}

    q = q.sort_values("fetched_at")
    ref = q.groupby("market_ticker").tail(1).set_index("market_ticker")

    out: dict[str, dict] = {}
    for (ticker, bucket), grp in q.groupby(["market_ticker", "bucket"]):
        final = ref.loc[ticker]
        row = grp.iloc[-1]
        if row["fetched_at"] >= final["fetched_at"]:
            continue                                    # exclusion (2)
        move = abs(float(row["yes_ask"]) - float(final["yes_ask"]))
        d = out.setdefault(bucket, {"moves": [], "refs": [], "contracts": set()})
        d["moves"].append(move)
        d["refs"].append(float(final["hours_to_kickoff"]))
        d["contracts"].add(ticker)

    summary = {}
    for bucket, d in out.items():
        moves = sorted(d["moves"])
        refs = sorted(d["refs"])
        summary[bucket] = {
            "n_contracts": len(d["contracts"]),
            "mean_abs_move": round(sum(moves) / len(moves), 5),
            "median_abs_move": round(moves[len(moves) // 2], 5),
            "max_abs_move": round(moves[-1], 5),
            "share_moved_ge_0.02": round(
                sum(1 for m in moves if m >= 0.02) / len(moves), 4),
            "reference_lag_h": round(refs[len(refs) // 2], 2),
        }

    order = {f: i for i, f in enumerate(sorted(
        summary, key=lambda b: float(b.split("..T-")[1].rstrip("h"))))}
    return {
        "sport": sport,
        "settled_events": int(q["event_ticker"].nunique()),
        "contracts": int(q["market_ticker"].nunique()),
        "quotes": int(len(q)),
        "note": ("|change| in implied probability (yes_ask) between a bucket's "
                 "last quote and the contract's LAST PRE-KICKOFF quote, over "
                 "games that have already kicked off. `reference_lag_h` is how "
                 "far that closing quote itself sat from kickoff -- a large "
                 "value means the bucket says nothing about the true close."),
        "buckets": dict(sorted(summary.items(), key=lambda kv: order[kv[0]])),
    }
