"""The recommender must not price a pre-game model against an in-play market.

On 2026-09-12, with six EPL fixtures about an hour into play, the recommender
produced Aston Villa at +278% "edge" (0.44 pre-game, 0.13 live) and Chelsea at
+24% (0.80 pre-game, 0.41 live), and logged two of them. Nothing in the
pipeline looked at the clock.

The bias has a direction, which is what makes it worse than noise: the market
marks down whichever side is currently losing, and the pre-game model does not
follow, so the apparent edge lands on the losing side essentially every time.
A rule that bets it is a rule that systematically buys teams that are behind.
"""
import pandas as pd
import pytest

from sportsedge.betting import recommend as R


def _row(ticker, expiration, **over):
    row = {"market_ticker": ticker, "event_ticker": ticker.rsplit("-", 1)[0],
           "home_team": "Chelsea", "away_team": "Hull",
           "expiration_time": expiration, "yes_ask": 0.41,
           "implied_prob_mid": 0.41}
    row.update(over)
    return row


def test_epl_fixture_under_way_is_gated_off(monkeypatch):
    """The 2026-09-12 case: expiry 17:00Z, kickoff 14:00Z, now 15:11Z."""
    monkeypatch.setattr(R.kickoff, "resolve_kickoff", lambda *a, **k: None)
    rows = [_row("KXEPLGAME-26SEP12CFCHUL-CFC", "2026-09-12T17:00:00Z")]

    upcoming, in_play = R.partition_in_play("soccer", rows,
                                            now="2026-09-12T15:11:34Z")

    assert upcoming == []
    assert len(in_play) == 1


def test_epl_fixture_not_yet_started_is_allowed(monkeypatch):
    """The later slate the same afternoon must still be bettable.

    Its quotes held to within 0.02 across the day while the in-play ones moved
    up to 0.57, so gating it off would discard a genuinely pre-game price.
    """
    monkeypatch.setattr(R.kickoff, "resolve_kickoff", lambda *a, **k: None)
    rows = [_row("KXEPLGAME-26SEP12TOTEVE-TOT", "2026-09-12T19:30:00Z")]

    upcoming, in_play = R.partition_in_play("soccer", rows,
                                            now="2026-09-12T15:11:34Z")

    assert len(upcoming) == 1
    assert in_play == []


def test_true_kickoff_is_preferred_over_the_expiry_estimate(monkeypatch):
    """When the stats source has the fixture, the assumed lag must not be used.

    Here the real kickoff is 16:00Z but expiry-minus-3h would infer 14:00Z.
    At 15:00Z the game has not started and the bet must be allowed.
    """
    monkeypatch.setattr(R.kickoff, "resolve_kickoff",
                        lambda *a, **k: pd.Timestamp("2026-09-12T16:00:00Z").to_pydatetime())
    rows = [_row("KXNFLGAME-26SEP12X-Y", "2026-09-12T17:00:00Z")]

    upcoming, in_play = R.partition_in_play("nfl", rows, now="2026-09-12T15:00:00Z")

    assert len(upcoming) == 1 and in_play == []


def test_nfl_sunday_slate_mid_afternoon_is_gated(monkeypatch):
    """Week 1 is 2026-09-13; Sunday games run 17:00-23:30Z.

    A scheduled run inside that window is the case that would have done this
    at scale, to the slate carrying run 4's pre-registered prediction.
    """
    monkeypatch.setattr(
        R.kickoff, "resolve_kickoff",
        lambda *a, **k: pd.Timestamp("2026-09-13T17:00:00Z").to_pydatetime())
    rows = [_row("KXNFLGAME-26SEP13CHICAR-CHI", "2026-09-13T20:00:00Z")]

    upcoming, in_play = R.partition_in_play("nfl", rows, now="2026-09-13T18:30:00Z")

    assert upcoming == [] and len(in_play) == 1


def test_exactly_at_kickoff_counts_as_started(monkeypatch):
    monkeypatch.setattr(
        R.kickoff, "resolve_kickoff",
        lambda *a, **k: pd.Timestamp("2026-09-13T17:00:00Z").to_pydatetime())
    rows = [_row("KXNFLGAME-26SEP13CHICAR-CHI", "2026-09-13T20:00:00Z")]

    upcoming, in_play = R.partition_in_play("nfl", rows, now="2026-09-13T17:00:00Z")

    assert upcoming == [] and len(in_play) == 1


def test_unknown_kickoff_and_unusable_expiry_is_left_alone(monkeypatch):
    """The gate removes games it can positively identify as started.

    With neither a kickoff nor a parseable expiration there is nothing to
    decide on, and silently dropping the quote would be a different bug.
    """
    monkeypatch.setattr(R.kickoff, "resolve_kickoff", lambda *a, **k: None)
    rows = [_row("KXEPLGAME-X-Y", None)]

    upcoming, in_play = R.partition_in_play("soccer", rows, now="2026-09-12T15:11:34Z")

    assert len(upcoming) == 1 and in_play == []


def test_recommend_soccer_logs_nothing_on_an_in_play_board(monkeypatch):
    """End-to-end: the gate is on by default, not an opt-in the caller can miss."""
    monkeypatch.setattr(R.kickoff, "resolve_kickoff", lambda *a, **k: None)

    # The real 2026-09-12 Chelsea/Hull board, ~1h into the match.
    ev = "KXEPLGAME-26SEP12CFCHUL"
    board = [
        _row(f"{ev}-CFC", "2026-09-12T17:00:00Z", yes_ask=0.41, implied_prob_mid=0.41),
        _row(f"{ev}-HUL", "2026-09-12T17:00:00Z", yes_ask=0.28, implied_prob_mid=0.28),
        _row(f"{ev}-TIE", "2026-09-12T17:00:00Z", yes_ask=0.32, implied_prob_mid=0.32),
    ]

    class _Model:
        def elo_diff(self, home, away):
            return 120.0

    class _Cal:
        def predict_proba(self, diff):
            # Pre-game view: Chelsea strong. Against the marked-down live price
            # this is exactly the fake +24% edge that was logged.
            return {"H": 0.509, "D": 0.24, "A": 0.251}

    recs = R.recommend_soccer(board, _Model(), _Cal(), apply_liquidity=False,
                              now="2026-09-12T15:11:34Z")

    assert recs == []


def test_gate_is_measured_not_guessed():
    """The lag constants are the ones the journal cites, per sport."""
    assert R._MAX_EXPIRATION_LAG["soccer"] == pd.Timedelta(hours=3)
    assert R._MAX_EXPIRATION_LAG["nfl"] == pd.Timedelta(hours=6)
