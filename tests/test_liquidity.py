from sportsedge.betting import liquidity


def _row(**kw):
    base = {"yes_bid": 0.40, "yes_ask": 0.42, "implied_prob_mid": 0.41,
            "yes_ask_size": 500.0, "volume": 5000.0}
    base.update(kw)
    return base


def test_healthy_market_passes():
    assert liquidity.check(_row()).ok


def test_wide_spread_rejected():
    v = liquidity.check(_row(yes_bid=0.30, yes_ask=0.50, implied_prob_mid=0.40))
    assert not v.ok and "spread" in v.reason


def test_thin_ask_size_rejected():
    v = liquidity.check(_row(yes_ask_size=5.0))
    assert not v.ok and "ask size" in v.reason


def test_low_volume_rejected():
    v = liquidity.check(_row(volume=10.0))
    assert not v.ok and "volume" in v.reason


def test_extreme_price_rejected():
    v = liquidity.check(_row(yes_bid=0.005, yes_ask=0.015, implied_prob_mid=0.01))
    assert not v.ok


def test_one_sided_book_rejected():
    v = liquidity.check(_row(yes_bid=0.0))
    assert not v.ok and "one-sided" in v.reason


def test_missing_quote_rejected():
    v = liquidity.check(_row(yes_ask=None))
    assert not v.ok


def test_partition_tags_reasons():
    keep, drop = liquidity.partition([_row(), _row(volume=1.0)])
    assert len(keep) == 1 and len(drop) == 1
    assert "reject_reason" in drop[0]
