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


# --- CLV resolution: is the headline mean bigger than one tick? -------------

def test_clv_resolution_prices_one_tick_in_clv_units(tmp_path, monkeypatch):
    """A one-cent move is worth more CLV on a longshot than on a coin-flip.

    Pinned with hand-checkable numbers because the whole point of the field is
    to be compared against the CLV mean, and a wrong scale would make a real
    signal look like noise just as easily as the reverse.
    """
    monkeypatch.setattr(ledger_mod, "LEDGER_PATH", tmp_path / "ledger.csv")

    # Struck at 0.50 (decimal 2.0), closed one tick better at 0.51.
    bet = _add(ledger_mod.SHADOW, market_odds_decimal=2.0)
    ledger_mod.record_result(bet, "won", closing_odds_decimal=1.0 / 0.51)

    res = ledger_mod.summarize()["shadow"]["clv_resolution"]
    assert res["n"] == 1
    assert res["tick"] == 0.01
    assert res["mean_price_paid"] == pytest.approx(0.50)
    # One tick at a 0.50 contract is worth the decimal odds paid, 2.00% --
    # EXACTLY, not the 2.0408% this asserted until run 19. That old value was
    # `0.50 / 0.49 - 1`, the cost of buying a cent lower, which is a different
    # quantity; see `_one_tick_as_clv_pct` for the derivation.
    assert res["one_tick_as_clv_pct"] == pytest.approx(2.0, abs=1e-12)
    # The row moved exactly one tick, so |clv| is exactly one tick. The old
    # conversion made this read 0.98 and the assertion needed abs=0.05 to
    # pass; a correct conversion needs no tolerance at all.
    assert res["mean_abs_ticks"] == pytest.approx(1.0, abs=1e-12)
    assert res["share_unmoved"] == pytest.approx(0.0)


def test_clv_resolution_flags_a_ledger_that_never_moved(tmp_path, monkeypatch):
    """Half this project's settled rows closed at the price they were struck
    at, making the median CLV exactly 0.000%.

    Runs 10-12 each quoted a sub-tick CLV mean as evidence about the model.
    This asserts the counter-evidence travels with it: a ledger of unmoved
    rows must report `share_unmoved == 1` and a median of exactly zero, so a
    future run cannot read the mean without seeing what it is made of.
    """
    monkeypatch.setattr(ledger_mod, "LEDGER_PATH", tmp_path / "ledger.csv")

    for i, odds in enumerate((2.0, 3.0, 5.0)):
        bet = _add(ledger_mod.SHADOW, game_id=f"g{i}", market_odds_decimal=odds)
        ledger_mod.record_result(bet, "lost", closing_odds_decimal=odds)

    shadow = ledger_mod.summarize()["shadow"]
    assert shadow["avg_clv_pct"] == pytest.approx(0.0)
    res = shadow["clv_resolution"]
    assert res["n"] == 3
    assert res["median_clv_pct"] == 0.0
    assert res["mean_abs_ticks"] == pytest.approx(0.0)
    assert res["share_unmoved"] == pytest.approx(1.0)


def test_clv_resolution_survives_a_contract_priced_at_one_tick(tmp_path, monkeypatch):
    """A 1c contract has no CHEAPER neighbour, but it does have a dearer one.

    Under the old conversion `p / (p - tick)` this row was a division by zero
    and had to be dropped. The exact conversion has no singularity: one tick
    of movement at a 1c contract takes it to 2c, which halves the decimal odds
    and is worth 100% CLV. That is a real number and the row belongs in the
    mean, so this now asserts it is KEPT rather than skipped.
    """
    monkeypatch.setattr(ledger_mod, "LEDGER_PATH", tmp_path / "ledger.csv")

    bet = _add(ledger_mod.SHADOW, market_odds_decimal=100.0)   # 0.01
    ledger_mod.record_result(bet, "lost", closing_odds_decimal=100.0)
    other = _add(ledger_mod.SHADOW, game_id="g2", market_odds_decimal=2.0)
    ledger_mod.record_result(other, "lost", closing_odds_decimal=2.0)

    res = ledger_mod.summarize()["shadow"]["clv_resolution"]
    assert res["n"] == 2
    # Both rows contribute: 100.0% at the 1c contract, 2.0% at the 50c one.
    assert res["one_tick_as_clv_pct"] == pytest.approx(51.0, abs=1e-12)


# --- CLV in exact ticks, and how precisely the mean is known ----------------

def _set_reference_lag(lags):
    """Stamp `clv_reference_lag_h` on the settled rows, as `settle` does.

    `record_result` does not write the column -- the lag is known to the
    settlement pass, which picks the reference snapshot -- so a test that
    needs the real-close split has to set it the same way.
    """
    df = ledger_mod._load()
    df["clv_reference_lag_h"] = lags
    ledger_mod._save(df)

