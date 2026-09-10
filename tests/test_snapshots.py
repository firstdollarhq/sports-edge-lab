from datetime import datetime, timezone

from sportsedge.storage import snapshots


def _row(ticker="KXNFLGAME-26SEP21NYGLAR-NYG", fetched="2026-09-10T12:00:00+00:00", ask=0.18):
    return {
        "sport": "nfl", "league": "NFL",
        "event_ticker": "KXNFLGAME-26SEP21NYGLAR", "market_ticker": ticker,
        "game_id": None, "home_team": "LA", "away_team": "NYG",
        "commence_time": "2026-09-22T03:15:00Z", "selection": "away",
        "yes_bid": 0.17, "yes_ask": ask, "implied_prob_mid": 0.175, "spread": 0.01,
        "yes_bid_size": 1000.0, "yes_ask_size": 700.0, "volume": 6000.0,
        "volume_24h": 1200.0, "open_interest": 5000.0, "status": "active",
        "source": "kalshi", "fetched_at": fetched,
    }


def test_append_and_load(tmp_path, monkeypatch):
    monkeypatch.setattr(snapshots, "SNAPSHOT_ROOT", tmp_path)
    res = snapshots.append_snapshot([_row()], sport="nfl",
                                    now=datetime(2026, 9, 10, tzinfo=timezone.utc))
    assert res["written"] == 1
    assert len(snapshots.load_snapshots("nfl")) == 1


def test_same_minute_is_deduped(tmp_path, monkeypatch):
    monkeypatch.setattr(snapshots, "SNAPSHOT_ROOT", tmp_path)
    now = datetime(2026, 9, 10, tzinfo=timezone.utc)
    snapshots.append_snapshot([_row()], sport="nfl", now=now)
    snapshots.append_snapshot([_row()], sport="nfl", now=now)
    assert len(snapshots.load_snapshots("nfl")) == 1


def test_later_minute_is_kept_as_new_observation(tmp_path, monkeypatch):
    monkeypatch.setattr(snapshots, "SNAPSHOT_ROOT", tmp_path)
    now = datetime(2026, 9, 10, tzinfo=timezone.utc)
    snapshots.append_snapshot([_row(fetched="2026-09-10T12:00:00+00:00")], sport="nfl", now=now)
    snapshots.append_snapshot([_row(fetched="2026-09-10T13:30:00+00:00", ask=0.22)],
                              sport="nfl", now=now)
    assert len(snapshots.load_snapshots("nfl")) == 2


def test_latest_before_picks_last_pre_kickoff_quote(tmp_path, monkeypatch):
    monkeypatch.setattr(snapshots, "SNAPSHOT_ROOT", tmp_path)
    now = datetime(2026, 9, 10, tzinfo=timezone.utc)
    snapshots.append_snapshot([
        _row(fetched="2026-09-10T10:00:00+00:00", ask=0.20),
        _row(fetched="2026-09-10T20:00:00+00:00", ask=0.25),
        _row(fetched="2026-09-23T10:00:00+00:00", ask=0.99),  # after kickoff
    ], sport="nfl", now=now)

    row = snapshots.latest_before("nfl", "KXNFLGAME-26SEP21NYGLAR-NYG",
                                 "2026-09-22T03:15:00Z")
    assert row is not None
    assert row["yes_ask"] == 0.25


def test_latest_before_returns_none_when_no_history(tmp_path, monkeypatch):
    monkeypatch.setattr(snapshots, "SNAPSHOT_ROOT", tmp_path)
    assert snapshots.latest_before("nfl", "missing", "2026-09-22T03:15:00Z") is None
