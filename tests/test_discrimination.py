"""Discrimination vs calibration, and the one-sided oracle bound.

The headline claim this module supports -- "no recalibration-shaped change can
fix the NFL leg" -- rests on AUC being invariant under monotone transforms.
That invariance is asserted directly here rather than taken on faith, because
the whole argument collapses without it.
"""
import numpy as np
import pytest

from sportsedge.backtest import discrimination as disc


def _synthetic(n=800, seed=3):
    rng = np.random.default_rng(seed)
    p = rng.uniform(0.05, 0.95, n)
    y = (rng.uniform(size=n) < p).astype(int)
    return y, p


def test_auc_is_invariant_under_monotone_recalibration():
    """The load-bearing fact. If this fails the module's conclusion is void."""
    y, p = _synthetic()
    base = disc.auc(y, p)

    for transform in (lambda x: x ** 3,
                      lambda x: np.sqrt(x),
                      lambda x: 0.5 * x + 0.25,          # shrink toward 0.5
                      lambda x: 1 / (1 + np.exp(-4 * (x - 0.5)))):
        assert disc.auc(y, transform(p)) == pytest.approx(base, abs=1e-12)


def test_auc_matches_known_orderings():
    assert disc.auc([0, 1], [0.1, 0.9]) == 1.0
    assert disc.auc([0, 1], [0.9, 0.1]) == 0.0
    assert disc.auc([0, 1], [0.5, 0.5]) == 0.5


def test_murphy_decomposition_reconstructs_the_brier_score():
    y, p = _synthetic()
    d = disc.murphy_decomposition(y, p, bins=10)
    # Brier = reliability - resolution + uncertainty, up to binning error.
    assert d["reliability"] - d["resolution"] + d["uncertainty"] == pytest.approx(
        d["brier"], abs=5e-3)
    assert d["reliability"] >= 0 and d["resolution"] >= 0


def test_a_well_calibrated_forecast_has_near_zero_reliability():
    y, p = _synthetic(n=4000)
    assert disc.murphy_decomposition(y, p)["reliability"] < 0.01


def test_recalibration_cannot_raise_resolution_but_can_cut_reliability():
    """The asymmetry the whole module exists to make legible."""
    y, p = _synthetic(n=3000)
    miscalibrated = np.clip(p * 0.5 + 0.3, 1e-6, 1 - 1e-6)  # same order, bad numbers

    bad = disc.murphy_decomposition(y, miscalibrated)
    good = disc.murphy_decomposition(y, p)

    assert bad["reliability"] > good["reliability"]
    assert disc.auc(y, miscalibrated) == pytest.approx(disc.auc(y, p), abs=1e-12)


def test_bootstrap_is_seeded_and_reproducible():
    y, p = _synthetic()
    _, q = _synthetic(seed=9)
    a = disc.auc_gap_bootstrap(y, p, q, draws=300)
    b = disc.auc_gap_bootstrap(y, p, q, draws=300)
    assert a == b


def test_identical_forecasts_give_a_zero_gap():
    y, p = _synthetic()
    out = disc.auc_gap_bootstrap(y, p, p.copy(), draws=200)
    assert out["gap"] == pytest.approx(0.0, abs=1e-12)
    assert out["ci95"][0] <= 0 <= out["ci95"][1]


def test_verdict_does_not_call_a_significant_gap_insignificant():
    """Regression: the EPL leg (CI entirely below 0, but the oracle bound met)
    was reported as 'no significant ranking difference', contradicting its own
    interval."""
    boot = {"ci95": [-0.039, -0.002]}
    v = disc._verdict(boot, oracle=0.57, market_ll=0.59)
    assert "significantly WORSE" in v
    assert "no significant" not in v
    assert "in-sample" in v, "must flag that the oracle bound proves nothing here"


def test_verdict_is_conclusive_when_the_oracle_bound_fails():
    boot = {"ci95": [-0.064, -0.029]}
    v = disc._verdict(boot, oracle=0.635, market_ll=0.610)
    assert "Conclusive" in v


def test_verdict_reports_a_genuinely_better_model():
    assert "BETTER" in disc._verdict({"ci95": [0.01, 0.05]}, oracle=0.5, market_ll=0.6)


def test_report_handles_games_with_no_market_price():
    preds = [{"game_id": "g1", "y": 1, "p_model": 0.6, "p_market": None},
             {"game_id": "g2", "y": 0, "p_model": 0.4, "p_market": None}]
    out = disc.discrimination_report(preds)
    assert out["n"] == 0 and "note" in out


def test_engines_expose_per_game_predictions():
    """The report reads the engine's own loop; a second copy of the
    walk-forward loop is what this repo's history warns about."""
    import pandas as pd
    from sportsedge.backtest.engine import backtest_nfl
    from sportsedge.models.elo import NflEloModel

    games = pd.DataFrame([{
        "game_id": f"g{w}", "season": "2023", "week": w,
        "game_date": f"2023-09-{w:02d}", "home_team": "AAA", "away_team": "BBB",
        "home_score": 21, "away_score": 17, "result": "H",
        "home_odds_decimal": 1.9, "away_odds_decimal": 2.1,
    } for w in range(1, 6)])

    res = backtest_nfl(games, NflEloModel())
    assert len(res["predictions"]) == 5
    row = res["predictions"][0]
    assert set(row) == {"game_id", "y", "p_model", "p_market"}
    assert row["p_market"] is not None, "a priced game must carry a market probability"
