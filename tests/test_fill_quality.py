"""Quote persistence vs the liquidity gate.

Three of these pin mistakes the module made in draft and one pins a trap it
inherited:

  - `collect_quotes` drops anything outside its widest bucket edge, so a
    caller that wants the far end of the NFL board must ask for it. The draft
    used the default edges and silently lost every quote past T-168h, which is
    where most of the gate's rejections live.
  - a cluster bootstrap over a one-contract arm returns a tight interval that
    is a restatement of its input; it must be suppressed, not printed.
  - pairs must not be formed across the overnight capture blackout.
  - in-play quotes must never enter, which is `collect_quotes`' job and is
    checked here because this module is the one that would publish them.
"""
import pandas as pd
import pytest

from sportsedge.betting import fill_quality as fq
from sportsedge.betting import line_movement as lm
from sportsedge.storage import snapshots

KICKOFF = pd.Timestamp("2026-09-20T17:00:00Z")


def _snap(ticker, at, ask, *, bid=None, size=5000.0, volume=5000.0,
          event="KXNFLGAME-26SEP20CLETB"):
    """One snapshot row, liquid by default so the gate's verdict is the variable."""
    bid = ask - 0.01 if bid is None else bid
    return {
        "sport": "nfl", "league": "NFL", "event_ticker": event,
        "market_ticker": ticker, "game_id": None,
        "home_team": "TB", "away_team": "CLE",
        "expiration_time": "2026-09-20T23:00:00Z", "selection": "away",
        "yes_bid": bid, "yes_ask": ask, "implied_prob_mid": (bid + ask) / 2,
        "spread": round(ask - bid, 4),
        "yes_bid_size": size, "yes_ask_size": size,
        "volume": volume, "volume_24h": volume, "open_interest": volume,
        "status": "active", "source": "kalshi", "fetched_at": at,
    }


@pytest.fixture
def patched(monkeypatch):
    """Feed rows straight through the real collect_quotes, with kickoff pinned."""
    def apply(rows):
        monkeypatch.setattr(snapshots, "load_snapshots",
                            lambda sport=None: pd.DataFrame(rows))
        monkeypatch.setattr(lm.kickoff_mod, "resolve_kickoff",
                            lambda *a, **k: KICKOFF)
        monkeypatch.setattr(lm, "parse_event_ticker",
                            lambda ev, sport: {"home_team": "TB", "away_team": "CLE"})
    return apply


def _at(hours_before):
    return (KICKOFF - pd.Timedelta(hours=hours_before)).isoformat()


# -- the inherited trap -------------------------------------------------------

def test_collect_quotes_drops_rows_past_its_widest_bucket():
    """Why fill_quality must pass its own edges, stated as a test.

    The gate rejects almost nothing inside T-72h; its rejections live out at
    T-120h to T-290h. Under the default edges (widest 168h) a quote at T-200h
    is dropped with no warning, so the draft measured the gate on the slice of
    the board where it is least active and would have reported a null.
    """
    assert lm._bucket_label(200.0, lm.DEFAULT_BUCKETS) is None
    assert lm._bucket_label(200.0, fq._ALL_HOURS) is not None


def test_keep_cols_carries_the_book(patched):
    patched([_snap("A", _at(100.0), 0.40)])
    q = lm.collect_quotes("nfl", buckets=fq._ALL_HOURS, keep_cols=fq._BOOK_COLS)
    assert set(fq._BOOK_COLS) <= set(q.columns)
    assert q.iloc[0]["volume"] == 5000.0
    assert q.iloc[0]["yes_bid"] == pytest.approx(0.39)


# -- pairing ------------------------------------------------------------------

def test_adverse_tick_is_a_rise_in_the_ask(patched):
    patched([
        _snap("A", _at(100.0), 0.40),
        _snap("A", _at(99.5), 0.41),     # +1 tick against the buyer
        _snap("A", _at(99.0), 0.41),     # unchanged
        _snap("A", _at(98.5), 0.40),     # -1 tick, in the buyer's favour
    ])
    p = fq.collect_pairs("nfl").sort_values("hours_to_kickoff", ascending=False)
    assert list(p["adverse_tick"]) == [1.0, 0.0, 0.0]
    assert list(p["favourable_tick"]) == [0.0, 0.0, 1.0]
    assert list(p["unmoved"]) == [0.0, 1.0, 0.0]


