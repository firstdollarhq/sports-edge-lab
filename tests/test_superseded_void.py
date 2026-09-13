"""A pricing-version bump must REPLACE a row, not duplicate it.

`existing_keys` includes `pricing_version` so that a bump makes a contract
eligible to be priced again. That is the insert half. Until 2026-09-13 there
was no other half: the superseded row stayed open, so the p1 -> p2 bump turned
35 wagers into 70 rows and every count published over the ledger -- pending
totals, the size of the pre-registered population, n in every CI -- was
inflated. These tests pin the replacement.
"""
import pandas as pd
import pytest

from sportsedge.betting import ledger
from sportsedge.betting.recommend import PRICING_VERSIONS, PRICING_VERSION


ORDER = ("p1", "p2", "p3")


@pytest.fixture
def tmp_ledger(tmp_path, monkeypatch):
    path = tmp_path / "ledger.csv"
    monkeypatch.setattr(ledger, "LEDGER_PATH", path)
    return path


def _row(**kw):
    base = dict(sport="soccer", league="EPL", game_id="G", matchup="A @ B",
                market="moneyline", selection="home", model_prob=0.5,
                model_version="m1", market_odds_decimal=2.0, book="kalshi",
                edge_pct=5.0, stake=1.0)
    base.update(kw)
    return ledger.add_bet(**base)


def test_declared_version_order_is_not_a_string_sort():
    """'p10' < 'p2' lexicographically. The order must be declared, not sorted."""
    assert PRICING_VERSIONS == tuple(PRICING_VERSIONS)
    assert PRICING_VERSION == PRICING_VERSIONS[-1]
    assert list(PRICING_VERSIONS) == sorted(PRICING_VERSIONS, key=PRICING_VERSIONS.index)


def test_the_older_half_is_voided_and_the_newer_survives(tmp_ledger):
    old = _row(market_ticker="T1", pricing_version="p1", market_odds_decimal=7.7)
    new = _row(market_ticker="T1", pricing_version="p2", market_odds_decimal=8.3)

    res = ledger.void_superseded_rows(ORDER)
    assert res["voided"] == 1

    df = pd.read_csv(tmp_ledger, dtype={"bet_id": str})
    assert df.set_index("bet_id").loc[old, "status"] == "void"
    assert df.set_index("bet_id").loc[new, "status"] == "pending"


def test_a_settled_duplicate_is_voided_too(tmp_ledger):
    """The double-count does its damage in win rate and ROI, which only
    settled rows reach. Sparing them would leave the defect where it counts."""
    old = _row(market_ticker="T1", pricing_version="p1")
    _row(market_ticker="T1", pricing_version="p2")
    ledger.record_result(old, "won")

    ledger.void_superseded_rows(ORDER)
    df = pd.read_csv(tmp_ledger, dtype={"bet_id": str})
    assert df.set_index("bet_id").loc[old, "status"] == "void"
    assert (df["status"] == "void").sum() == 1


def test_a_contract_never_re_priced_is_left_alone(tmp_ledger):
    """A p1 row with no p2 successor is not superseded by anything. The
    project's one settled NFL win is exactly this row."""
    solo = _row(market_ticker="T1", pricing_version="p1")
    ledger.record_result(solo, "won")
    res = ledger.void_superseded_rows(ORDER)
    assert res["voided"] == 0
    df = pd.read_csv(tmp_ledger, dtype={"bet_id": str})
    assert df.set_index("bet_id").loc[solo, "status"] == "won"


def test_different_selections_on_one_contract_are_different_wagers(tmp_ledger):
    """Grouping on the ticker alone would void a live bet on the other side."""
    _row(market_ticker="T1", pricing_version="p2", selection="home")
    _row(market_ticker="T1", pricing_version="p2", selection="draw")
    assert ledger.void_superseded_rows(ORDER)["voided"] == 0


def test_a_model_bump_is_not_a_pricing_bump(tmp_ledger):
    """Rows under different model versions are different wagers; the model
    bump has its own void path and must not be double-handled here."""
    _row(market_ticker="T1", pricing_version="p2", model_version="m1")
    _row(market_ticker="T1", pricing_version="p2", model_version="m2")
    assert ledger.void_superseded_rows(ORDER)["voided"] == 0


def test_an_unknown_version_is_reported_not_guessed_at(tmp_ledger):
    """Guessing the order is how the correct row gets voided in favour of the
    superseded one. An unrecognised version leaves the group untouched."""
    a = _row(market_ticker="T1", pricing_version="p1")
    b = _row(market_ticker="T1", pricing_version="pX")
    res = ledger.void_superseded_rows(ORDER)
    assert res["voided"] == 0
    assert len(res["unorderable"]) == 1
    df = pd.read_csv(tmp_ledger, dtype={"bet_id": str}).set_index("bet_id")
    assert df.loc[a, "status"] == "pending" and df.loc[b, "status"] == "pending"


def test_it_is_idempotent(tmp_ledger):
    _row(market_ticker="T1", pricing_version="p1")
    _row(market_ticker="T1", pricing_version="p2")
    assert ledger.void_superseded_rows(ORDER)["voided"] == 1
    assert ledger.void_superseded_rows(ORDER)["voided"] == 0
    assert ledger.void_superseded_rows(ORDER)["voided"] == 0


def test_already_void_rows_are_not_reconsidered(tmp_ledger):
    """A row voided for an unrelated reason (in-play pricing, superseded
    model) must not be resurrected into a supersede group."""
    _row(market_ticker="T1", pricing_version="p1")
    _row(market_ticker="T1", pricing_version="p2")
    ledger.void_superseded_rows(ORDER)
    before = pd.read_csv(tmp_ledger)["notes"].tolist()
    ledger.void_superseded_rows(ORDER)
    assert pd.read_csv(tmp_ledger)["notes"].tolist() == before


def test_dry_run_writes_nothing(tmp_ledger):
    _row(market_ticker="T1", pricing_version="p1")
    _row(market_ticker="T1", pricing_version="p2")
    before = tmp_ledger.read_text()
    res = ledger.void_superseded_rows(ORDER, dry_run=True)
    assert res["voided"] == 1
    assert tmp_ledger.read_text() == before


def test_it_never_changes_a_price_selection_or_outcome(tmp_ledger):
    """The correction is a de-duplication, not a re-pricing. Only `status`,
    `notes` and `result_logged_at` may move on the voided row, and nothing at
    all may move on the survivor."""
    _row(market_ticker="T1", pricing_version="p1", market_odds_decimal=7.7)
    _row(market_ticker="T1", pricing_version="p2", market_odds_decimal=8.3)
    before = pd.read_csv(tmp_ledger, dtype={"bet_id": str}).set_index("bet_id")
    ledger.void_superseded_rows(ORDER)
    after = pd.read_csv(tmp_ledger, dtype={"bet_id": str}).set_index("bet_id")

    mutable = {"status", "notes", "result_logged_at"}
    for col in before.columns:
        if col in mutable:
            continue
        pd.testing.assert_series_equal(before[col], after[col], check_dtype=False)
