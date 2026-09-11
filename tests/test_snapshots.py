import pathlib
from datetime import datetime, timezone

from sportsedge.storage import snapshots


def _row(ticker="KXNFLGAME-26SEP21NYGLAR-NYG", fetched="2026-09-10T12:00:00+00:00", ask=0.18):
    return {
        "sport": "nfl", "league": "NFL",
        "event_ticker": "KXNFLGAME-26SEP21NYGLAR", "market_ticker": ticker,
        "game_id": None, "home_team": "LA", "away_team": "NYG",
        "expiration_time": "2026-09-22T03:15:00Z", "selection": "away",
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


# -- historical game tables ---------------------------------------------------

def test_reingesting_an_in_progress_season_fills_scores_without_duplicating(tmp_path, monkeypatch):
    """In-progress seasons get re-ingested every run as results land.

    The merge is keyed on game_id, so a fixture logged while unplayed must be
    updated in place rather than appended a second time.
    """
    import pandas as pd
    from sportsedge.storage import snapshots as snap
    monkeypatch.setattr(snap, "PROCESSED_DIR", tmp_path / "processed")

    unplayed = pd.DataFrame([{
        "game_id": "soccer_E0_2627_2026-09-20_Fulham_ManUnited",
        "season": "2026-27", "game_date": "2026-09-20",
        "home_team": "Fulham", "away_team": "Man United",
        "home_score": None, "away_score": None, "result": None,
    }])
    snap.write_processed("epl_games", unplayed)

    played = unplayed.copy()
    played.loc[0, ["home_score", "away_score", "result"]] = [1, 2, "A"]
    snap.write_processed("epl_games", played)

    df = snap.read_processed("epl_games")
    assert len(df) == 1, "same fixture must not be stored twice"
    assert df.iloc[0]["result"] == "A", "later ingest must fill in the result"


def test_read_processed_names_the_fix_when_missing(tmp_path, monkeypatch):
    import pytest
    from sportsedge.storage import snapshots as snap
    monkeypatch.setattr(snap, "PROCESSED_DIR", tmp_path / "processed")
    with pytest.raises(FileNotFoundError, match="refresh-history"):
        snap.read_processed("nfl_games")


def _game_row(game_id, **over):
    row = {"game_id": game_id, "season": "2026", "game_date": "2026-09-20",
           "home_team": "SEA", "away_team": "NE", "home_score": None,
           "away_score": None, "result": None, "home_odds_decimal": 1.5,
           "ingested_at": "2026-09-10T00:00:00+00:00"}
    row.update(over)
    return row


def test_reingest_does_not_restamp_unchanged_rows(tmp_path, monkeypatch):
    """A refresh that changes no data must produce a byte-identical file.

    `ingested_at` is a fetch timestamp, not a fact about the game. Restamping
    every row on every run rewrites the whole table, which buries the rows
    that genuinely moved under thousands of identical ones -- in a repo whose
    review mechanism is reading diffs.
    """
    import pandas as pd
    from sportsedge.storage import snapshots as snap
    monkeypatch.setattr(snap, "PROCESSED_DIR", tmp_path / "processed")

    first = pd.DataFrame([_game_row("g1"), _game_row("g2", home_team="LA")])
    path, _ = snap.write_processed("nfl_games", first)
    before = path.read_bytes()

    again = first.assign(ingested_at="2026-09-11T12:00:00+00:00")
    snap.write_processed("nfl_games", again)

    assert path.read_bytes() == before, "unchanged re-ingest must not rewrite the table"


def test_changed_row_keeps_its_new_timestamp(tmp_path, monkeypatch):
    """Only the timestamp is preserved, and only where the data is unchanged.

    The row that actually moved must still show up in the diff -- that is the
    whole point of suppressing the noise around it.
    """
    import pandas as pd
    from sportsedge.storage import snapshots as snap
    monkeypatch.setattr(snap, "PROCESSED_DIR", tmp_path / "processed")

    snap.write_processed("nfl_games", pd.DataFrame([_game_row("g1"), _game_row("g2")]))

    revised = pd.DataFrame([
        _game_row("g1", ingested_at="2026-09-11T12:00:00+00:00"),
        _game_row("g2", home_odds_decimal=1.9, ingested_at="2026-09-11T12:00:00+00:00"),
    ])
    snap.write_processed("nfl_games", revised)

    df = snap.read_processed("nfl_games").set_index("game_id")
    assert df.loc["g1", "ingested_at"] == "2026-09-10T00:00:00+00:00", "untouched row keeps old stamp"
    assert df.loc["g2", "ingested_at"] == "2026-09-11T12:00:00+00:00", "revised row takes the new stamp"
    assert df.loc["g2", "home_odds_decimal"] == 1.9, "the revision itself must survive"


def test_newly_played_fixture_is_restamped(tmp_path, monkeypatch):
    """A fixture gaining a score is a data change, so it restamps and diffs."""
    import pandas as pd
    from sportsedge.storage import snapshots as snap
    monkeypatch.setattr(snap, "PROCESSED_DIR", tmp_path / "processed")

    snap.write_processed("nfl_games", pd.DataFrame([_game_row("g1")]))
    snap.write_processed("nfl_games", pd.DataFrame([
        _game_row("g1", home_score=27, away_score=7, result="H",
                  ingested_at="2026-09-11T12:00:00+00:00")]))

    df = snap.read_processed("nfl_games").set_index("game_id")
    assert df.loc["g1", "result"] == "H"
    assert df.loc["g1", "ingested_at"] == "2026-09-11T12:00:00+00:00"


def test_one_ulp_odds_drift_is_not_a_line_move(tmp_path, monkeypatch):
    """Re-deriving decimal odds is not bit-stable; that must not read as news.

    nflverse returned the same quote as 1.3690036900369005 and then
    ...0003 -- a 1-ULP difference on 585 of 2,499 rows. A price cannot carry
    sixteen significant digits, so this is float noise, not a revision.
    """
    import pandas as pd
    from sportsedge.storage import snapshots as snap
    monkeypatch.setattr(snap, "PROCESSED_DIR", tmp_path / "processed")

    path, _ = snap.write_processed(
        "nfl_games", pd.DataFrame([_game_row("g1", home_odds_decimal=1.3690036900369005)]))
    before = path.read_bytes()

    snap.write_processed("nfl_games", pd.DataFrame([
        _game_row("g1", home_odds_decimal=1.3690036900369003,
                  ingested_at="2026-09-11T12:00:00+00:00")]))

    assert path.read_bytes() == before, "1-ULP drift must not rewrite the row"


def test_real_line_move_still_diffs(tmp_path, monkeypatch):
    """The tolerance must not swallow a move a bettor would care about."""
    import pandas as pd
    from sportsedge.storage import snapshots as snap
    monkeypatch.setattr(snap, "PROCESSED_DIR", tmp_path / "processed")

    snap.write_processed("nfl_games", pd.DataFrame([_game_row("g1", home_odds_decimal=2.02)]))
    snap.write_processed("nfl_games", pd.DataFrame([
        _game_row("g1", home_odds_decimal=1.9803921568627447,
                  ingested_at="2026-09-11T12:00:00+00:00")]))

    df = snap.read_processed("nfl_games").set_index("game_id")
    assert df.loc["g1", "home_odds_decimal"] == 1.9803921568627447
    assert df.loc["g1", "ingested_at"] == "2026-09-11T12:00:00+00:00"


def test_committed_csv_survives_a_read_write_cycle(tmp_path, monkeypatch):
    """Reading a committed table must not alter it.

    pandas' default CSV float parser is not correctly rounded: it reads
    "1.3690036900369003" back as ...005. That silently rewrote 585 of 2,499
    NFL rows on every refresh and, worse, meant the act of reading the
    irreplaceable snapshot store changed it.
    """
    import pandas as pd
    from sportsedge.storage import snapshots as snap
    monkeypatch.setattr(snap, "PROCESSED_DIR", tmp_path / "processed")

    exact = 1.3690036900369003
    path, _ = snap.write_processed("nfl_games", pd.DataFrame([
        _game_row("g1", home_odds_decimal=exact)]))

    back = snap.read_processed("nfl_games")
    assert float(back.iloc[0]["home_odds_decimal"]) == exact, "read must round-trip exactly"

    before = path.read_bytes()
    snap.write_processed("nfl_games", back)
    assert path.read_bytes() == before, "rewriting what was just read must be a no-op"


def test_snapshot_store_survives_a_read_write_cycle(tmp_path, monkeypatch):
    """Same guarantee for the odds snapshots, which cannot be re-fetched."""
    import pandas as pd
    from sportsedge.storage import snapshots as snap
    monkeypatch.setattr(snap, "SNAPSHOT_ROOT", tmp_path / "snapshots")

    row = {"sport": "nfl", "league": "NFL", "event_ticker": "E", "market_ticker": "E-X",
           "game_id": "g1", "home_team": "LA", "away_team": "SF",
           "expiration_time": "2026-09-22T03:15:00Z", "selection": "away",
           "yes_bid": 0.35, "yes_ask": 0.36, "implied_prob_mid": 0.3550000000000003,
           "spread": 0.01, "yes_bid_size": 10, "yes_ask_size": 10, "volume": 100,
           "volume_24h": 50, "open_interest": 200, "status": "active",
           "source": "kalshi", "fetched_at": "2026-09-11T12:00:00+00:00"}
    res = snap.append_snapshot([row], sport="nfl")
    path = pathlib.Path(res["path"])
    before = path.read_bytes()

    df = snap.load_snapshots("nfl")
    assert float(df.iloc[0]["implied_prob_mid"]) == 0.3550000000000003

    # Re-appending the same capture must dedupe to a byte-identical file.
    snap.append_snapshot([row], sport="nfl")
    assert path.read_bytes() == before, "re-capture must not rewrite stored prices"
