"""ESPN cross-source ingest: naming, the scheduled-game 0-0 trap, and the audit.

Network-free: every test drives `parse_scoreboard` / `audit_against_primary`
with payloads shaped like the real ones.
"""
import pandas as pd
import pytest

from sportsedge.ingest import espn


def _event(eid, date, home, away, *, hs=None, as_=None, completed=False,
           season_type=2, slug="2026-27-english-premier-league", year=2026,
           week=None):
    def side(abbr, score, ha):
        # ESPN reports "0" for a scheduled game, not null. Mirrored exactly.
        return {"homeAway": ha, "team": {"abbreviation": abbr},
                "score": "0" if score is None else str(score)}
    return {
        "id": eid,
        "date": date,
        "season": {"year": year, "type": season_type, "slug": slug},
        "week": {"number": week} if week is not None else None,
        "competitions": [{
            "competitors": [side(home, hs, "home"), side(away, as_, "away")],
            "status": {"type": {"completed": completed,
                                "name": "STATUS_FULL_TIME" if completed
                                        else "STATUS_SCHEDULED"}},
        }],
    }


# --- team naming ------------------------------------------------------------

def test_epl_manchester_pair_is_not_guessed():
    """ESPN MAN is United and MNC is City -- the opposite of Kalshi's MUN/MCI.

    Pinned because getting it backwards inverts a result silently: the fixture
    still exists, the score still parses, and every downstream check agrees
    with itself.
    """
    assert espn.canonical_team("soccer", "MAN") == "Man United"
    assert espn.canonical_team("soccer", "MNC") == "Man City"


def test_epl_abbreviations_map_onto_the_kalshi_vocabulary():
    """Both maps must land on football-data.co.uk's names, or joins silently
    produce zero rows rather than an error."""
    from sportsedge.ingest.teams import EPL_KALSHI_TO_FOOTBALL_DATA
    assert (set(espn.ESPN_EPL_TO_FOOTBALL_DATA.values())
            == set(EPL_KALSHI_TO_FOOTBALL_DATA.values()))


def test_nfl_abbreviation_differences():
    assert espn.canonical_team("nfl", "LAR") == "LA"
    assert espn.canonical_team("nfl", "WSH") == "WAS"
    assert espn.canonical_team("nfl", "KC") == "KC"


def test_unknown_team_is_loud():
    with pytest.raises(espn.EspnTeamUnknown):
        espn.canonical_team("soccer", "XYZ")
    with pytest.raises(espn.EspnTeamUnknown):
        espn.canonical_team("nfl", "XYZ")


# --- the 0-0 trap -----------------------------------------------------------

def test_scheduled_game_records_no_score():
    """A scheduled EPL event reports 0-0. Recording it would settle bets on a
    fabricated -- and entirely plausible -- draw."""
    df = espn.parse_scoreboard("soccer", {"events": [
        _event("1", "2026-09-20T14:00Z", "ARS", "CHE", completed=False)]})
    assert len(df) == 1
    assert pd.isna(df.iloc[0]["home_score"])
    assert pd.isna(df.iloc[0]["away_score"])
    assert df.iloc[0]["result"] is None
    assert bool(df.iloc[0]["completed"]) is False


def test_completed_game_records_score_and_result():
    df = espn.parse_scoreboard("soccer", {"events": [
        _event("1", "2026-09-12T14:00Z", "CRY", "IPS", hs=2, as_=3,
               completed=True)]})
    row = df.iloc[0]
    assert (row["home_score"], row["away_score"]) == (2, 3)
    assert row["result"] == "A"
    assert row["home_team"] == "Crystal Palace" and row["away_team"] == "Ipswich"


def test_genuine_nil_nil_draw_is_kept():
    """The 0-0 guard keys on `completed`, not on the score being 0-0 -- a real
    goalless draw must survive it. Liverpool 0-0 Fulham is in the ledger."""
    df = espn.parse_scoreboard("soccer", {"events": [
        _event("1", "2026-09-12T14:00Z", "LIV", "FUL", hs=0, as_=0,
               completed=True)]})
    row = df.iloc[0]
    assert (row["home_score"], row["away_score"]) == (0, 0)
    assert row["result"] == "D"


# --- NFL preseason ----------------------------------------------------------

def test_nfl_preseason_is_excluded():
    """Preseason restarts week numbering at 1, so admitting it makes `week`
    mean two different things in one committed table."""
    payload = {"events": [
        _event("pre", "2026-08-07T23:00Z", "ARI", "CAR", hs=30, as_=33,
               completed=True, season_type=1, slug=None, week=1),
        _event("reg", "2026-09-13T17:00Z", "CIN", "TB", hs=20, as_=17,
               completed=True, season_type=2, slug=None, week=1),
    ]}
    df = espn.parse_scoreboard("nfl", payload)
    assert list(df["game_id"]) == ["espn_nfl_reg"]


def test_soccer_is_not_filtered_by_nfl_season_types():
    """eng.1 season.type is a league id (14308), not pre/regular/post."""
    df = espn.parse_scoreboard("soccer", {"events": [
        _event("1", "2026-09-12T14:00Z", "ARS", "CHE", hs=1, as_=0,
               completed=True, season_type=14308)]})
    assert len(df) == 1


# --- season labels ----------------------------------------------------------

