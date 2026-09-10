"""Durability of the committed odds record.

CLV cannot be backfilled: a pre-kickoff quote that was not written down is
gone. These tests cover the two ways that record could silently lose data --
an overwrite that drops earlier observations, and a merge that duplicates or
clobbers rows when an in-progress season is re-ingested.
"""
import pandas as pd

from sportsedge.storage import snapshots


def _quote(ticker, fetched_at, ask=0.52):
    return {
        "sport": "nfl", "league": "NFL", "event_ticker": "EV1",
        "market_ticker": ticker, "selection": "Kansas City",
        "yes_bid": ask - 0.01, "yes_ask": ask, "implied_prob_mid": ask - 0.005,
        "executable_prob_yes": ask, "spread_cost_frac": 0.01,
        "volume": 1000.0, "open_interest": 900.0,
        "yes_bid_size": 100.0, "yes_ask_size": 100.0,
        "status": "active", "source": "kalshi", "fetched_at": fetched_at,
    }


def test_second_snapshot_same_day_is_kept_not_overwritten(tmp_path, monkeypatch):
    monkeypatch.setattr(snapshots, "SNAPSHOT_DIR", tmp_path / "snapshots")

    snapshots.write_snapshot([_quote("M1", "2026-09-10T12:00:00+00:00", 0.52)], day="2026-09-10")
    snapshots.write_snapshot([_quote("M1", "2026-09-10T18:00:00+00:00", 0.57)], day="2026-09-10")

    df = pd.read_csv(snapshots.snapshot_path("2026-09-10"))
    assert len(df) == 2, "intraday price movement must not be overwritten"
    assert sorted(df["yes_ask"]) == [0.52, 0.57]


def test_identical_reobservation_is_deduplicated(tmp_path, monkeypatch):
    monkeypatch.setattr(snapshots, "SNAPSHOT_DIR", tmp_path / "snapshots")
    row = _quote("M1", "2026-09-10T12:00:00+00:00")
    snapshots.write_snapshot([row], day="2026-09-10")
    snapshots.write_snapshot([row], day="2026-09-10")
    assert len(pd.read_csv(snapshots.snapshot_path("2026-09-10"))) == 1


def test_load_snapshots_spans_multiple_days(tmp_path, monkeypatch):
    monkeypatch.setattr(snapshots, "SNAPSHOT_DIR", tmp_path / "snapshots")
    snapshots.write_snapshot([_quote("M1", "2026-09-09T12:00:00+00:00")], day="2026-09-09")
    snapshots.write_snapshot([_quote("M1", "2026-09-10T12:00:00+00:00")], day="2026-09-10")
    assert len(snapshots.load_snapshots()) == 2


def test_reingesting_an_in_progress_season_fills_scores_without_duplicating(tmp_path, monkeypatch):
    monkeypatch.setattr(snapshots, "PROCESSED_DIR", tmp_path / "processed")

    unplayed = pd.DataFrame([{
        "game_id": "soccer_E0_2627_2026-09-20_Fulham_ManUnited",
        "season": "2026-27", "game_date": "2026-09-20",
        "home_team": "Fulham", "away_team": "Man United",
        "home_score": None, "away_score": None, "result": None,
    }])
    snapshots.write_processed("epl_games", unplayed)

    played = unplayed.copy()
    played.loc[0, ["home_score", "away_score", "result"]] = [1, 2, "A"]
    snapshots.write_processed("epl_games", played)

    df = snapshots.read_processed("epl_games")
    assert len(df) == 1, "same fixture must not be stored twice"
    assert df.loc[0, "result"] == "A", "later ingest must fill in the result"


def test_read_processed_names_the_fix_when_missing(tmp_path, monkeypatch):
    import pytest
    monkeypatch.setattr(snapshots, "PROCESSED_DIR", tmp_path / "processed")
    with pytest.raises(FileNotFoundError, match="refresh-history"):
        snapshots.read_processed("nfl_games")
