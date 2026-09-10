"""Liquidity gating on Kalshi quotes.

The filter exists because `liquidity_dollars` -- the obvious field to use --
reads 0.0000 on every open NFL/EPL market sampled from the live API. These
tests pin the fields we actually rely on so a future refactor cannot quietly
fall back to the broken one.
"""
from sportsedge.ingest.kalshi import is_tradeable, _market_row, _f


def _row(**overrides):
    base = {
        "executable_prob_yes": 0.52,
        "spread_cost_frac": 0.01,
        "volume": 5000.0,
        "open_interest": 4000.0,
        "yes_bid_size": 800.0,
        "yes_ask_size": 900.0,
    }
    base.update(overrides)
    return base


def test_healthy_quote_passes():
    assert is_tradeable(_row()) is True


def test_untradeable_without_two_sided_book():
    assert is_tradeable(_row(executable_prob_yes=None)) is False


def test_rejects_thin_open_interest_and_volume():
    assert is_tradeable(_row(open_interest=10.0)) is False
    assert is_tradeable(_row(volume=10.0)) is False


def test_rejects_token_resting_size():
    # A 1-lot on each side is a quote, not liquidity.
    assert is_tradeable(_row(yes_bid_size=1.0)) is False


def test_rejects_quote_whose_spread_eats_the_edge_threshold():
    # 3.45% is the median spread cost on sub-$0.30 EPL contracts -- larger
    # than the entire 3% edge threshold, so such a quote is never bettable.
    assert is_tradeable(_row(spread_cost_frac=0.0345)) is False
    assert is_tradeable(_row(spread_cost_frac=None)) is False


def test_market_row_reads_the_fp_suffixed_fields():
    # The v2 API has no `volume`/`open_interest` keys; a refactor that looks
    # for them would silently produce all-None liquidity and gate everything.
    raw = {
        "ticker": "KXNFLGAME-26SEP21NYGLAR-NYG",
        "event_ticker": "KXNFLGAME-26SEP21NYGLAR",
        "yes_sub_title": "New York G",
        "yes_bid_dollars": "0.1700",
        "yes_ask_dollars": "0.1800",
        "volume_fp": "12345.67",
        "open_interest_fp": "8000.00",
        "yes_bid_size_fp": "300.0",
        "yes_ask_size_fp": "250.0",
        "liquidity_dollars": "0.0000",
        "status": "active",
    }
    row = _market_row(raw, "nfl", "NFL", "2026-09-10T00:00:00+00:00")
    assert row["volume"] == 12345.67
    assert row["open_interest"] == 8000.0
    assert row["yes_ask"] == 0.18
    assert row["executable_prob_yes"] == 0.18       # the ask, never the mid
    assert abs(row["implied_prob_mid"] - 0.175) < 1e-9
    assert abs(row["spread_cost_frac"] - (0.18 / 0.175 - 1)) < 1e-9


def test_f_coerces_kalshi_string_numbers():
    assert _f("0.1700") == 0.17
    assert _f(None) is None
    assert _f("not-a-number") is None
