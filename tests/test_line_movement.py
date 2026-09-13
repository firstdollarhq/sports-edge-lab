"""Line movement by time-to-kickoff.

The tests that matter here are the two exclusions. Both were wrong in the
first draft, and both failed in the *reassuring* direction -- they reported
"the line does not move near kickoff" from data containing no near-kickoff
observation at all.
"""
import pandas as pd
import pytest

from sportsedge.betting import line_movement as lm

KICKOFF = pd.Timestamp("2026-09-12T14:00:00Z")


def _quotes(rows):
    """rows: (ticker, hours_before_kickoff, ask)."""
    return pd.DataFrame([
        {"market_ticker": t,
         "event_ticker": "KXEPLGAME-26SEP12LFCFUL",
         "fetched_at": KICKOFF - pd.Timedelta(hours=h),
         "hours_to_kickoff": h,
         "kickoff": KICKOFF,
         "yes_ask": a,
         "bucket": lm._bucket_label(h, lm.DEFAULT_BUCKETS)}
        for t, h, a in rows
    ])


@pytest.fixture
def patched(monkeypatch):
    def apply(rows):
        monkeypatch.setattr(lm, "collect_quotes",
                            lambda sport, **kw: _quotes(rows))
    return apply


AFTER = KICKOFF + pd.Timedelta(hours=3)


def test_bucket_labels_are_contiguous():
    assert lm._bucket_label(0.5, lm.DEFAULT_BUCKETS) == "T-0h..T-1h"
    assert lm._bucket_label(1.0, lm.DEFAULT_BUCKETS) == "T-0h..T-1h"
    assert lm._bucket_label(1.5, lm.DEFAULT_BUCKETS) == "T-1h..T-2h"
    assert lm._bucket_label(9.0, lm.DEFAULT_BUCKETS) == "T-8h..T-24h"
    assert lm._bucket_label(1000.0, lm.DEFAULT_BUCKETS) is None


def test_move_is_measured_against_the_closing_quote(patched):
    patched([("A", 10.0, 0.40), ("A", 0.5, 0.46)])
    out = lm.summarize("soccer", now=AFTER)
    assert out["buckets"]["T-8h..T-24h"]["mean_abs_move"] == pytest.approx(0.06)
    # The closing quote's own bucket is not compared to itself.
    assert "T-0h..T-1h" not in out["buckets"]
    assert out["buckets"]["T-8h..T-24h"]["reference_lag_h"] == pytest.approx(0.5)


def test_upcoming_games_are_excluded(patched):
    """THE trap. For a game that has not kicked off, the 'last pre-kickoff
    quote' is just the newest capture, so the newest bucket is compared to
    itself and yields exactly 0.00 -- reported as 'the line is quiet near
    kickoff' from a sample where no near-kickoff price has been observed."""
    patched([("A", 10.0, 0.40), ("A", 0.5, 0.46)])
    before_kickoff = KICKOFF - pd.Timedelta(minutes=10)
    out = lm.summarize("soccer", now=before_kickoff)
    assert out["contracts"] == 0
    assert out["buckets"] == {}
    assert "kicked off" in out["note"]


def test_reference_lag_exposes_a_stale_closing_quote(patched):
    """A bucket whose reference quote is itself 7.8h from kickoff has measured
    nothing about the close, and `reference_lag_h` is how a reader can tell."""
    patched([("A", 30.0, 0.40), ("A", 7.8, 0.42)])
    out = lm.summarize("soccer", now=AFTER)
    assert out["buckets"]["T-24h..T-168h"]["reference_lag_h"] == pytest.approx(7.8)
    assert "T-8h..T-24h" not in out["buckets"]


def test_a_contract_that_never_moved_counts_as_zero(patched):
    patched([("A", 10.0, 0.40), ("A", 0.5, 0.40)])
    out = lm.summarize("soccer", now=AFTER)
    b = out["buckets"]["T-8h..T-24h"]
    assert b["mean_abs_move"] == 0.0 and b["n_contracts"] == 1


def test_share_moved_threshold(patched):
    patched([("A", 10.0, 0.40), ("A", 0.5, 0.43),
             ("B", 10.0, 0.60), ("B", 0.5, 0.605)])
    out = lm.summarize("soccer", now=AFTER)
    assert out["buckets"]["T-8h..T-24h"]["share_moved_ge_0.02"] == pytest.approx(0.5)


def test_last_quote_in_a_bucket_is_the_one_used(patched):
    """Two quotes in one bucket: the later is the bucket's price."""
    patched([("A", 20.0, 0.10), ("A", 9.0, 0.40), ("A", 0.5, 0.45)])
    out = lm.summarize("soccer", now=AFTER)
    assert out["buckets"]["T-8h..T-24h"]["mean_abs_move"] == pytest.approx(0.05)


def test_empty_history_is_not_an_error(patched):
    patched([])
    out = lm.summarize("soccer", now=AFTER)
    assert out["contracts"] == 0 and out["buckets"] == {}


def test_in_play_quotes_never_enter_collect_quotes(monkeypatch):
    """Kalshi expiration is 3h (EPL) to 6h (NFL) after kickoff, so the raw
    snapshot history contains post-kickoff quotes. A price that already knows
    part of the result is not a line movement."""
    raw = pd.DataFrame([
        {"event_ticker": "KXEPLGAME-26SEP12LFCFUL",
         "market_ticker": "KXEPLGAME-26SEP12LFCFUL-LFC",
         "expiration_time": "2026-09-12T17:00:00Z",
         "fetched_at": (KICKOFF + pd.Timedelta(hours=1)).isoformat(),
         "yes_ask": 0.95},
        {"event_ticker": "KXEPLGAME-26SEP12LFCFUL",
         "market_ticker": "KXEPLGAME-26SEP12LFCFUL-LFC",
         "expiration_time": "2026-09-12T17:00:00Z",
         "fetched_at": (KICKOFF - pd.Timedelta(hours=2)).isoformat(),
         "yes_ask": 0.55},
    ])
    monkeypatch.setattr(lm.snapshots, "load_snapshots", lambda sport: raw)
    monkeypatch.setattr(lm.kickoff_mod, "resolve_kickoff",
                        lambda *a, **k: KICKOFF.to_pydatetime())
    q = lm.collect_quotes("soccer")
    assert list(q["yes_ask"]) == [0.55]
