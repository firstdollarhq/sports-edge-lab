import sportsedge.betting.ledger as ledger_mod


def _add(mode, **kw):
    params = dict(
        sport="nfl", league="NFL", game_id="g1", matchup="KC @ BUF",
        market="moneyline", selection="home", model_prob=0.6,
        model_version="elo-v1", market_odds_decimal=2.0, book="kalshi",
        edge_pct=20.0, stake=1.0, mode=mode,
    )
    params.update(kw)
    return ledger_mod.add_bet(**params)


def test_add_and_summarize_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(ledger_mod, "LEDGER_PATH", tmp_path / "ledger.csv")

    bet_id = _add(ledger_mod.LIVE)
    summary = ledger_mod.summarize()
    assert summary["total_bets"] == 1
    assert summary["settled"] == 0
    assert summary["pending"] == 1

    ledger_mod.record_result(bet_id, "won", closing_odds_decimal=1.9)
    summary = ledger_mod.summarize()
    assert summary["settled"] == 1
    assert summary["win_rate"] == 100.0
    assert summary["roi_pct"] > 0


def test_shadow_bets_excluded_from_headline_stats(tmp_path, monkeypatch):
    """Shadow rows come from models that failed backtest.

    Folding them into the headline win rate would describe nothing real, so the
    split is enforced here.
    """
    monkeypatch.setattr(ledger_mod, "LEDGER_PATH", tmp_path / "ledger.csv")

    live_id = _add(ledger_mod.LIVE)
    shadow_id = _add(ledger_mod.SHADOW, market_ticker="T-SHADOW")
    ledger_mod.record_result(live_id, "won", closing_odds_decimal=1.9)
    ledger_mod.record_result(shadow_id, "lost", closing_odds_decimal=2.5)

    summary = ledger_mod.summarize()
    assert summary["total_bets"] == 1          # live only
    assert summary["win_rate"] == 100.0
    assert summary["shadow"]["total_bets"] == 1
    assert summary["shadow"]["win_rate"] == 0.0


def test_empty_ledger_summarizes_cleanly(tmp_path, monkeypatch):
    monkeypatch.setattr(ledger_mod, "LEDGER_PATH", tmp_path / "ledger.csv")
    summary = ledger_mod.summarize()
    assert summary["total_bets"] == 0
    assert summary["win_rate"] is None
    assert summary["shadow"]["total_bets"] == 0


def test_existing_keys_prevents_duplicate_logging(tmp_path, monkeypatch):
    monkeypatch.setattr(ledger_mod, "LEDGER_PATH", tmp_path / "ledger.csv")
    _add(ledger_mod.SHADOW, market_ticker="KX-A")
    keys = ledger_mod.existing_keys()
    assert ("KX-A", "elo-v1") in keys


def test_all_numeric_bet_id_still_settles(tmp_path, monkeypatch):
    """bet_id is 8 hex chars, so ~2% of ids are all digits.

    Read back without an explicit dtype, pandas infers int64 for those and every
    lookup by the string id misses -- settlement then raises KeyError for a
    random 2% of bets. Pinned here because it is invisible most runs.
    """
    monkeypatch.setattr(ledger_mod, "LEDGER_PATH", tmp_path / "ledger.csv")
    monkeypatch.setattr(ledger_mod.uuid, "uuid4", lambda: "80412665-dead-beef-0000-000000000000")

    bet_id = _add(ledger_mod.LIVE)
    assert bet_id == "80412665"
    ledger_mod.record_result(bet_id, "won", closing_odds_decimal=1.9)
    assert ledger_mod.summarize()["settled"] == 1


def test_clv_recorded_on_settlement(tmp_path, monkeypatch):
    monkeypatch.setattr(ledger_mod, "LEDGER_PATH", tmp_path / "ledger.csv")
    bet_id = _add(ledger_mod.LIVE)
    ledger_mod.record_result(bet_id, "won", closing_odds_decimal=1.6)
    summary = ledger_mod.summarize()
    # Bet at 2.0, closed at 1.6 -> we beat the close by 25%.
    assert summary["avg_clv_pct"] > 0
    assert summary["clv_positive_rate"] == 100.0
