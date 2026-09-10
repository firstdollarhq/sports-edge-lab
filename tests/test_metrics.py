"""Uncertainty reporting on simulated ROI.

The point of these tests is that a positive ROI must never be reportable
without the interval around it. The EPL 2025-26 holdout (+8.27%, t=+0.84)
is the concrete case: profitable-looking, statistically empty.
"""
import math

from sportsedge.backtest.metrics import (
    log_loss,
    brier_score,
    simulate_flat_stake_roi,
    bets_needed_for_significance,
)


def _bets(n_win, n_loss, odds=3.0):
    return ([{"decimal_odds": odds, "won": True}] * n_win
            + [{"decimal_odds": odds, "won": False}] * n_loss)


def test_empty_bets_reports_no_significance_rather_than_crashing():
    r = simulate_flat_stake_roi([])
    assert r["n_bets"] == 0
    assert r["roi_pct"] is None
    assert r["significant_at_95"] is None


def test_small_positive_sample_is_not_significant():
    # 36% strike rate at 3.0 odds -> +8% ROI, but on a small sample.
    r = simulate_flat_stake_roi(_bets(36, 64))
    assert r["roi_pct"] > 0
    assert r["significant_at_95"] is False
    lo, hi = r["roi_ci95_pct"]
    assert lo < 0 < hi, "a noisy positive must report an interval spanning zero"


def test_large_consistent_loss_is_significant():
    r = simulate_flat_stake_roi(_bets(250, 1750))
    assert r["roi_pct"] < 0
    assert r["significant_at_95"] is True
    lo, hi = r["roi_ci95_pct"]
    assert hi < 0


def test_roi_matches_the_per_bet_pnl_mean():
    r = simulate_flat_stake_roi(_bets(36, 64))
    expected = (36 * 2.0 - 64 * 1.0) / 100 * 100
    assert abs(r["roi_pct"] - expected) < 1e-9


def test_t_stat_sign_follows_roi_sign():
    assert simulate_flat_stake_roi(_bets(36, 64))["roi_t_stat"] > 0
    assert simulate_flat_stake_roi(_bets(20, 80))["roi_t_stat"] < 0


def test_bets_needed_grows_as_the_edge_shrinks():
    strong = bets_needed_for_significance(_bets(40, 60))
    weak = bets_needed_for_significance(_bets(35, 65))
    assert weak > strong, "a smaller edge must take longer to resolve"


def test_bets_needed_is_none_for_a_losing_strategy():
    assert bets_needed_for_significance(_bets(10, 90)) is None


def test_log_loss_and_brier_reward_the_confident_correct_forecast():
    assert log_loss([1, 1], [0.9, 0.9]) < log_loss([1, 1], [0.6, 0.6])
    assert brier_score([1, 0], [0.9, 0.1]) < brier_score([1, 0], [0.6, 0.4])
    assert abs(log_loss([1], [1.0])) < 1e-9
    assert not math.isinf(log_loss([1], [0.0])), "clamped, must not be infinite"
