"""Claimed-edge decay: the anchor, the lookahead guard, and the decomposition.

Network-free. `collect_edges` is driven through a stubbed snapshot store and a
stubbed pricing call, so these test the module's own arithmetic and its choice
of anchor rather than the Elo model or Kalshi.

The behaviours pinned here are the ones whose absence produced a wrong number
during this module's own development, not the ones that were easy to assert:

  * anchoring on the first capture instead of the first GATE-PASSING capture
    reported +20pp of "edge growth", CI [+11.6, +31.6], that was entirely a
    contract's book opening;
  * building the as-of model from all games rather than prior ones is the
    lookahead this project has shipped three times;
  * pooling finished and unfinished contracts lets games that have not been
    played speak about what happens at kickoff.
"""
import numpy as np
import pandas as pd
import pytest

from sportsedge.betting import edge_decay


def _edges(rows):
    """(ticker, hours_to_kickoff, ask, model_prob, gate_ok) -> an edges frame."""
    out = []
    base = pd.Timestamp("2026-09-10T00:00:00Z")
    for ticker, h, ask, mp, ok in rows:
        out.append({
            "market_ticker": ticker,
            "event_ticker": ticker.rsplit("-", 1)[0],
            "fetched_at": base + pd.Timedelta(hours=(400 - h)),
            "hours_to_kickoff": float(h),
            "selection": "home",
            "gate_ok": bool(ok),
            "reject_reason": "" if ok else "spread",
            "spread": 0.01 if ok else 0.38,
            "volume": 900.0 if ok else 10.0,
            "yes_ask_size": 500.0 if ok else 4.0,
            "yes_ask": float(ask),
            "model_prob": float(mp),
            "fair_prob": float(ask) - 0.01,
            "edge_pct": edge_decay._edge_pct(mp, ask),
        })
    return pd.DataFrame(out)


# --- the anchor -------------------------------------------------------------

def test_the_opening_stub_is_excluded_from_the_decay_measurement():
    """The bug this module was rewritten around.

    KXNFLGAME-26SEP27KCMIA-MIA listed at 0.29/0.67 and was at 0.19/0.21 eighty
    -six minutes later. Measured from its first capture that is a 48-cent
    "price move"; measured from its first tradeable quote it is nothing. Only
    the second is a market.
    """
    edges = _edges([
        ("G-A", 300, 0.67, 0.50, False),   # the stub: wide, empty, rejected
        ("G-A", 290, 0.20, 0.50, True),    # book opens
        ("G-A", 100, 0.20, 0.50, True),    # and does not move again
    ])
    decay = edge_decay.contract_decay(edges)

    assert len(decay) == 1
    row = decay.iloc[0]
    assert row["first_h"] == 290          # NOT 300
    assert row["d_ask"] == 0.0
    assert row["d_edge_pp"] == 0.0
    # The stub is still recorded as having happened.
    assert bool(row["ever_rejected"]) is True


def test_a_contract_with_one_tradeable_quote_is_not_a_decay_observation():
    edges = _edges([
        ("G-B", 300, 0.67, 0.50, False),
        ("G-B", 290, 0.20, 0.50, True),
        ("G-B", 280, 0.25, 0.50, False),
    ])
    assert edge_decay.contract_decay(edges).empty


def test_a_short_span_is_not_a_walk_to_kickoff():
    edges = _edges([
        ("G-C", 100, 0.20, 0.50, True),
        ("G-C", 90, 0.30, 0.50, True),     # 10h apart, below MIN_SPAN_HOURS
    ])
    assert edge_decay.contract_decay(edges).empty
    assert len(edge_decay.contract_decay(edges, min_span_hours=5.0)) == 1


# --- the decomposition ------------------------------------------------------

def test_a_pure_market_move_is_charged_to_the_market_leg():
    edges = _edges([
        ("G-D", 200, 0.40, 0.50, True),
        ("G-D", 100, 0.45, 0.50, True),    # ask moved, model did not
    ])
    row = edge_decay.contract_decay(edges).iloc[0]
    assert row["model_leg_pp"] == 0.0
    assert row["market_leg_pp"] == pytest.approx(row["d_edge_pp"])
    assert row["d_edge_pp"] < 0           # paying more for the same belief


