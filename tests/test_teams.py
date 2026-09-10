"""Team/ticker resolution.

The home/away order tests are the important ones. Kalshi uses a DIFFERENT order
per sport (NFL away+home, EPL home+away), which is not documented anywhere and
was established by checking tickers against nflverse and football-data.co.uk.
If either of these ever flips, every model probability silently applies to the
wrong side and the bug is invisible in aggregate metrics -- so these are pinned.
"""
import pytest

from sportsedge.ingest.teams import (
    TeamResolutionError,
    market_team_code,
    parse_event_ticker,
    resolve_epl_team,
    resolve_nfl_team,
    selection_for,
)


def test_nfl_ticker_is_away_then_home():
    # Verified against nflverse: NYG travelled to the Rams on 2026-09-21.
    t = parse_event_ticker("KXNFLGAME-26SEP21NYGLAR", "nfl")
    assert t["away_team"] == "NYG"
    assert t["home_team"] == "LA"


def test_epl_ticker_is_home_then_away():
    # Verified against football-data.co.uk: Arsenal hosted Chelsea 2026-09-06.
    t = parse_event_ticker("KXEPLGAME-26SEP06ARSCFC", "soccer")
    assert t["home_team"] == "Arsenal"
    assert t["away_team"] == "Chelsea"


def test_nfl_alias_mapping():
    assert resolve_nfl_team("LAR") == "LA"    # Kalshi LAR -> nflverse LA
    assert resolve_nfl_team("JAC") == "JAX"
    assert resolve_nfl_team("KC") == "KC"


def test_epl_name_mapping():
    assert resolve_epl_team("NFO") == "Nott'm Forest"
    assert resolve_epl_team("MUN") == "Man United"


def test_ambiguous_two_and_three_letter_split_resolves():
    # 'LVLAC' could be LV+LAC or LVL+AC; only one leaves two valid codes.
    t = parse_event_ticker("KXNFLGAME-26SEP20LVLAC", "nfl")
    assert (t["away_team"], t["home_team"]) == ("LV", "LAC")


def test_unknown_team_code_raises():
    with pytest.raises(TeamResolutionError):
        resolve_nfl_team("ZZZ")
    with pytest.raises(TeamResolutionError):
        resolve_epl_team("ZZZ")


def test_malformed_ticker_raises():
    with pytest.raises(TeamResolutionError):
        parse_event_ticker("NOT-A-TICKER", "nfl")


def test_market_team_code_and_selection():
    ev = "KXNFLGAME-26SEP21NYGLAR"
    assert market_team_code(f"{ev}-NYG", ev) == "NYG"
    assert selection_for(f"{ev}-NYG", ev, "nfl") == "away"
    assert selection_for(f"{ev}-LAR", ev, "nfl") == "home"


def test_soccer_draw_selection():
    ev = "KXEPLGAME-26SEP06ARSCFC"
    assert selection_for(f"{ev}-TIE", ev, "soccer") == "draw"
    assert selection_for(f"{ev}-ARS", ev, "soccer") == "home"
    assert selection_for(f"{ev}-CFC", ev, "soccer") == "away"


def test_market_not_extending_event_raises():
    with pytest.raises(TeamResolutionError):
        market_team_code("KXNFLGAME-26SEP21OTHER-NYG", "KXNFLGAME-26SEP21NYGLAR")
