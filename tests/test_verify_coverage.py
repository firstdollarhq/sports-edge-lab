"""`unmatched_games` must distinguish "not covered" from "missing".

The NFL leg of `verify-settlements` reported `unmatched_games: 94` for two
runs and nobody could say what the 94 were. They were all **preseason**:
nflverse carries regular season and playoffs only, so a KXNFLGAME market for
an August game has no counterpart in the table and never will.

That is the source being correct, but it was counted in the same integer as a
real failure would be -- which means a genuine mapping bug on a covered date
could have appeared as 95 and nobody would have looked. These tests pin the
split, and specifically that an in-coverage miss is NOT absorbed into the
out-of-coverage bucket.
"""
import pandas as pd
import pytest

from sportsedge.betting import settle


def _games():
    """Two seasons of a toy stats table, regular season only."""
    return pd.DataFrame([
        # season 2025 window: 2025-09-07 .. 2025-09-14
        dict(season=2025, game_date="2025-09-07", home_team="KC", away_team="BAL",
             home_score=27, away_score=20, result="H"),
        dict(season=2025, game_date="2025-09-14", home_team="SF", away_team="LA",
             home_score=17, away_score=24, result="A"),
        # season 2026 window: 2026-09-13 .. 2026-09-13
        dict(season=2026, game_date="2026-09-13", home_team="PIT", away_team="ATL",
             home_score=20, away_score=13, result="H"),
    ])


@pytest.fixture
def played():
    return _games()


def test_coverage_windows_are_per_season(played):
    """A global min..max would swallow the whole 2025-2026 offseason."""
    windows = settle._coverage_windows(played)
    assert len(windows) == 2
    # August 2026 falls between the two seasons, so it is outside both.
    assert not settle._in_coverage(windows, "26AUG29")
    # A date inside a covered season is covered.
    assert settle._in_coverage(windows, "26SEP13")
    assert settle._in_coverage(windows, "25SEP07")


def test_preseason_is_out_of_coverage_not_a_failure(played, monkeypatch):
    """94 August markets should land in out_of_coverage, leaving in_coverage 0."""
    results = {
        "KXNFLGAME-26AUG29CHITEN-CHI": "no",
        "KXNFLGAME-26AUG29CHITEN-TEN": "yes",
                # NFL ticker order is AWAY+HOME, so ATL at PIT is ...ATLPIT.
        "KXNFLGAME-26SEP13ATLPIT-PIT": "yes",
    }
    monkeypatch.setattr(settle, "fetch_settled_results", lambda sport: results)
    out = settle.verify_against_stats(played, "nfl")

    assert out["checked"] == 1
    assert out["agreed"] == 1
    assert out["unmatched_games"] == 2
    assert out["unmatched_out_of_coverage"] == 2
    assert out["unmatched_in_coverage"] == 0
    assert out["unmatched_in_coverage_sample"] == []


def test_in_coverage_miss_is_reported_separately(played, monkeypatch):
    """A covered date that does not match is the real signal and must surface.

    This is the case the old undifferentiated counter hid: before the split,
    this market and a preseason one were the same number.
    """
    results = {
        "KXNFLGAME-26AUG29CHITEN-CHI": "no",          # preseason, expected miss
        "KXNFLGAME-26SEP13DENCAR-DEN": "yes",         # covered date, real miss
    }
    monkeypatch.setattr(settle, "fetch_settled_results", lambda sport: results)
    out = settle.verify_against_stats(played, "nfl")

    assert out["unmatched_games"] == 2
    assert out["unmatched_out_of_coverage"] == 1
    assert out["unmatched_in_coverage"] == 1
    sample = out["unmatched_in_coverage_sample"]
    assert len(sample) == 1
    assert sample[0]["date"] == "2026-09-13"
    assert sample[0]["home"] == "CAR"
    assert sample[0]["away"] == "DEN"


def test_totals_still_add_up(played, monkeypatch):
    """The split must partition unmatched_games exactly -- no double counting."""
    results = {
        "KXNFLGAME-26AUG29CHITEN-CHI": "no",
        "KXNFLGAME-26AUG28MINDEN-MIN": "yes",
        "KXNFLGAME-26SEP13DENCAR-DEN": "yes",
                # NFL ticker order is AWAY+HOME, so ATL at PIT is ...ATLPIT.
        "KXNFLGAME-26SEP13ATLPIT-PIT": "yes",
    }
    monkeypatch.setattr(settle, "fetch_settled_results", lambda sport: results)
    out = settle.verify_against_stats(played, "nfl")
    assert (out["unmatched_out_of_coverage"] + out["unmatched_in_coverage"]
            == out["unmatched_games"])


def test_empty_stats_table_covers_nothing():
    """No coverage windows means nothing can be called 'covered' by accident."""
    assert settle._coverage_windows(pd.DataFrame()) == []
    assert not settle._in_coverage([], "26SEP13")
