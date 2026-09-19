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


# Every club here has played before, which is what a rating table looks like:
# the real one holds eight seasons. It matters because the supplement refuses
# a club it has never seen (see the rename test at the bottom), so a fixture
# where teams appear from nowhere would test that guard instead of the fill.
COMMITTED = _games([
    ["2026-27", "2026-09-12", "Arsenal", "Chelsea", 2.0, 1.0,
     "2026-09-12T14:00:00+00:00", "2026-09-16T06:00:00+00:00"],
    ["2026-27", "2026-09-13", "Liverpool", "Everton", 0.0, 0.0,
     "2026-09-13T14:00:00+00:00", "2026-09-16T06:00:00+00:00"],
    ["2026-27", "2026-09-05", "Spurs", "Liverpool", 1.0, 2.0,
     "2026-09-05T14:00:00+00:00", "2026-09-16T06:00:00+00:00"],
    ["2026-27", "2026-09-06", "Fulham", "Arsenal", 0.0, 3.0,
     "2026-09-06T14:00:00+00:00", "2026-09-16T06:00:00+00:00"],
])

ESPN_SAME = _games(list(COMMITTED.itertuples(index=False, name=None)))

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
    assert len(games) == 4


def test_dead_source_falls_back_and_is_usable_when_espn_agrees(stub_tables):
    stub_tables({"epl_games": COMMITTED, "espn_epl_games": ESPN_SAME})
    games, prov = sources.load_games("soccer", ["2026-27"], _labels, _dead)
    assert prov["source"] == "committed_table"
    assert prov["degraded"] is True
    assert prov["usable"] is True
    assert prov["freshness"]["missing_played"] == 0
    assert len(games) == 4
    assert "127.0.0.1" in prov["error"]


def test_a_gap_espn_can_fill_is_filled_rather_than_refused(stub_tables):
    """The 09-19 case: the league moved on and the odds source is still down.

    Age is not the test; a missing result is -- and a missing result that ESPN
    holds is now repaired instead of being a reason to go dark. The rating
    path reads scores, not odds, and ESPN carries scores.
    """
    stub_tables({"epl_games": COMMITTED, "espn_epl_games": ESPN_AHEAD})
    games, prov = sources.load_games("soccer", ["2026-27"], _labels, _dead)
    assert prov["usable"] is True
    assert len(games) == 5
    assert prov["espn_supplement"]["rows"] == 1
    assert prov["espn_supplement"]["games"] == ["Fulham @ Spurs 2026-09-16"]
    added = games[games["source"] == "espn"]
    assert len(added) == 1
    assert added.iloc[0]["home_team"] == "Spurs"
    assert float(added.iloc[0]["home_score"]) == 3.0


def test_the_gap_before_the_fill_is_kept_next_to_the_gap_after(stub_tables):
    """A supplemented run must not be able to report a clean zero.

    `usable` after a supplement means "the table agrees with ESPN", which is
    trivially true of rows that came from ESPN. The pre-fill gap is what says
    how much of the table is no longer independently checked, so it stays in
    the provenance and in the one-line log.
    """
    stub_tables({"epl_games": COMMITTED, "espn_epl_games": ESPN_AHEAD})
    _, prov = sources.load_games("soccer", ["2026-27"], _labels, _dead)
    assert prov["freshness"]["missing_played"] == 1
    assert prov["freshness_after_supplement"]["missing_played"] == 0
    line = sources.describe(prov)
    assert "1 filled from ESPN (no odds)" in line
    assert "residual gap 0" in line


def test_supplemented_rows_carry_no_odds_rather_than_a_blank_that_reads_as_one(stub_tables):
    """ESPN has no odds columns at all. They must arrive as NaN, not absent.

    A concat that reshaped the frame, or a zero standing in for "unknown
    price", is how an odds-free row gets read as a free bet.
    """
    committed = COMMITTED.copy()
    committed["home_odds_decimal"] = [2.10, 1.85, 3.40, 2.75]
    committed["source"] = "football-data.co.uk"
    stub_tables({"epl_games": committed, "espn_epl_games": ESPN_AHEAD})
    games, _ = sources.load_games("soccer", ["2026-27"], _labels, _dead)
    assert list(games.columns) == list(committed.columns)
    added = games[games["source"] == "espn"]
    assert added["home_odds_decimal"].isna().all()


