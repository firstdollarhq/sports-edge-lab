"""Kickoff resolution, and the leak it exists to prevent.

This is the second lookahead bug in this project, and structurally the same as
the first: a column whose name promised one thing (`commence_time`, `week`)
while holding another, feeding the one code path whose docstring promised no
leakage. The first cost every NFL ROI figure published before 2026-09-10. This
one would have cost every NFL CLV figure, which is worse -- CLV is the metric
the project designated as its better short-run signal, and an in-play price
makes it a restatement of the result.

So these tests pin the behaviour, not the implementation.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from sportsedge.betting import settle
from sportsedge.ingest import kickoff


UTC = timezone.utc


@pytest.fixture
def schedule(monkeypatch):
    """A two-fixture schedule, one per sport, with known kickoffs."""
    df = pd.DataFrame([
        {"sport": "nfl", "home_team": "LA", "away_team": "SF",
         "game_date": "2026-09-10", "kickoff_utc": "2026-09-11T00:35:00+00:00"},
        {"sport": "nfl", "home_team": "IND", "away_team": "BAL",
         "game_date": "2026-09-13", "kickoff_utc": "2026-09-13T17:00:00+00:00"},
    ])
    epl = pd.DataFrame([
        {"sport": "soccer", "home_team": "Chelsea", "away_team": "Hull",
         "game_date": "2026-09-12", "kickoff_utc": "2026-09-12T14:00:00+00:00"},
    ])
    tables = {"nfl_games": df, "epl_games": epl}
    kickoff.clear_cache()
    monkeypatch.setattr(kickoff.snapshots, "read_processed", lambda name: tables[name])
    yield tables
    kickoff.clear_cache()


def test_resolves_true_kickoff_not_the_kalshi_expiration(schedule):
    """Kalshi said 06:35Z for SF @ LA. The ball was snapped at 00:35Z."""
    ko = kickoff.resolve_kickoff("nfl", "LA", "SF", "2026-09-11T06:35:00Z")
    assert ko == datetime(2026, 9, 11, 0, 35, tzinfo=UTC)


def test_kalshi_expiration_is_always_after_kickoff(schedule):
    """The property that makes the expiration unusable as a pre-game cutoff.

    Measured across all 31 NFL events on the 2026-09-10 board: 27 at +3h, 4 at
    +6h, none at +0h. If this ever comes back zero or negative, the assumption
    behind this whole module has changed and the CLV path needs re-examining.
    """
    lag = kickoff.expiration_lag("nfl", "LA", "SF", "2026-09-11T06:35:00Z")
    assert lag == timedelta(hours=6)

    lag = kickoff.expiration_lag("nfl", "IND", "BAL", "2026-09-13T20:00:00Z")
    assert lag == timedelta(hours=3)


def test_unknown_fixture_returns_none_rather_than_guessing(schedule):
    assert kickoff.resolve_kickoff("nfl", "NYG", "DAL", "2026-09-14T06:20:00Z") is None


def test_far_from_any_fixture_returns_none(schedule):
    """A hint months away must not snap onto an unrelated fixture."""
    assert kickoff.resolve_kickoff("nfl", "LA", "SF", "2027-01-01T00:00:00Z") is None


def test_require_kickoff_raises_instead_of_falling_back(schedule):
    with pytest.raises(kickoff.KickoffUnavailable):
        kickoff.require_kickoff("nfl", "NYG", "DAL", "2026-09-14T06:20:00Z")


# -- the consumer that actually leaked ---------------------------------------


def _bet(**over):
    base = {
        "bet_id": "deadbeef", "sport": "nfl", "matchup": "SF @ LA",
        "market_ticker": "KXNFLGAME-26SEP10SFLAR-SF",
        "market_odds_decimal": 2.7777777777777777,
        "expiration_time": "2026-09-11T06:35:00Z", "kickoff_utc": None,
    }
    base.update(over)
    return pd.Series(base)


def test_clv_cutoff_is_kickoff_so_in_play_quotes_are_excluded(schedule, monkeypatch):
    """The regression. An in-play quote must never become the closing price.

    Two captures exist: 0.36 well before kickoff, and 0.99 an hour into the
    game. Cutting at Kalshi's expiration picks the 0.99 and manufactures a CLV
    of roughly +175% on a bet that was entered at 0.36 -- a number produced
    entirely by the clock, and one that would only ever look good when the bet
    won.
    """
    captures = {
        "2026-09-11T00:35:00+00:00": {"yes_ask": 0.36},   # last pre-kickoff
        "2026-09-11T06:35:00Z": {"yes_ask": 0.99},        # in-play
    }

    def fake_latest_before(sport, ticker, cutoff):
        return captures.get(str(cutoff))

    monkeypatch.setattr(settle.snapshots, "latest_before", fake_latest_before)

    odds = settle._closing_odds(_bet())
    assert odds == pytest.approx(1 / 0.36)

    clv = settle._clv_pct(2.7777777777777777, odds)
    assert clv == pytest.approx(0.0, abs=1e-9)


def test_no_kickoff_means_no_clv_never_a_fallback(schedule, monkeypatch):
    """An unresolvable kickoff yields a missing number, not a guessed one."""
    monkeypatch.setattr(settle.snapshots, "latest_before",
                        lambda *a, **k: {"yes_ask": 0.99})
    assert settle._closing_odds(_bet(matchup="DAL @ NYG", sport="nfl")) is None


def test_stored_kickoff_is_preferred_over_re_resolving(schedule):
    assert settle._kickoff_for(_bet(kickoff_utc="2026-09-11T00:35:00+00:00")) == \
        "2026-09-11T00:35:00+00:00"


def test_soccer_kickoff_resolves_once_the_match_is_played(schedule):
    """EPL kickoffs arrive with the result, which is when CLV is computed."""
    ko = kickoff.resolve_kickoff("soccer", "Chelsea", "Hull", "2026-09-12T17:00:00Z")
    assert ko == datetime(2026, 9, 12, 14, 0, tzinfo=UTC)
