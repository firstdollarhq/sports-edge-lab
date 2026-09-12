"""Recommendation logic, including the two honesty-critical behaviours:
pricing at the ask, and only betting when the model genuinely disagrees.
"""
import pytest

from sportsedge.betting import recommend


class _FixedNfl:
    """Stand-in model with a fixed home win probability."""

    def __init__(self, p_home):
        self.p_home = p_home

    def win_prob_home(self, home, away):
        return self.p_home


class _FixedCalibrator:
    def __init__(self, probs):
        self.probs = probs

    def predict_proba(self, diff):
        return self.probs


class _FixedSoccerElo:
    def elo_diff(self, home, away):
        return 0.0


def _row(selection, bid, ask, **kw):
    base = {
        "sport": "nfl", "league": "NFL",
        "event_ticker": "KXNFLGAME-26SEP21NYGLAR",
        "market_ticker": f"KXNFLGAME-26SEP21NYGLAR-{selection.upper()}",
        "home_team": "LA", "away_team": "NYG", "selection": selection,
        "expiration_time": "2026-09-22T03:15:00Z",
        "yes_bid": bid, "yes_ask": ask, "implied_prob_mid": (bid + ask) / 2,
        "spread": round(ask - bid, 4), "yes_ask_size": 900.0, "yes_bid_size": 900.0,
        "volume": 9000.0,
    }
    base.update(kw)
    return base


def test_prices_at_ask_not_mid():
    """A model that agrees with the mid must NOT produce an edge.

    Pricing at the mid would hand the model half the spread for free, which is
    the same order of magnitude as the edges being hunted.
    """
    rows = [_row("home", 0.49, 0.51), _row("away", 0.49, 0.51)]
    recs = recommend.recommend_nfl(rows, _FixedNfl(0.50), edge_threshold=0.0)
    for r in recs:
        # 0.50 * (1/0.51) - 1 < 0
        assert r["edge_pct"] < 0 or r["market_odds_decimal"] == 1 / 0.51


def test_real_disagreement_produces_edge():
    rows = [_row("home", 0.29, 0.31), _row("away", 0.69, 0.71)]
    recs = recommend.recommend_nfl(rows, _FixedNfl(0.50), edge_threshold=0.03)
    home = [r for r in recs if r["selection"] == "home"]
    assert home, "model at 50% vs 31% ask should clear a 3% threshold"
    assert home[0]["edge_pct"] > 50
    assert home[0]["disagreement_pp"] > 0


def test_threshold_is_respected():
    rows = [_row("home", 0.49, 0.51), _row("away", 0.49, 0.51)]
    assert recommend.recommend_nfl(rows, _FixedNfl(0.52), edge_threshold=0.50) == []


def test_incomplete_event_is_skipped():
    """A one-sided event can't be de-vigged, so it must not be priced."""
    rows = [_row("home", 0.49, 0.51)]
    assert recommend.recommend_nfl(rows, _FixedNfl(0.99), edge_threshold=0.0) == []


def test_liquidity_filter_applied_by_default():
    rows = [_row("home", 0.29, 0.31, volume=1.0), _row("away", 0.69, 0.71, volume=1.0)]
    assert recommend.recommend_nfl(rows, _FixedNfl(0.50), edge_threshold=0.03) == []


def test_soccer_three_way_includes_draw():
    rows = [
        _row("home", 0.44, 0.46, sport="soccer", league="EPL"),
        _row("draw", 0.24, 0.26, sport="soccer", league="EPL"),
        _row("away", 0.29, 0.31, sport="soccer", league="EPL"),
    ]
    calib = _FixedCalibrator({"H": 0.30, "D": 0.50, "A": 0.20})
    recs = recommend.recommend_soccer(rows, _FixedSoccerElo(), calib, edge_threshold=0.03)
    assert any(r["selection"] == "draw" for r in recs)


def test_market_fair_probs_sum_to_one():
    rows = [_row("home", 0.49, 0.51), _row("away", 0.49, 0.51)]
    sides = recommend._group_events(rows)["KXNFLGAME-26SEP21NYGLAR"]
    fair = recommend._market_fair_probs(sides, "nfl")
    assert abs(sum(fair.values()) - 1.0) < 1e-9


# -- Kalshi's trading fee: reported on every row, binding on none of them ------
#
# backtest.kalshi_engine measured the fee as the LARGER of the two venue costs
# (~4.7% of stake against the spread's ~1.7%), so `edge_pct` -- computed at the
# ask alone -- overstates every edge this module logs. These pin the two halves
# of the chosen response: make the overstatement visible per row, and do NOT
# let it change which bets exist until the pre-registered week-1 prediction has
# settled. See recommend.FEE_RATE_ASSUMPTION.


def test_fee_is_quadratic_and_regressive_in_stake():
    """Flat in notional, worst as a fraction of stake on longshots."""
    assert recommend.trading_fee(0.5) == pytest.approx(recommend.FEE_RATE_ASSUMPTION * 0.25)
    assert recommend.trading_fee(0.2) == pytest.approx(recommend.trading_fee(0.8))
    as_fraction_of_stake = [recommend.trading_fee(p) / p for p in (0.15, 0.50, 0.85)]
    assert as_fraction_of_stake == sorted(as_fraction_of_stake, reverse=True)


def test_fee_rate_is_flagged_unverified():
    """Kalshi's API gives the fee's shape, not its coefficient.

    While this is False, nothing may enforce a threshold against the rate or
    present a fee-inclusive figure as settled.
    """
    assert recommend.FEE_RATE_IS_VERIFIED is False


def test_after_fee_edge_is_reported_and_lower():
    recs = recommend.recommend_nfl(
        [_row("home", 0.39, 0.40), _row("away", 0.59, 0.60)],
        _FixedNfl(0.60), edge_threshold=0.03)
    assert recs, "expected at least one flagged side"
    for r in recs:
        assert r["edge_after_fee_pct"] is not None
        assert r["edge_after_fee_pct"] < r["edge_pct"], "the fee cannot increase edge"
        assert r["fee_assumption"] == recommend.FEE_RATE_ASSUMPTION


def test_fee_does_not_change_which_bets_are_flagged():
    """The threshold still tests the pre-fee edge -- deliberately.

    Run 4 pre-registered a prediction over the 70 open bets and the slate
    settles from 2026-09-13. Moving the threshold onto the fee-inclusive number
    now would silently replace that test's population with a different one.
    When it does move, it moves as a PRICING_VERSION bump and an explicit
    re-pricing, and this test is the thing that should fail first.
    """
    # p_home = 0.416 against an ask of 0.40 is a +4.0% edge before the fee and
    # -0.2% after it: exactly the row the threshold's choice decides the fate of.
    rows = [_row("home", 0.39, 0.40), _row("away", 0.59, 0.60)]
    recs = recommend.recommend_nfl(rows, _FixedNfl(0.416), edge_threshold=0.03)
    # A side whose edge clears 3% pre-fee but not post-fee must still be logged.
    borderline = [r for r in recs
                  if r["edge_pct"] >= 3.0 > (r["edge_after_fee_pct"] or -99)]
    assert borderline, "fixture should produce a side that the fee would have cut"
    assert all(r["pricing_version"] == recommend.PRICING_VERSION for r in recs)


def test_after_fee_edge_is_none_when_there_is_no_price():
    recs = recommend.recommend_nfl(
        [_row("home", 0.0, 0.0), _row("away", 0.59, 0.60)],
        _FixedNfl(0.60), edge_threshold=0.03)
    assert all(r["selection"] != "home" for r in recs)