def test_every_settled_clv_in_the_committed_ledger_is_an_integer_tick():
    """The venue quotes whole cents, so under a correct conversion every CLV
    in `bets/ledger.csv` must be an exact integer number of ticks.

    This is the evidence that `clv_pct / placed_decimal` is the right
    conversion and `p / (p - tick) - 1` was not. It reads the committed
    ledger on purpose: a synthetic fixture would prove only that the formula
    agrees with itself, whereas this fails if the conversion drifts OR if a
    future settlement writes a CLV that no whole-cent move could produce.
    """
    import pandas as pd
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "bets" / "ledger.csv"
    df = pd.read_csv(path)
    rows = df[df["status"].isin(["won", "lost"]) & df["clv_pct"].notna()]
    assert len(rows) >= 28

    ticks = rows["clv_pct"].astype(float) / rows["market_odds_decimal"].astype(float)
    assert (ticks - ticks.round()).abs().max() < 1e-9


def test_the_old_tick_conversion_was_biased_high_and_that_biased_ticks_low(tmp_path, monkeypatch):
    """Pins the direction of the error the exact conversion replaced.

    `p / (p - tick) - 1` overstates one tick, so dividing by it understates
    how many ticks a move was -- making a real one-tick move read as less
    than a tick. For a field whose entire job is to stop sub-tick means being
    read as signal, an error in that direction is the dangerous one.
    """
    monkeypatch.setattr(ledger_mod, "LEDGER_PATH", tmp_path / "ledger.csv")

    bet = _add(ledger_mod.SHADOW, market_odds_decimal=4.0)     # 0.25
    ledger_mod.record_result(bet, "won", closing_odds_decimal=1.0 / 0.26)

    res = ledger_mod.summarize()["shadow"]["clv_resolution"]
    exact, old = 4.0, (0.25 / 0.24 - 1) * 100                  # 4.1667
    assert old > exact                                         # old ran high
    assert res["one_tick_as_clv_pct"] == pytest.approx(exact, abs=1e-12)

    # The row moved exactly one tick (0.25 -> 0.26). Under the exact
    # conversion that reads 1.000; under the old one it would have read
    # 4.0 / 4.1667 = 0.96 -- a genuine tick, reported as less than a tick.
    assert res["mean_abs_ticks"] == pytest.approx(1.0, abs=1e-12)
    assert exact / old == pytest.approx(0.96, abs=0.005)


def test_clv_precision_reports_the_interval_and_the_rows_still_needed(tmp_path, monkeypatch):
    """The mean alone cannot say whether 'no edge' is measured or merely
    unresolved, so the block carries an SE, an interval and a required n."""
    monkeypatch.setattr(ledger_mod, "LEDGER_PATH", tmp_path / "ledger.csv")

    # Four rows at 0.50, moving +1, -1, +1, -1 ticks. Mean is exactly 0 and
    # the sample sd (ddof=1) is sqrt(4/3) = 1.1547 ticks, so SE = 0.5774 and
    # n for SE = 0.25 is (1.1547/0.25)^2 = 21.3 -> 21.
    for i, close_p in enumerate((0.51, 0.49, 0.51, 0.49)):
        bet = _add(ledger_mod.SHADOW, game_id=f"g{i}", market_odds_decimal=2.0)
        ledger_mod.record_result(bet, "lost", closing_odds_decimal=1.0 / close_p)
    _set_reference_lag(0.5)

    pr = ledger_mod.summarize()["shadow"]["clv_precision_real_close"]
    assert pr["n"] == 4
    assert pr["mean_ticks"] == pytest.approx(0.0, abs=1e-12)
    import math
    sd = math.sqrt(4.0 / 3.0)
    assert pr["sd_ticks"] == pytest.approx(sd, abs=1e-12)
    assert pr["se_ticks"] == pytest.approx(sd / 2.0, abs=1e-12)
    assert pr["ci95_ticks"][0] == pytest.approx(-1.96 * sd / 2.0, abs=1e-9)
    assert pr["n_for_target_se"] == 21


def test_clv_precision_excludes_stale_references(tmp_path, monkeypatch):
    """A reference from 8 hours out is not a close. The precision block must
    describe the real-close cohort only -- the cohort the headline quotes."""
    monkeypatch.setattr(ledger_mod, "LEDGER_PATH", tmp_path / "ledger.csv")

    for i in range(4):
        bet = _add(ledger_mod.SHADOW, game_id=f"g{i}", market_odds_decimal=2.0)
        ledger_mod.record_result(bet, "lost", closing_odds_decimal=1.0 / 0.51)
    _set_reference_lag([0.4, 0.4, 8.0, 8.0])

    shadow = ledger_mod.summarize()["shadow"]
    assert shadow["clv_real_close_n"] == 2
    assert shadow["clv_precision_real_close"]["n"] == 2
    # `clv_resolution` still covers every row with a CLV; the two differ, and
    # quoting the wrong one is the error the split exists to prevent.
    assert shadow["clv_resolution"]["n"] == 4