def test_a_fixture_the_table_already_has_is_never_re_added(stub_tables):
    """The supplement must use the audit's matcher, not an exact date equality.

    ESPN dates a late kickoff in UTC and the primary source in local time, so
    the same fixture legitimately appears a calendar day apart. Matching on
    the raw date would call it missing and append a SECOND copy of a game the
    table already has -- which double-counts that result in the Elo path, a
    silent corruption of every rating downstream of it.
    """
    espn_shifted = ESPN_SAME.copy()
    espn_shifted.loc[1, "game_date"] = "2026-09-14"
    espn_shifted.loc[1, "kickoff_utc"] = "2026-09-14T01:00:00+00:00"
    stub_tables({"epl_games": COMMITTED, "espn_epl_games": espn_shifted})
    games, prov = sources.load_games("soccer", ["2026-27"], _labels, _dead)
    assert len(games) == 4
    assert prov["usable"] is True
    assert "espn_supplement" not in prov      # no gap was ever reported


def test_a_gap_espn_cannot_fill_still_refuses_to_price(stub_tables):
    """Filling what ESPN has must not become "price anyway" when it has not.

    Here ESPN's played game is outside the requested rating seasons, so the
    season filter correctly refuses to import it -- and the residual gap must
    keep the league dark rather than pricing on a table known to be behind.
    """
    espn_other_season = ESPN_AHEAD.copy()
    espn_other_season.loc[4, "season"] = "2025-26"
    stub_tables({"epl_games": COMMITTED, "espn_epl_games": espn_other_season})
    games, prov = sources.load_games("soccer", ["2026-27"], _labels, _dead)
    assert prov["usable"] is False
    assert prov["espn_supplement"]["rows"] == 0
    assert prov["freshness_after_supplement"]["missing_played"] == 1
    assert len(games) == 4


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
    """An unfillable gap, which is the state that still stops a league."""
    stub_tables({"epl_games": COMMITTED})
    _, prov = sources.load_games("soccer", ["2026-27"], _labels, _dead)
    line = sources.describe(prov)
    assert "upstream DOWN" in line and "NOT USABLE" in line


def test_supplement_does_not_reach_backtest_loader(monkeypatch):
    """Odds-free rows must never enter a backtest sample.

    Backtests train and score against the closing line, so a row with NaN
    odds is not a game they can use -- it is a hole that some later
    `dropna`/`fillna` gets to interpret. The separation that prevents it is
    structural: `cli._load_games` reads the committed table directly and never
    calls this module, so the supplement lives only in the live pricing path.
    Asserted here because it is an invariant of the design, not of the code
    that happens to implement it today.
    """
    from sportsedge import cli

    committed = COMMITTED.copy()
    committed["source"] = "football-data.co.uk"
    monkeypatch.setattr(cli.snapshots, "read_processed",
                        lambda name: {"epl_games": committed,
                                      "espn_epl_games": ESPN_AHEAD}[name])

    def _explode(*_a, **_k):
        raise AssertionError("backtest loader must not consult ingest.sources")

    monkeypatch.setattr(sources, "load_games", _explode)

    games = cli._load_games("epl_games", ["2026-27"], _labels, _dead)
    assert len(games) == 4
    assert "espn" not in set(games["source"])


def test_a_renamed_team_is_refused_rather_than_opening_a_second_elo_entity(stub_tables):
    """The silent-corruption case, and the reason the guard is in the code.

    If ESPN renames a club, its games stop matching, so they arrive here as a
    gap to fill -- under a name the ratings book has never seen. Importing
    them would start a fresh entity at the default rating while the real one
    goes stale, and every subsequent price for that club would be wrong with
    nothing in the output to show it. Refusing leaves the gap, which takes the
    league dark with the offending name written down.
    """
    renamed = ESPN_AHEAD.copy()
    renamed.loc[4, "home_team"] = "Tottenham Hotspur"   # committed table says "Spurs"
    stub_tables({"epl_games": COMMITTED, "espn_epl_games": renamed})
    games, prov = sources.load_games("soccer", ["2026-27"], _labels, _dead)
    assert prov["usable"] is False
    assert prov["espn_supplement"]["rows"] == 0
    assert prov["espn_supplement"]["unknown_teams"] == ["Tottenham Hotspur"]
    assert len(games) == 4