def test_a_pure_model_move_is_charged_to_the_model_leg():
    edges = _edges([
        ("G-E", 200, 0.40, 0.50, True),
        ("G-E", 100, 0.40, 0.44, True),    # model changed its mind, ask did not
    ])
    row = edge_decay.contract_decay(edges).iloc[0]
    assert row["market_leg_pp"] == 0.0
    assert row["model_leg_pp"] == pytest.approx(row["d_edge_pp"])


def test_the_legs_are_reported_separately_when_both_move():
    """Net change alone would let a model rethink look like a market correction."""
    edges = _edges([
        ("G-F", 200, 0.40, 0.50, True),
        ("G-F", 100, 0.45, 0.44, True),
    ])
    row = edge_decay.contract_decay(edges).iloc[0]
    assert row["market_leg_pp"] != 0.0 and row["model_leg_pp"] != 0.0
    # Both legs point the same way here, so each is smaller than the total.
    assert abs(row["market_leg_pp"]) < abs(row["d_edge_pp"])
    assert abs(row["model_leg_pp"]) < abs(row["d_edge_pp"])


# --- no lookahead -----------------------------------------------------------

def test_the_as_of_model_never_sees_a_game_that_had_not_finished():
    """The guard against this project's recurring bug (runs 2, 3, 6).

    A game kicking off at the same instant as the capture is excluded: strict
    `<`, which is the conservative side of the only ambiguous case.
    """
    games = pd.DataFrame([
        {"season": "2026", "week": 1, "game_date": "2026-09-10",
         "kickoff_utc": "2026-09-10T17:00:00+00:00", "home_team": "KC",
         "away_team": "BUF", "home_score": 20.0, "away_score": 17.0},
        {"season": "2026", "week": 2, "game_date": "2026-09-17",
         "kickoff_utc": "2026-09-17T17:00:00+00:00", "home_team": "KC",
         "away_team": "MIA", "home_score": 30.0, "away_score": 10.0},
    ])
    seen = {}

    def spy(prior):
        seen["n"] = len(prior)
        return object()

    import sportsedge.betting.edge_decay as mod
    original = mod.build_nfl_model
    mod.build_nfl_model = spy
    try:
        mod._as_of_model("nfl", games, pd.Timestamp("2026-09-17T17:00:00Z"))
        assert seen["n"] == 1          # week 2 kicks off exactly now: excluded
        mod._as_of_model("nfl", games, pd.Timestamp("2026-09-18T00:00:00Z"))
        assert seen["n"] == 2
    finally:
        mod.build_nfl_model = original


# --- reporting guards -------------------------------------------------------

def test_an_unfinished_contract_is_not_counted_as_having_reached_kickoff():
    edges = _edges([
        ("G-G", 200, 0.40, 0.50, True),
        ("G-G", 80, 0.40, 0.50, True),     # still 80h out: window truncated
        ("G-H", 200, 0.40, 0.50, True),
        ("G-H", 0.4, 0.40, 0.50, True),    # last capture ~T-0.4h: complete
    ])
    decay = edge_decay.contract_decay(edges)
    by = dict(zip(decay["market_ticker"], decay["reached_kickoff"]))
    assert by["G-G"] is False
    assert by["G-H"] is True


def test_a_contract_already_listed_when_capture_began_is_not_a_listing():
    """Otherwise the cron's own start date gets reported as a market event."""
    edges = _edges([
        ("G-I", 300, 0.67, 0.50, False),   # first capture in the whole frame
        ("G-I", 290, 0.20, 0.50, True),
        ("G-J", 200, 0.30, 0.50, False),   # appeared later: a real listing
        ("G-J", 150, 0.22, 0.50, True),
    ])
    rep = edge_decay.listing_report("nfl", edges)
    assert rep["observed_listings"] == 1
    assert rep["opened_outside_the_gate"] == 1


def test_a_thin_cohort_gets_counts_but_no_confidence_interval():
    """Run 14's lesson, one level up: an interval over two events is its input."""
    edges = _edges([
        ("G-K", 200, 0.20, 0.50, True), ("G-K", 100, 0.20, 0.50, True),
        ("G-L", 200, 0.60, 0.30, True), ("G-L", 100, 0.60, 0.30, True),
    ])
    decay = edge_decay.contract_decay(edges)
    out = edge_decay._compare(decay, "flagged_first")
    assert out["ci"] is None
    assert "underpowered" in out
    assert out["yes"]["n_contracts"] + out["no"]["n_contracts"] == len(decay)
