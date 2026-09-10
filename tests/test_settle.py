import pytest

from sportsedge.betting.settle import _clv_pct, _lookup_by_date, ticker_date


def test_ticker_date_parsing():
    assert ticker_date("26SEP21") == "2026-09-21"
    assert ticker_date("26AUG02") == "2026-08-02"


def test_clv_positive_when_price_beat_the_close():
    # Bet at decimal 2.5 (40c), closed at 2.0 (50c) -> we got the better price.
    assert _clv_pct(2.5, 2.0) == pytest.approx(25.0)


def test_clv_negative_when_price_worse_than_close():
    assert _clv_pct(2.0, 2.5) < 0


def test_lookup_matches_exact_date():
    key = {("2026-09-21", "LA", "NYG"): "H"}
    teams = {"date_code": "26SEP21", "home_team": "LA", "away_team": "NYG"}
    assert _lookup_by_date(key, teams) == "H"


def test_lookup_tolerates_one_day_timezone_skew():
    key = {("2026-09-22", "LA", "NYG"): "A"}
    teams = {"date_code": "26SEP21", "home_team": "LA", "away_team": "NYG"}
    assert _lookup_by_date(key, teams) == "A"


def test_lookup_rejects_same_pairing_on_a_different_date():
    """The same two teams meet repeatedly (preseason, reverse fixture, playoffs).

    Matching on teams alone silently compares a market to the wrong game -- this
    actually happened and produced 20 phantom settlement mismatches.
    """
    key = {("2026-12-25", "LA", "NYG"): "H"}
    teams = {"date_code": "26SEP21", "home_team": "LA", "away_team": "NYG"}
    assert _lookup_by_date(key, teams) is None