def test_season_label_matches_primary_vocabulary():
    epl = espn.parse_scoreboard("soccer", {"events": [
        _event("1", "2026-09-12T14:00Z", "ARS", "CHE", hs=1, as_=0,
               completed=True)]})
    assert epl.iloc[0]["season"] == "2026-27"     # football-data.co.uk's form

    nfl = espn.parse_scoreboard("nfl", {"events": [
        _event("2", "2026-09-13T17:00Z", "CIN", "TB", hs=1, as_=0,
               completed=True, slug=None, week=1)]})
    assert nfl.iloc[0]["season"] == "2026"        # nflverse's form


# --- the audit --------------------------------------------------------------

def _primary(rows):
    return pd.DataFrame(rows, columns=[
        "game_date", "kickoff_utc", "home_team", "away_team",
        "home_score", "away_score"])


def test_audit_reports_agreement():
    espn_df = espn.parse_scoreboard("soccer", {"events": [
        _event("1", "2026-09-12T14:00Z", "LIV", "FUL", hs=0, as_=0,
               completed=True)]})
    primary = _primary([["2026-09-12", "2026-09-12T14:00:00+00:00",
                         "Liverpool", "Fulham", 0, 0]])
    out = espn.audit_against_primary(espn_df, primary)
    assert out["compared"] == 1 and out["score_agree"] == 1
    assert out["kickoff_agree"] == 1 and out["disagreements"] == []


def test_audit_flags_a_score_disagreement():
    espn_df = espn.parse_scoreboard("soccer", {"events": [
        _event("1", "2026-09-12T14:00Z", "LIV", "FUL", hs=3, as_=1,
               completed=True)]})
    primary = _primary([["2026-09-12", "2026-09-12T14:00:00+00:00",
                         "Liverpool", "Fulham", 0, 0]])
    out = espn.audit_against_primary(espn_df, primary)
    assert out["score_disagree"] == 1
    assert out["disagreements"][0]["field"] == "score"


def test_audit_does_not_count_an_unpublished_fixture_as_a_disagreement():
    """The whole point of the source: a game the primary has not published is
    `only_espn`, not a mismatch."""
    espn_df = espn.parse_scoreboard("soccer", {"events": [
        _event("1", "2026-09-12T14:00Z", "LIV", "FUL", hs=0, as_=0,
               completed=True)]})
    out = espn.audit_against_primary(espn_df, _primary([]))
    assert out["score_disagree"] == 0
    assert out["only_espn"] == 1


def test_audit_ignores_primary_rows_outside_the_espn_window():
    """The committed tables hold every season ever ingested. Counting them all
    as `only_primary` buries the one-game gap the audit exists to surface."""
    espn_df = espn.parse_scoreboard("soccer", {"events": [
        _event("1", "2026-09-12T14:00Z", "LIV", "FUL", hs=0, as_=0,
               completed=True)]})
    primary = _primary([
        ["2026-09-12", "2026-09-12T14:00:00+00:00", "Liverpool", "Fulham", 0, 0],
        ["2019-08-10", "2019-08-10T14:00:00+00:00", "Arsenal", "Chelsea", 1, 0],
    ])
    out = espn.audit_against_primary(espn_df, primary)
    assert out["compared"] == 1
    assert out["only_primary"] == 0


def test_date_param_single_day_vs_range():
    """A start with no end is a ONE DAY request -- which silently returned an
    empty table and reported success.

    `_date_param` no longer builds the URL (ESPN 400s on the range form as of
    run 13); this pins the string that stopped working so a future run can
    re-probe it without reconstructing the format from a comment.
    """
    assert espn._date_param("2026-08-01", None) == "20260801"
    assert espn._date_param("2026-08-01", "2026-09-13") == "20260801-20260913"


def test_months_covering_spans_the_window_inclusively():
    assert espn._months_covering("2026-08-01", "2026-10-07") == ["202608", "202609", "202610"]
    assert espn._months_covering("2026-09-14", "2026-09-14") == ["202609"]


def test_months_covering_crosses_a_year_boundary():
    """An EPL season spans December. Rolling the month without rolling the
    year would fetch 202613, which is not a month."""
    assert espn._months_covering("2026-11-20", "2027-01-05") == [
        "202611", "202612", "202701"]


def test_months_covering_rejects_a_backwards_window():
    with pytest.raises(ValueError):
        espn._months_covering("2026-10-07", "2026-08-01")


def test_fetch_walks_months_and_trims_to_the_window(monkeypatch):
    """The month fetch must not leak whole calendar months into the table."""
    payloads = {
        "202608": {"events": [_event("1", "2026-08-15T14:00Z", "ARS", "CHE")]},
        "202609": {"events": [_event("2", "2026-09-05T14:00Z", "LIV", "TOT")]},
    }
    asked = []

    def fake(sport, dates, **kwargs):
        asked.append(dates)
        return payloads[dates]

    monkeypatch.setattr(espn, "fetch_espn_scoreboard", fake)
    df = espn.fetch_espn_games("soccer", "2026-08-20", "2026-09-30")

    assert asked == ["202608", "202609"]
    # The August fixture is inside the months fetched but outside the window.
    assert list(df["game_id"]) == ["espn_soccer_2"]


def test_fetch_keeps_a_late_kickoff_at_the_window_edge(monkeypatch):
    """ESPN dates an event locally; `game_date` here is UTC. A Sunday-night
    NFL kickoff lands on Monday in UTC, so a hard trim on the last day of the
    window would drop exactly the games the range form used to return."""
    monkeypatch.setattr(espn, "fetch_espn_scoreboard", lambda sport, dates, **kw: {
        "events": [_event("9", "2026-09-15T00:20Z", "LAR", "WSH", year=2026)],
    })
    df = espn.fetch_espn_games("nfl", "2026-09-01", "2026-09-14")
    assert list(df["game_id"]) == ["espn_nfl_9"]
