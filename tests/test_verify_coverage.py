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


# --- the ESPN supplement, against a real gap (run 19) -----------------------

def test_espn_supplement_covers_settlements_the_primary_has_not_published():
    """Run 16 built the supplement; run 19 is the first run it mattered.

    Brentford 3-0 Chelsea kicked off 2026-09-18T19:00Z and carried two open
    wagers. Kalshi settled them and ESPN had the score the next morning;
    football-data.co.uk had not published the fixture and still stops at
    2026-09-14. Without the supplement those two settlements are simply
    absent from the cross-check -- and they are the newest rows in the
    ledger, which is exactly the cohort most in need of checking.

    Asserted on the committed tables rather than a fixture, because the claim
    being pinned is about the two sources' real relative lag. If
    football-data.co.uk later backfills 09-18, the first assertion goes
    slack and the test still holds the ones that matter.
    """
    import pandas as pd
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    primary = pd.read_csv(root / "data" / "processed" / "epl_games.csv")
    supplement = pd.read_csv(root / "data" / "processed" / "espn_epl_games.csv")
    ledger = pd.read_csv(root / "bets" / "ledger.csv")

    played = supplement.dropna(subset=["home_score", "away_score"])
    game = played[(played["home_team"] == "Brentford")
                  & (played["away_team"] == "Chelsea")]
    assert len(game) == 1, "ESPN must carry the 09-18 fixture"

    have = {(str(r["game_date"])[:10], r["home_team"], r["away_team"])
            for _, r in primary.dropna(subset=["home_score"]).iterrows()}
    key = ("2026-09-18", "Brentford", "Chelsea")

    settled = ledger[ledger["status"].isin(["won", "lost"])]
    on_game = settled[settled["game_id"].astype(str).str.contains("26SEP18BRECFC")]
    assert len(on_game) == 2, "both wagers on that fixture must be settled"

    # The whole point: these two are verifiable only via the supplement.
    if key not in have:
        assert key in {(str(r["game_date"])[:10], r["home_team"], r["away_team"])
                       for _, r in played.iterrows()}
