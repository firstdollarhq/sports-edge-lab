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


def test_relative_spread_cost_rejects_what_absolute_spread_misses():
    """The gap that made this gate necessary.

    Sunderland at Man City, observed 2026-09-10: bid 0.06 / ask 0.08. The
    spread is 2c -- well inside MAX_SPREAD -- and the mid sits inside the price
    band, so every absolute check passes it. But the book is 14.3% wide in
    relative terms, which makes the de-vigged fair price we would measure
    disagreement against essentially noise.
    """
    from sportsedge.betting.liquidity import check
    row = {"yes_bid": 0.06, "yes_ask": 0.08, "implied_prob_mid": 0.07,
           "yes_ask_size": 500.0, "volume": 5000.0}
    verdict = check(row)
    assert verdict.ok is False
    assert "crossing the spread" in verdict.reason

    healthy = {"yes_bid": 0.51, "yes_ask": 0.52, "implied_prob_mid": 0.515,
               "yes_ask_size": 500.0, "volume": 5000.0}
    assert check(healthy).ok is True


def test_ordinary_width_still_passes():
    """Guards against over-tightening: this gate is a tail filter, not a tax.

    A 0.40/0.42 book is 2.4% wide and entirely normal; an earlier version of
    this gate rejected it and would have thrown away most of the live board.
    """
    from sportsedge.betting.liquidity import check
    assert check({"yes_bid": 0.40, "yes_ask": 0.42, "implied_prob_mid": 0.41,
                  "yes_ask_size": 500.0, "volume": 5000.0}).ok is True
    # 0.29/0.31 is 3.3% wide -- wider than typical, still a real market.
    assert check({"yes_bid": 0.29, "yes_ask": 0.31, "implied_prob_mid": 0.30,
                  "yes_ask_size": 900.0, "volume": 9000.0}).ok is True


def test_relative_gate_is_configurable():
    from sportsedge.betting.liquidity import check
    row = {"yes_bid": 0.06, "yes_ask": 0.08, "implied_prob_mid": 0.07,
           "yes_ask_size": 500.0, "volume": 5000.0}
    assert check(row, max_spread_cost=0.20).ok is True
