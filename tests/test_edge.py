from sportsedge.betting.edge import (
    american_to_decimal,
    decimal_to_implied_prob,
    devig_two_way,
    devig_three_way,
    edge_pct,
    kelly_fraction,
)


def test_american_to_decimal_favorite():
    assert american_to_decimal(-150) == 1 + 100 / 150


def test_american_to_decimal_underdog():
    assert american_to_decimal(120) == 2.2


def test_devig_two_way_sums_to_one():
    a, b = devig_two_way(0.55, 0.52)
    assert abs((a + b) - 1.0) < 1e-9
    assert a > b


def test_devig_three_way_sums_to_one():
    h, d, a = devig_three_way(0.45, 0.30, 0.32)
    assert abs((h + d + a) - 1.0) < 1e-9


def test_edge_pct_positive_when_model_beats_market():
    # Model thinks 60%, market offers 2.0 decimal (implied 50%) -> positive edge
    assert edge_pct(0.60, 2.0) > 0


def test_edge_pct_negative_when_model_below_market():
    assert edge_pct(0.40, 2.0) < 0


def test_kelly_fraction_zero_with_no_edge():
    assert kelly_fraction(0.5, 2.0) == 0.0


def test_kelly_fraction_positive_with_edge():
    f = kelly_fraction(0.6, 2.0, kelly_multiplier=1.0)
    assert abs(f - 0.2) < 1e-9  # full Kelly: (b*p - q)/b = (1*0.6-0.4)/1 = 0.2


def test_decimal_to_implied_prob():
    assert abs(decimal_to_implied_prob(2.0) - 0.5) < 1e-9
