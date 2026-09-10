import sportsedge.betting.ledger as ledger_mod


def test_add_and_summarize_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(ledger_mod, "LEDGER_PATH", tmp_path / "ledger.csv")

    bet_id = ledger_mod.add_bet(
        sport="nfl", league="NFL", game_id="g1", matchup="KC @ BUF",
        market="moneyline", selection="home", model_prob=0.6,
        model_version="elo-v1", market_odds_decimal=2.0, book="kalshi",
        edge_pct=20.0, stake=1.0,
    )
    summary = ledger_mod.summarize()
    assert summary["total_bets"] == 1
    assert summary["settled"] == 0

    ledger_mod.record_result(bet_id, "won", closing_odds_decimal=1.9)
    summary = ledger_mod.summarize()
    assert summary["settled"] == 1
    assert summary["win_rate"] == 100.0
    assert summary["roi_pct"] > 0
