"""Placement lag is reported, per cohort, rather than asserted in prose.

Runs 19 and 20 both wrote that the 11 open pre-registered wagers had been
"placed at T-48h to T-56h" and built a falsifiable prediction on it. That
range is the SETTLED cohort's (min 48.1h, median 53.1h). The open rows were
struck at T-217.7h to T-225.0h. Nothing in the codebase computed either
number, so the mix-up survived two runs and inverted the prediction it
supported: under the lag-variance relationship being invoked, the longest-lag
rows in the ledger raise the CLV standard deviation, they do not lower it.

The last two tests re-derive that correction from the committed ledger, so it
is reproducible from the repo rather than living only in a journal entry.
"""
import datetime as dt

import pandas as pd
import pytest

import sportsedge.betting.ledger as ledger_mod

from test_ledger import _add, _set_reference_lag


def _stamp_kickoffs(offsets_h):
    """Give each row a kickoff `offsets_h` after the moment it was placed."""
    df = ledger_mod._load()
    placed = pd.to_datetime(df["placed_at"], utc=True, format="mixed")
    df["kickoff_utc"] = [
        (p + dt.timedelta(hours=h)).isoformat()
        for p, h in zip(placed, offsets_h)
    ]
    ledger_mod._save(df)


def test_settled_and_pending_lags_are_reported_apart(tmp_path, monkeypatch):
    """The exact confusion that produced the error: two cohorts, two ranges.

    Two settled rows at ~50h and two open rows at ~220h. Reading the settled
    range and attributing it to the open book is what runs 19 and 20 did.
    """
    monkeypatch.setattr(ledger_mod, "LEDGER_PATH", tmp_path / "ledger.csv")

    for i, close_p in enumerate((0.51, 0.49)):
        bet = _add(ledger_mod.SHADOW, game_id=f"s{i}", market_odds_decimal=2.0)
        ledger_mod.record_result(bet, "lost", closing_odds_decimal=1.0 / close_p)
    _add(ledger_mod.SHADOW, game_id="p0", market_odds_decimal=2.0)
    _add(ledger_mod.SHADOW, game_id="p1", market_odds_decimal=2.0)
    _stamp_kickoffs([48.0, 56.0, 218.0, 225.0])
    _set_reference_lag([0.5, 0.5, None, None])

    shadow = ledger_mod.summarize()["shadow"]
    settled = shadow["placement_lag_real_close"]
    pending = shadow["placement_lag_pending"]

    assert settled["n"] == 2
    assert settled["min_h"] == pytest.approx(48.0, abs=1e-6)
    assert settled["max_h"] == pytest.approx(56.0, abs=1e-6)

    assert pending["n"] == 2
    assert pending["min_h"] == pytest.approx(218.0, abs=1e-6)
    assert pending["max_h"] == pytest.approx(225.0, abs=1e-6)

    # The whole point: the open book's range does not overlap the settled
    # cohort's, so quoting one for the other is visibly wrong.
    assert pending["min_h"] > settled["max_h"]


def test_lag_block_is_empty_rather_than_guessing(tmp_path, monkeypatch):
    """No kickoff means no lag. An absent kickoff must not read as T-0."""
    monkeypatch.setattr(ledger_mod, "LEDGER_PATH", tmp_path / "ledger.csv")

    _add(ledger_mod.SHADOW, game_id="p0", market_odds_decimal=2.0)
    shadow = ledger_mod.summarize()["shadow"]

    assert shadow["placement_lag_pending"] == {
        "n": 0, "min_h": None, "median_h": None, "max_h": None}


def test_empty_ledger_reports_no_lag(tmp_path, monkeypatch):
    monkeypatch.setattr(ledger_mod, "LEDGER_PATH", tmp_path / "ledger.csv")
    shadow = ledger_mod.summarize()["shadow"]
    assert shadow["placement_lag_pending"]["n"] == 0


def test_lag_reporting_mutates_no_row(tmp_path, monkeypatch):
    """A diagnostic. It gates nothing and re-prices nothing.

    Asserted so a later run cannot quietly turn placement lag into a filter --
    run 19 already recorded that lag is not a variance knob, because betting
    later shrinks the estimand by the same mechanism that shrinks the noise.
    """
    monkeypatch.setattr(ledger_mod, "LEDGER_PATH", tmp_path / "ledger.csv")

    _add(ledger_mod.SHADOW, game_id="p0", market_odds_decimal=2.0)
    _stamp_kickoffs([220.0])
    before = (tmp_path / "ledger.csv").read_bytes()

    ledger_mod.summarize()

    assert (tmp_path / "ledger.csv").read_bytes() == before


def test_the_open_pre_registered_wagers_were_not_placed_at_t_minus_48h():
    """Re-derives the correction from the committed ledger.

    The pre-registered cohort is reconstructed from `placed_at` -- 1 row on
    09-10 and 35 on 09-11 -- exactly as the README specifies. Its open rows
    are the ones runs 19 and 20 described as struck at T-48h to T-56h.
    """
    df = ledger_mod._load()
    placed = pd.to_datetime(df["placed_at"], utc=True, format="mixed")
    kick = pd.to_datetime(df["kickoff_utc"], utc=True, format="mixed")
    lag_h = (kick - placed).dt.total_seconds() / 3600.0

    cohort = placed.dt.date.astype(str).isin(["2026-09-10", "2026-09-11"])
    open_rows = cohort & (df["status"] == "pending")
    if not open_rows.any():
        pytest.skip("cohort has fully settled; the correction is now history")

    # Not 48-56h. The longest lags the ledger holds.
    assert lag_h[open_rows].min() > 200.0
    assert lag_h[open_rows].max() > 200.0


def test_the_settled_cohort_is_where_48_to_56_hours_came_from():
    """The misquoted range is real -- it just belongs to the other cohort."""
    df = ledger_mod._load()
    placed = pd.to_datetime(df["placed_at"], utc=True, format="mixed")
    kick = pd.to_datetime(df["kickoff_utc"], utc=True, format="mixed")
    lag_h = (kick - placed).dt.total_seconds() / 3600.0

    ref = pd.to_numeric(df["clv_reference_lag_h"], errors="coerce")
    real_close = (df["status"].isin(["won", "lost"])
                  & ref.notna()
                  & (ref <= ledger_mod.CLV_REFERENCE_MAX_LAG_H))

    settled_lag = lag_h[real_close].dropna()
    assert len(settled_lag) >= 20
    # The settled real-close cohort starts just above 48h and its median sits
    # in the low 50s -- which is the "T-48h to T-56h" that was carried over.
    assert 48.0 <= settled_lag.min() < 49.0
    assert 50.0 < settled_lag.median() < 60.0
