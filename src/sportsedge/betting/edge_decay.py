"""Does a claimed edge survive the walk to kickoff, and where does it come from?

THE QUESTION, AND WHY IT IS THE ONE LEFT OVER.

Two observations sat in this journal for several runs without being put
against each other:

  * Runs 4, 11, 13 and 14 each recorded that the LARGEST claimed edge on the
    board was a freshly-listed, thinly-traded contract.
  * Run 14 measured, from the other side, that the liquidity gate's rejections
    are almost entirely early-board quotes -- 0 of 1,084 NFL rejections sit
    inside T-72h.

Both say "the model's biggest disagreements live on the early board". Run 14
named joining them up as the next piece of work, needing no new data source.
This is it, and the join produces one strong positive and one strong negative.

WHAT IS MEASURED. For every contract in the committed snapshot history the
claimed edge is recomputed at every capture, through the production pricing
path (`recommend.recommend_*` with the liquidity gate switched off so that
rejected quotes are priced too, and `now` set to the capture time so the
in-play gate applies as of then). The gate verdict is attached separately; it
must not also decide who gets a price.

NO LOOKAHEAD. The model at each capture is built only from games that had
FINISHED BEFORE THAT CAPTURE, not from today's ratings. Pricing a 09-11 quote
with a model that has seen week 1 would manufacture exactly the decay this
module looks for, and this project has already shipped three lookahead bugs
(runs 2, 3, 6). The as-of model is why this is a module and not a script.

THE ANCHOR IS THE FIRST GATE-PASSING CAPTURE, NOT THE FIRST CAPTURE. The first
draft anchored on the first capture and reported that claimed edge GROWS by
20pp on gate-rejected contracts, CI [+11.6, +31.6]. That number is real and it
means almost nothing, because of what `listing_report` below then measured:
a contract's first captures are not a market at all. KXNFLGAME-26SEP27KCMIA-MIA
listed at 0.29/0.67 -- a 38-cent spread, ask size 20, volume 106 -- and was at
0.19/0.21 eighty-six minutes later. Anchoring there measures a book opening
and calls it a price move. Anchoring at the first quote the gate accepts is
the same instrument asking the question that was meant.

THE DECOMPOSITION. A claimed edge is a ratio between two things that both
move:

    edge = model_prob / (1 / ask) - 1

so it can decay because the market came to us, or because the model changed
its mind when last week's results landed. Those have opposite meanings: the
first is a real mispricing being corrected, the second is the model's early
number having been noise its own later evidence overwrote. Reporting only the
net change lets the second masquerade as the first, so each leg is frozen in
turn:

    market_leg = edge(model_first, ask_last)  - edge(model_first, ask_first)
    model_leg  = edge(model_last,  ask_first) - edge(model_first, ask_first)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from sportsedge.betting import fill_quality, line_movement, liquidity
from sportsedge.betting import recommend as recommend_mod
from sportsedge.models.live import build_nfl_model, build_soccer_model
from sportsedge.storage import snapshots

# Every pre-kickoff hour, as in fill_quality. NFL books open ~320h out and
# line_movement's default buckets stop at 168h, which would silently drop the
# exact cohort this module is about.
_ALL_HOURS = (1e9,)

# Columns the production pricing path reads off a snapshot row, beyond the ask
# `collect_quotes` already carries. Taken from HERE rather than re-derived, for
# the reason in `line_movement.collect_quotes`: kickoff resolution has silently
# produced in-play quotes when re-derived (run 13), so it lives in one place.
_PRICING_COLS = ("home_team", "away_team", "selection", "implied_prob_mid",
                 "yes_bid", "yes_ask_size", "volume", "spread", "expiration_time")

# A contract needs captures far enough apart for "decay" to mean anything.
MIN_SPAN_HOURS = 24.0

# Inside this many hours of kickoff, the last capture counts as a closing
# quote and the contract's window is COMPLETE. Outside it, "edge_last" is
# simply the most recent price of a game that has not been played, and the
# decay measured on it is a decay over a truncated window. The two are
# reported separately because pooling them would let 45 unfinished NFL
# contracts speak about what happens at kickoff.
CLOSED_WITHIN_HOURS = 2.0

# A contract counts as having been watched from its listing only if its first
# capture is comfortably after capture began for that sport. Otherwise it was
# already on the board when the cron started and its opening is unobserved --
# counting those as "opened inside the gate" would be counting our own start
# date as a market event.
LISTING_GRACE_MIN = 60.0

PRIMARY_TABLE = {"nfl": "nfl_games", "soccer": "epl_games"}


# --- as-of pricing ----------------------------------------------------------

def _as_of_model(sport: str, games: pd.DataFrame, as_of: pd.Timestamp):
    """Ratings built only from games that finished before `as_of`.

    Games are anchored on their published kickoff where there is one and on the
    calendar date otherwise, and the comparison is strict: a game kicking off
    at the same instant as the capture is NOT in the model, which is the
    conservative side of the only ambiguous case.
    """
    played = games.dropna(subset=["home_score", "away_score"]).copy()
    ko = pd.to_datetime(played.get("kickoff_utc"), utc=True, errors="coerce")
    date = pd.to_datetime(played["game_date"], utc=True, errors="coerce")
    played["_anchor"] = ko.fillna(date)
    prior = played[played["_anchor"] < as_of].drop(columns=["_anchor"])
    if sport == "nfl":
        return build_nfl_model(prior), None
    model, calibrator = build_soccer_model(prior)
    return model, calibrator


def _price_capture(sport: str, rows: list[dict], model, calibrator,
                   now: pd.Timestamp) -> list[dict]:
    """Every side of every event at one capture, priced by the production path."""
    kwargs = dict(edge_threshold=-1e9, apply_liquidity=False, now=now)
    if sport == "nfl":
        return recommend_mod.recommend_nfl(rows, model, **kwargs)
    return recommend_mod.recommend_soccer(rows, model, calibrator, **kwargs)


def collect_edges(sport: str, games: pd.DataFrame) -> pd.DataFrame:
    """One row per (contract, capture): claimed edge, as of that moment.

    Costs one model build per distinct capture DATE rather than per capture:
    Elo only moves when a game finishes, and the snapshot store partitions by
    UTC date, so two captures on the same day cannot straddle a result.
    """
    quotes = line_movement.collect_quotes(sport, buckets=_ALL_HOURS,
                                          keep_cols=_PRICING_COLS)
    if quotes.empty:
        return pd.DataFrame()

    verdicts = [liquidity.check(rec) for rec in quotes.to_dict("records")]
    quotes = quotes.assign(
        gate_ok=[v.ok for v in verdicts],
        reject_reason=[v.reason for v in verdicts],
        capture_date=quotes["fetched_at"].dt.strftime("%Y-%m-%d"),
    )

    priced = []
    model_cache: dict[str, tuple] = {}
    for (date, at), chunk in quotes.groupby(["capture_date", "fetched_at"], sort=True):
        if date not in model_cache:
            model_cache[date] = _as_of_model(sport, games, pd.Timestamp(at))
        model, calibrator = model_cache[date]

        recs = _price_capture(sport, chunk.to_dict("records"), model, calibrator, at)
        by_ticker = {r["market_ticker"]: r for r in recs}
        for rec in chunk.to_dict("records"):
            r = by_ticker.get(rec["market_ticker"])
            if r is None:          # missing side, unpriceable de-vig, in-play
                continue
            priced.append({
                "market_ticker": rec["market_ticker"],
                "event_ticker": rec["event_ticker"],
                "fetched_at": at,
                "hours_to_kickoff": rec["hours_to_kickoff"],
                "selection": rec["selection"],
                "gate_ok": rec["gate_ok"],
                "reject_reason": rec["reject_reason"],
                "spread": rec["spread"],
                "volume": rec["volume"],
                "yes_ask_size": rec["yes_ask_size"],
                "yes_ask": r["price_ask"],
                "model_prob": r["model_prob"],
                "fair_prob": r["market_fair_prob"],
                "edge_pct": r["edge_pct"],
            })
    return pd.DataFrame(priced)


# --- the opening book -------------------------------------------------------

def listing_report(sport: str, edges: pd.DataFrame,
                   *, grace_min: float = LISTING_GRACE_MIN) -> dict:
    """What a contract's quotes look like between listing and the book opening.

    Restricted to contracts whose listing we actually watched. A contract
    already on the board when capture began has an unobserved opening, and
    including it would report the cron's start date as a market event.
    """
    if edges.empty:
        return {"observed_listings": 0}

    t0 = edges["fetched_at"].min()
    rows = []
    for ticker, g in edges.sort_values("fetched_at").groupby("market_ticker"):
        first = g.iloc[0]
        if (first["fetched_at"] - t0).total_seconds() / 60.0 <= grace_min:
            continue                       # already listed when we started
        passing = g[g["gate_ok"]]
        f_ok = None if passing.empty else passing.iloc[0]
        rows.append({
            "market_ticker": ticker,
            "opened_rejected": not bool(first["gate_ok"]),
            "open_spread": float(first["spread"]) if pd.notna(first["spread"]) else np.nan,
            "open_volume": float(first["volume"]) if pd.notna(first["volume"]) else np.nan,
            "open_ask_size": (float(first["yes_ask_size"])
                              if pd.notna(first["yes_ask_size"]) else np.nan),
            "mins_to_gate_pass": (np.nan if f_ok is None else
                                  (f_ok["fetched_at"] - first["fetched_at"]
                                   ).total_seconds() / 60.0),
            "abs_ask_move_to_gate_pass": (np.nan if f_ok is None else
                                          abs(float(f_ok["yes_ask"])
                                              - float(first["yes_ask"]))),
            "abs_edge_move_to_gate_pass": (np.nan if f_ok is None else
                                           abs(float(f_ok["edge_pct"])
                                               - float(first["edge_pct"]))),
            "never_passed": f_ok is None,
        })
    if not rows:
        return {"observed_listings": 0,
                "note": "every contract was already on the board when capture began"}

    df = pd.DataFrame(rows)
    stub = df[df["opened_rejected"]]
    out = {
        "observed_listings": int(len(df)),
        "opened_outside_the_gate": int(len(stub)),
        "share_opened_outside_the_gate": round(float(df["opened_rejected"].mean()), 4),
    }
    if stub.empty:
        return out
    for label, col in (("open_spread", "open_spread"),
                       ("open_volume", "open_volume"),
                       ("open_ask_size", "open_ask_size"),
                       ("mins_to_gate_pass", "mins_to_gate_pass"),
                       ("abs_ask_move_to_gate_pass", "abs_ask_move_to_gate_pass"),
                       ("abs_edge_move_to_gate_pass", "abs_edge_move_to_gate_pass")):
        vals = stub[col].dropna()
        if vals.empty:
            continue
        out[f"median_{label}"] = round(float(vals.median()), 4)
        out[f"mean_{label}"] = round(float(vals.mean()), 4)
    out["never_passed_the_gate"] = int(stub["never_passed"].sum())
    return out


# --- decay from the first tradeable quote ------------------------------------

def _edge_pct(model_prob: float, ask: float) -> float:
    """The production edge formula, with one leg held fixed."""
    dec = recommend_mod._decimal_odds(ask)
    return np.nan if dec is None else recommend_mod.edge_fraction(model_prob, dec) * 100


def contract_decay(edges: pd.DataFrame, *, min_span_hours: float = MIN_SPAN_HOURS,
                   flag_threshold_pct: float = 3.0) -> pd.DataFrame:
    """First GATE-PASSING capture vs last pre-kickoff one, per contract.

    Only gate-passing captures are considered at either end. A contract is
    included once it has two such quotes at least `min_span_hours` apart --
    which is the same population the recommender could actually have bet, at
    both ends of the comparison.
    """
    if edges.empty:
        return pd.DataFrame()

    out = []
    for ticker, all_g in edges.sort_values("fetched_at").groupby("market_ticker"):
        g = all_g[all_g["gate_ok"]]
        if len(g) < 2:
            continue
        first, last = g.iloc[0], g.iloc[-1]
        span = first["hours_to_kickoff"] - last["hours_to_kickoff"]
        if span < min_span_hours:
            continue

        base = _edge_pct(first["model_prob"], first["yes_ask"])
        market_only = _edge_pct(first["model_prob"], last["yes_ask"])
        model_only = _edge_pct(last["model_prob"], first["yes_ask"])
        out.append({
            "market_ticker": ticker,
            "event_ticker": first["event_ticker"],
            "selection": first["selection"],
            "n_captures": int(len(g)),
            "first_h": round(float(first["hours_to_kickoff"]), 2),
            "last_h": round(float(last["hours_to_kickoff"]), 2),
            "span_h": round(float(span), 2),
            "edge_first_pct": round(float(base), 3),
            "edge_last_pct": round(float(last["edge_pct"]), 3),
            "d_edge_pp": round(float(last["edge_pct"] - base), 3),
            "market_leg_pp": round(float(market_only - base), 3),
            "model_leg_pp": round(float(model_only - base), 3),
            "d_ask": round(float(last["yes_ask"] - first["yes_ask"]), 4),
            "d_model_prob": round(float(last["model_prob"] - first["model_prob"]), 4),
            # The side the recommender would have flagged at the first
            # tradeable quote. This is the winner's-curse cohort: every claim
            # the project has ever made about "the biggest edge on the board"
            # is about these rows and not about the other side of the same
            # game, whose edge is mechanically the mirror image.
            "flagged_first": bool(base >= flag_threshold_pct),
            "ever_rejected": bool((~all_g["gate_ok"]).any()),
            # Did this contract's window actually finish? See CLOSED_WITHIN_HOURS.
            "reached_kickoff": bool(last["hours_to_kickoff"] <= CLOSED_WITHIN_HOURS),
        })
    return pd.DataFrame(out)


_COMPARED = ("edge_first_pct", "edge_last_pct", "d_edge_pp",
             "market_leg_pp", "model_leg_pp")


def _arm(df: pd.DataFrame, cols=_COMPARED) -> dict:
    out = {"n_contracts": int(len(df)),
           "n_events": int(df["event_ticker"].nunique()) if len(df) else 0}
    for c in cols:
        out[f"mean_{c}"] = round(float(df[c].mean()), 3) if len(df) else None
        out[f"median_{c}"] = round(float(df[c].median()), 3) if len(df) else None
    return out


def _flagged_arm(decay: pd.DataFrame) -> dict:
    """The flagged sides of one cohort, with its own contract and event count."""
    out = {"n_contracts_in_cohort": int(len(decay))}
    f = decay[decay["flagged_first"]] if len(decay) else decay
    out.update(_arm(f))
    if len(f):
        out["median_last_h"] = round(float(f["last_h"].median()), 2)
    return out


def _compare(decay: pd.DataFrame, flag: str) -> dict:
    """Two arms plus a cluster bootstrap over EVENTS, not contracts.

    Both sides of an NFL game are one de-vig apart, so the two rows of an event
    are not two independent observations -- resampling contracts would report
    an interval about 1.4x too tight, which is the same mistake run 14 caught
    one level down.
    """
    a, b = decay[decay[flag]], decay[~decay[flag]]
    out = {"yes": _arm(a), "no": _arm(b)}
    if not (len(a) and len(b)):
        return out
    for c in _COMPARED:
        out[f"diff_{c}"] = round(float(a[c].mean() - b[c].mean()), 3)

    if (min(len(a), len(b)) < fill_quality.MIN_ARM_QUOTES
            or min(a["event_ticker"].nunique(),
                   b["event_ticker"].nunique()) < fill_quality.MIN_ARM_CONTRACTS):
        out["ci"] = None
        out["underpowered"] = (
            f"an arm has < {fill_quality.MIN_ARM_QUOTES} contracts or "
            f"< {fill_quality.MIN_ARM_CONTRACTS} events; no interval reported")
        return out
    out["ci"] = {c: fill_quality._cluster_ci(decay, value=c, group=flag,
                                             cluster="event_ticker")
                 for c in _COMPARED}
    return out


def summarize(sport: str, *, games: pd.DataFrame | None = None,
              min_span_hours: float = MIN_SPAN_HOURS) -> dict:
    """Claimed-edge decay over the tradeable pre-kickoff window."""
    if games is None:
        games = snapshots.read_processed(PRIMARY_TABLE[sport])

    edges = collect_edges(sport, games)
    if edges.empty:
        return {"sport": sport, "contracts": 0,
                "note": "no priceable pre-kickoff captures in the snapshot history"}

    out = {
        "sport": sport,
        "quotes_priced": int(len(edges)),
        "gate_pass_rate": round(float(edges["gate_ok"].mean()), 4),
        "listing": listing_report(sport, edges),
    }

    decay = contract_decay(edges, min_span_hours=min_span_hours)
    if decay.empty:
        out.update(contracts=0,
                   note=f"no contract has two gate-passing quotes "
                        f">= {min_span_hours}h apart")
        return out

    overall = _arm(decay)
    overall["mean_abs_d_ask"] = round(float(decay["d_ask"].abs().mean()), 4)
    overall["mean_abs_d_model_prob"] = round(float(decay["d_model_prob"].abs().mean()), 4)
    overall["share_ask_unmoved"] = round(float((decay["d_ask"] == 0).mean()), 4)
    overall["share_model_unmoved"] = round(float((decay["d_model_prob"] == 0).mean()), 4)

    out.update({
        "contracts": int(len(decay)),
        "min_span_hours": min_span_hours,
        "median_span_h": round(float(decay["span_h"].median()), 2),
        "median_first_h": round(float(decay["first_h"].median()), 2),
        "overall": overall,
        # The winner's-curse test: on the sides the recommender would have
        # flagged, does the market come toward the model by kickoff?
        "by_flagged_at_first_tradeable_quote": _compare(decay, "flagged_first"),
        # The same test on the cohort whose window actually FINISHED. Smaller
        # and the only one entitled to the word "closing"; the complement is a
        # set of games that have not been played, whose "edge_last" is just
        # today's price.
        "flagged_by_window_completeness": {
            "complete": _flagged_arm(decay[decay["reached_kickoff"]]),
            "truncated": _flagged_arm(decay[~decay["reached_kickoff"]]),
        },
    })
    return out