def test_espn_results_reproduce_the_primary_ratings_exactly(monkeypatch):
    """The claim this whole mechanism rests on, measured on the real tables.

    Everything above is synthetic. This one takes the committed EPL table,
    truncates it to before 2026-09-11 -- the state the 09-19 fixtures would
    have left it in, with the odds source still dead -- and rebuilds the
    ratings from the ESPN supplement. If ESPN's scores, team names, dates or
    ordering differed from football-data.co.uk's in any way that mattered, the
    two rating books would part company here.

    They do not: all 30 clubs, zero difference. That is what licenses pricing
    EPL through an outage, and it is a fact about these two sources on this
    slate, so it is checked rather than assumed.
    """
    from sportsedge.models import live
    from sportsedge.storage import snapshots as real_snapshots

    real_epl = real_snapshots.read_processed("epl_games")
    real_espn = real_snapshots.read_processed("espn_epl_games")
    stale = real_epl[real_epl["game_date"].astype(str) < "2026-09-11"]
    assert len(stale) < len(real_epl), "fixture window no longer truncates anything"

    # Compare only where BOTH sources have published. As of run 19 ESPN is a
    # fixture ahead of football-data.co.uk -- it carries Brentford 3-0 Chelsea
    # (2026-09-18) and the primary still stops at 09-14 -- so an unrestricted
    # supplement builds its ratings from a game the primary has never seen and
    # the two books cannot be equal by construction. That lead is a real and
    # useful property of the supplement, asserted on its own below and pinned
    # against the ledger in test_verify_coverage.py; it is not what this test
    # is about, which is whether the two sources AGREE where they overlap.
    published_through = real_epl["game_date"].astype(str).max()
    real_espn = real_espn[real_espn["game_date"].astype(str) <= published_through]

    tables = {"epl_games": stale, "espn_epl_games": real_espn}
    monkeypatch.setattr(sources.snapshots, "read_processed", lambda n: tables[n])

    seasons = ["1920", "2021", "2122", "2223", "2324", "2425", "2526", "2627"]
    games, prov = sources.load_games(
        "soccer", seasons,
        lambda ss: {f"20{str(s)[:2]}-{str(s)[2:]}" for s in ss}, _dead)

    assert prov["usable"] is True
    assert prov["espn_supplement"]["rows"] == len(real_epl) - len(stale)
    assert prov["freshness_after_supplement"]["missing_played"] == 0
    assert "unknown_teams" not in prov["espn_supplement"]

    supplemented = live.build_soccer_model(games)[0].book.ratings
    truth = live.build_soccer_model(real_epl)[0].book.ratings
    assert set(supplemented) == set(truth)          # no phantom club
    assert max(abs(supplemented[t] - truth[t]) for t in truth) == 0.0


def test_the_espn_supplement_runs_ahead_of_the_primary_source():
    """The supplement's whole value is that it is EARLIER, not just equal.

    Run 16 verified ESPN agrees with football-data.co.uk; run 18 recorded that
    it had still never been tested against a real gap. This is that gap: ESPN
    published Brentford 3-0 Chelsea (2026-09-18) while the primary's latest
    row is 2026-09-14, and two settled wagers sit on that fixture.

    Asserted as `>=` rather than a fixed date so a backfill by the primary
    makes this go quiet instead of red -- the property being pinned is that
    the supplement is never BEHIND, which is what makes it worth consulting.
    """
    from sportsedge.storage import snapshots as real_snapshots

    primary = real_snapshots.read_processed("epl_games")
    espn = real_snapshots.read_processed("espn_epl_games")
    espn_played = espn.dropna(subset=["home_score", "away_score"])

    assert (espn_played["game_date"].astype(str).max()
            >= primary["game_date"].astype(str).max())
