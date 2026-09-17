"""Degrading to the committed table when an upstream stats source is down.

Written after football-data.co.uk started redirecting every request to
`http://127.0.0.1/` on 2026-09-17 and took `recommend --sports soccer` down
with it. The behaviour under test is not "does the fallback work" -- that part
is a try/except -- but the two ways a fallback goes wrong quietly:

  * it prices on a table that is missing games that have already been played;
  * it cannot check for that and treats "could not check" as "fine".

Network-free: `fetch` is a callable, so a dead source is a function that
raises.
"""
import pandas as pd
import pytest

from sportsedge.ingest import sources


def _labels(seasons):
    return {str(s) for s in seasons}


def _games(rows):
    return pd.DataFrame(rows, columns=["season", "game_date", "home_team",
                                       "away_team", "home_score", "away_score",
                                       "kickoff_utc", "ingested_at"])


COMMITTED = _games([
    ["2026-27", "2026-09-12", "Arsenal", "Chelsea", 2.0, 1.0,
     "2026-09-12T14:00:00+00:00", "2026-09-16T06:00:00+00:00"],
    ["2026-27", "2026-09-13", "Liverpool", "Everton", 0.0, 0.0,
     "2026-09-13T14:00:00+00:00", "2026-09-16T06:00:00+00:00"],
])

ESPN_SAME = _games([
    ["2026-27", "2026-09-12", "Arsenal", "Chelsea", 2.0, 1.0,
     "2026-09-12T14:00:00+00:00", "2026-09-17T06:00:00+00:00"],
    ["2026-27", "2026-09-13", "Liverpool", "Everton", 0.0, 0.0,
     "2026-09-13T14:00:00+00:00", "2026-09-17T06:00:00+00:00"],
])

# One more played game than the committed table has: the league has moved on.
ESPN_AHEAD = _games(list(ESPN_SAME.itertuples(index=False, name=None)) + [
    ["2026-27", "2026-09-16", "Spurs", "Fulham", 3.0, 1.0,
     "2026-09-16T19:00:00+00:00", "2026-09-17T06:00:00+00:00"],
])


def _dead(*_a, **_k):
    raise ConnectionError("upstream redirected to http://127.0.0.1/")


@pytest.fixture
def stub_tables(monkeypatch):
    """Point read_processed at in-memory frames, per table name."""
    def install(tables):
        def fake(name):
            if name not in tables:
                raise FileNotFoundError(name)
            return tables[name]
        monkeypatch.setattr(sources.snapshots, "read_processed", fake)
    return install


def test_live_source_is_used_and_not_marked_degraded(stub_tables):
    stub_tables({})
    games, prov = sources.load_games(
        "soccer", ["2026-27"], _labels, lambda: COMMITTED)
    assert prov["source"] == "upstream"
    assert prov["degraded"] is False and prov["usable"] is True
    assert len(games) == 2


def test_dead_source_falls_back_and_is_usable_when_espn_agrees(stub_tables):
    stub_tables({"epl_games": COMMITTED, "espn_epl_games": ESPN_SAME})
    games, prov = sources.load_games("soccer", ["2026-27"], _labels, _dead)
    assert prov["source"] == "committed_table"
    assert prov["degraded"] is True
    assert prov["usable"] is True
    assert prov["freshness"]["missing_played"] == 0
    assert len(games) == 2
    assert "127.0.0.1" in prov["error"]


def test_fallback_is_refused_when_espn_knows_a_played_game_the_table_lacks(stub_tables):
    """The whole point. Age is not the test; a missing result is.

    The committed table here is complete as of 09-13 and would pass any
    freshness-by-timestamp check with a generous window. It is still the wrong
    thing to build Elo ratings from, because a match has been played since.
    """
    stub_tables({"epl_games": COMMITTED, "espn_epl_games": ESPN_AHEAD})
    _, prov = sources.load_games("soccer", ["2026-27"], _labels, _dead)
    assert prov["usable"] is False
    assert prov["freshness"]["missing_played"] == 1


def test_unverifiable_fallback_is_not_treated_as_a_verified_one(stub_tables):
    """No ESPN table means nothing independent confirmed the fallback.

    `checked: False` must not read as `missing_played: 0`. This is the branch
    that would otherwise let a completely unchecked table price a live board
    the first time both sources are down at once.
    """
    stub_tables({"epl_games": COMMITTED})
    _, prov = sources.load_games("soccer", ["2026-27"], _labels, _dead)
    assert prov["usable"] is False
    assert prov["freshness"]["checked"] is False
    assert prov["freshness"]["missing_played"] is None


def test_dead_source_with_no_committed_table_is_not_usable(stub_tables):
    stub_tables({})
    games, prov = sources.load_games("soccer", ["2026-27"], _labels, _dead)
    assert prov["usable"] is False
    assert games.empty


def test_season_filter_is_applied_to_the_fallback_too(stub_tables):
    """The committed table holds every season ever ingested.

    Returning it unfiltered is the bug `_load_games` documents for backtests;
    the fallback path must not reintroduce it.
    """
    stub_tables({"epl_games": COMMITTED, "espn_epl_games": ESPN_SAME})
    games, prov = sources.load_games("soccer", ["2025-26"], _labels, _dead)
    assert games.empty
    assert prov["usable"] is False        # empty ratings can never price
    assert prov["missing_seasons"] == ["2025-26"]


def test_an_old_but_complete_table_is_usable(stub_tables):
    """Age alone never blocks a price, and the timestamp is not a fetch time.

    `write_processed` holds back rows it re-fetched unchanged, so `ingested_at`
    dates the last CHANGE, not the last look -- a table refreshed minutes ago
    can carry a two-day-old stamp. Reported under a name that says so, and
    never consulted for `usable`.
    """
    old = COMMITTED.copy()
    old["ingested_at"] = "2020-01-01T00:00:00+00:00"
    stub_tables({"epl_games": old, "espn_epl_games": ESPN_SAME})
    _, prov = sources.load_games("soccer", ["2026-27"], _labels, _dead)
    assert prov["usable"] is True
    assert prov["table_last_changed_at"] == "2020-01-01T00:00:00+00:00"
    assert "ingested_at" not in prov


def test_describe_names_the_state_in_one_line(stub_tables):
    stub_tables({"epl_games": COMMITTED, "espn_epl_games": ESPN_AHEAD})
    _, prov = sources.load_games("soccer", ["2026-27"], _labels, _dead)
    line = sources.describe(prov)
    assert "upstream DOWN" in line and "NOT USABLE" in line