def test_an_exact_one_tick_move_is_counted(patched):
    """`0.41 - 0.40` is 0.009999999999999953, so `delta >= 0.01` misses it.

    Whether a one-cent move survives a float comparison depends on the price
    -- 0.33 -> 0.34 registers, 0.40 -> 0.41 does not -- so the draft's counts
    were wrong in a price-dependent direction, not merely low. Every pair of
    adjacent cents from 0.01 to 0.98 is checked rather than the one that
    happened to fail.
    """
    assert (0.41 - 0.40) < 0.01                      # the reason this test exists
    for cents in range(1, 98):
        lo, hi = cents / 100, (cents + 1) / 100
        patched([_snap("A", _at(100.0), lo), _snap("A", _at(99.5), hi)])
        p = fq.collect_pairs("nfl")
        assert p.iloc[0]["adverse_tick"] == 1.0, f"{lo} -> {hi} not counted"


def test_pairs_are_not_formed_across_the_capture_blackout(patched):
    """The cron sleeps 04:00-10:00Z. A six-hour 'persistence' is not one."""
    patched([
        _snap("A", _at(100.0), 0.40),
        _snap("A", _at(94.0), 0.55),     # six hours later: a blackout gap
    ])
    assert fq.collect_pairs("nfl").empty


def test_in_play_quotes_never_enter(patched):
    """A post-kickoff quote knows part of the result; pairing to it would
    report the settlement jump as a failure of quote persistence."""
    patched([
        _snap("A", _at(0.4), 0.40),
        _snap("A", (KICKOFF + pd.Timedelta(hours=1)).isoformat(), 0.98),
    ])
    assert fq.collect_pairs("nfl").empty


# -- the reporting guard ------------------------------------------------------

def test_a_one_contract_arm_gets_no_confidence_interval(patched):
    rows = []
    # One illiquid contract (fails the gate on volume) against three liquid ones.
    for i, h in enumerate([100.0, 99.5, 99.0]):
        rows.append(_snap("THIN", _at(h), 0.40, volume=1.0))
    for t in ("A", "B", "C"):
        for h in (100.0, 99.5, 99.0):
            rows.append(_snap(t, _at(h), 0.40))
    patched(rows)

    out = fq.summarize("nfl")
    overall = out["overall"]
    assert overall["rejected"]["n_contracts"] == 1
    assert overall["diff_p_adverse_tick"] is not None      # the point estimate stands
    assert overall["diff_ci_cluster"] is None              # the interval does not
    assert "underpowered" in overall


def test_a_powered_cohort_does_get_an_interval(patched):
    rows = []
    for t in ("T1", "T2", "T3", "T4"):                     # rejected arm
        for h in [100.0 - 0.5 * k for k in range(12)]:
            rows.append(_snap(t, _at(h), 0.40, volume=1.0))
    for t in ("A", "B", "C", "D"):                         # accepted arm
        for h in [100.0 - 0.5 * k for k in range(12)]:
            rows.append(_snap(t, _at(h), 0.40))
    patched(rows)

    overall = fq.summarize("nfl")["overall"]
    assert overall["rejected"]["n_contracts"] == 4
    assert overall["diff_ci_cluster"] is not None
    lo, hi = overall["diff_ci_cluster"]
    assert lo <= overall["diff_p_adverse_tick"] <= hi
    assert "underpowered" not in overall


def test_width_rule_is_isolated_from_the_other_rules(patched):
    """The 5% relative-width rule must not be credited with volume's rejections.

    A contract that fails on volume is excluded from the width-rule cohort
    entirely rather than counted on its narrow side, which would otherwise
    load the rule's 'accepted' arm with quotes another rule had already
    condemned.
    """
    rows = []
    for h in [100.0 - 0.5 * k for k in range(8)]:
        rows.append(_snap("THIN", _at(h), 0.40, volume=1.0))       # volume reject
        rows.append(_snap("WIDE", _at(h), 0.15, bid=0.13))         # width reject
        rows.append(_snap("GOOD", _at(h), 0.40))                   # passes
    patched(rows)

    out = fq.summarize("nfl")
    tickers = set(fq.collect_pairs("nfl")["market_ticker"])
    assert tickers == {"THIN", "WIDE", "GOOD"}
    w = out["width_rule_alone"]
    assert w["rejected"]["n_contracts"] == 1                       # WIDE only
    assert w["accepted"]["n_contracts"] == 1                       # GOOD only; THIN dropped


def test_empty_history_reports_itself(monkeypatch):
    monkeypatch.setattr(snapshots, "load_snapshots",
                        lambda sport=None: pd.DataFrame(columns=snapshots.COLUMNS))
    out = fq.summarize("nfl")
    assert out["pairs"] == 0
    assert "no consecutive capture pairs" in out["note"]
