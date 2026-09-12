import pytest

import sportsedge.betting.ledger as ledger_mod


@pytest.fixture
def tmp_ledger(tmp_path, monkeypatch):
    """An empty ledger on disk, isolated from the committed one."""
    path = tmp_path / "ledger.csv"
    monkeypatch.setattr(ledger_mod, "LEDGER_PATH", path)
    return path


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
    _add(ledger_mod.SHADOW, market_ticker="KX-A", pricing_version="p2")
    keys = ledger_mod.existing_keys()
    assert ("KX-A", "elo-v1", "p2") in keys


def test_pricing_change_is_not_deduped_against_the_old_pipeline(tmp_path, monkeypatch):
    """A pricing change must re-price open bets even when the model is static.

    Deduping on (ticker, model_version) alone is how 12 EPL rows survived the
    2026-09-10 liquidity fix: their NFL counterparts were voided and re-priced
    because NFL's model string happened to move v1 -> v2, while the soccer
    model never moved, so the stale rows were silently treated as current --
    including two on a contract the new gate rejects.
    """
    monkeypatch.setattr(ledger_mod, "LEDGER_PATH", tmp_path / "ledger.csv")
    _add(ledger_mod.SHADOW, market_ticker="KX-A", pricing_version="p1")
    keys = ledger_mod.existing_keys()

    assert ("KX-A", "elo-v1", "p1") in keys
    assert ("KX-A", "elo-v1", "p2") not in keys


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


def test_voided_bets_are_not_counted_as_pending_or_in_avg_edge(tmp_path, monkeypatch):
    """Voided rows are withdrawn evidence, not open positions.

    Counting them as pending overstated the book by 30 rows, and folding their
    prices into avg_edge_pct imported exactly the numbers the project had just
    disowned -- the two voided Hull @ Chelsea rows carried +206% and +64%
    'edges' against a book 7.7% wide.
    """
    monkeypatch.setattr(ledger_mod, "LEDGER_PATH", tmp_path / "ledger.csv")
    _add(ledger_mod.SHADOW, market_ticker="KX-OPEN", edge_pct=10.0)
    bad = _add(ledger_mod.SHADOW, market_ticker="KX-BAD", edge_pct=206.0)

    df = ledger_mod._load()
    df.loc[df["bet_id"] == bad, "status"] = "void"
    ledger_mod._save(df)

    s = ledger_mod.summarize()["shadow"]
    assert s["pending"] == 1
    assert s["void"] == 1
    assert s["total_bets"] == 1
    assert s["avg_edge_pct"] == 10.0


# -- the fee backfill: a derived column, never a re-pricing --------------------


def test_backfill_after_fee_is_derived_not_a_repricing(tmp_ledger):
    """It may add the fee-inclusive edge; it may not touch anything else.

    The 70 open bets carry run 4's pre-registered prediction, which settles
    from 2026-09-13. Computing a number those rows already implied is safe;
    changing price, stake, status or pricing_version would swap the test's
    population out from under it. This is the test that should fail if a
    future run blurs the two.
    """
    from sportsedge.betting import ledger as led

    bet_id = led.add_bet(
        sport="nfl", league="NFL", game_id="g1", matchup="A @ B", market="moneyline",
        selection="away", model_prob=0.40, model_version="v1",
        market_odds_decimal=1 / 0.30, book="kalshi", edge_pct=33.33, stake=1.0,
        market_ticker="T-1", pricing_version="p2")

    before = led._load().set_index("bet_id").loc[bet_id].to_dict()
    res = led.backfill_after_fee_edges(0.07)
    after = led._load().set_index("bet_id").loc[bet_id].to_dict()

    assert res["filled"] == 1
    # ask = 0.30, fee = 0.07 * 0.30 * 0.70 = 0.0147, so you pay 0.3147.
    assert after["edge_after_fee_pct"] == pytest.approx((0.40 / 0.3147 - 1) * 100)
    assert after["fee_assumption"] == 0.07

    untouched = ["status", "stake", "edge_pct", "market_odds_decimal", "model_prob",
                 "pricing_version", "model_version", "selection", "mode", "placed_at"]
    for col in untouched:
        assert after[col] == before[col], f"backfill must not move {col}"


def test_backfill_is_idempotent(tmp_ledger):
    from sportsedge.betting import ledger as led

    led.add_bet(sport="nfl", league="NFL", game_id="g1", matchup="A @ B",
                market="moneyline", selection="away", model_prob=0.40,
                model_version="v1", market_odds_decimal=1 / 0.30, book="kalshi",
                edge_pct=33.33, stake=1.0, market_ticker="T-1", pricing_version="p2")
    assert led.backfill_after_fee_edges(0.07)["filled"] == 1
    second = led.backfill_after_fee_edges(0.07)
    assert second["filled"] == 0 and second["skipped"] == 1


def test_backfill_dry_run_writes_nothing(tmp_ledger):
    from sportsedge.betting import ledger as led

    led.add_bet(sport="nfl", league="NFL", game_id="g1", matchup="A @ B",
                market="moneyline", selection="away", model_prob=0.40,
                model_version="v1", market_odds_decimal=1 / 0.30, book="kalshi",
                edge_pct=33.33, stake=1.0, market_ticker="T-1", pricing_version="p2")
    assert led.backfill_after_fee_edges(0.07, dry_run=True)["filled"] == 1
    assert led._load()["edge_after_fee_pct"].isna().all()
