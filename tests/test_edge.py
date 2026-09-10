from sportsedge.betting.edge import (
    american_to_decimal,
    decimal_to_implied_prob,
    devig_two_way,
    devig_three_way,
    edge_fraction,
    edge_percent,
    executable_price,
    mid_price,
    spread_cost_fraction,
    decimal_odds_from_price,
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


def test_edge_fraction_positive_when_model_beats_market():
    # Model thinks 60%, market offers 2.0 decimal (implied 50%) -> positive edge
    assert edge_fraction(0.60, 2.0) > 0


def test_edge_fraction_negative_when_model_below_market():
    assert edge_fraction(0.40, 2.0) < 0


def test_kelly_fraction_zero_with_no_edge():
    assert kelly_fraction(0.5, 2.0) == 0.0


def test_kelly_fraction_positive_with_edge():
    f = kelly_fraction(0.6, 2.0, kelly_multiplier=1.0)
    assert abs(f - 0.2) < 1e-9  # full Kelly: (b*p - q)/b = (1*0.6-0.4)/1 = 0.2


def test_decimal_to_implied_prob():
    assert abs(decimal_to_implied_prob(2.0) - 0.5) < 1e-9


def test_edge_percent_is_exactly_one_hundred_times_the_fraction():
    # The whole point of the rename: these are different units and must not
    # be confusable. 0.20 vs 20.0 written into the same ledger column was the
    # latent corruption this guards against.
    assert abs(edge_percent(0.60, 2.0) - 100 * edge_fraction(0.60, 2.0)) < 1e-9
    assert abs(edge_fraction(0.60, 2.0) - 0.20) < 1e-9
    assert abs(edge_percent(0.60, 2.0) - 20.0) < 1e-9


def test_executable_price_is_the_ask_not_the_mid():
    assert executable_price(0.17, 0.18, "yes") == 0.18
    assert abs(mid_price(0.17, 0.18) - 0.175) < 1e-9


def test_executable_price_for_no_side_hits_the_yes_bid():
    assert abs(executable_price(0.17, 0.18, "no") - 0.83) < 1e-9


def test_executable_price_rejects_one_sided_or_crossed_book():
    assert executable_price(None, 0.18) is None
    assert executable_price(0.0, 0.0) is None
    assert executable_price(0.50, 0.50) is None   # zero-width book is not real
    assert executable_price(0.60, 0.50) is None   # crossed


def test_spread_cost_matches_the_edge_it_destroys():
    # Real observed market: Sunderland at MCI, bid 0.06 / ask 0.08.
    cost = spread_cost_fraction(0.06, 0.08)
    assert abs(cost - (0.08 / 0.07 - 1)) < 1e-9
    assert cost > 0.14  # >14%: five times the 3% edge threshold

    # And it is exactly the gap between mid-priced and ask-priced edge.
    p = 0.30
    mid_edge = edge_fraction(p, decimal_odds_from_price(0.07))
    ask_edge = edge_fraction(p, decimal_odds_from_price(0.08))
    assert abs((1 + mid_edge) / (1 + ask_edge) - (1 + cost)) < 1e-9
    assert mid_edge > ask_edge


def test_decimal_odds_from_price_rejects_impossible_prices():
    import pytest
    assert abs(decimal_odds_from_price(0.25) - 4.0) < 1e-9
    for bad in (0.0, 1.0, -0.1, 1.5):
        with pytest.raises(ValueError):
            decimal_odds_from_price(bad)
