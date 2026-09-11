"""Tests for the selection audit and the blend sweep.

These pin the machinery, not the conclusion. The conclusion (w* = 0 on real
data) is a finding that lives in the journal and could legitimately change;
what must not change silently is what the functions mean.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from sportsedge.backtest import selection


def _sides(rows):
    return pd.DataFrame(rows)


def _side(model_prob, fair, won, *, odds=None, flagged=None):
    odds = odds if odds is not None else 1 / fair
    from sportsedge.betting.edge import edge_fraction
    e = edge_fraction(model_prob, odds)
    return {"model_prob": model_prob, "fair_market_prob": fair, "decimal_odds": odds,
            "won": won, "edge_frac": e,
            "flagged": (e >= 0.03) if flagged is None else flagged}


def test_blend_recovers_a_model_that_genuinely_knows_more():
    """If the model IS better than the market, the sweep must say so.

    Without this the suite only ever proves the code can return w*=0, which is
    also what a broken implementation returns.
    """
    rng = np.random.default_rng(0)
    truth = rng.uniform(0.15, 0.85, 4000)
    won = rng.random(4000) < truth
    # Market is a noisy read of the truth; the model sees it exactly.
    market = np.clip(truth + rng.normal(0, 0.08, 4000), 0.02, 0.98)
    sides = _sides([_side(float(t), float(m), bool(w))
                    for t, m, w in zip(truth, market, won)])

    summary = selection.summarize_blend(selection.blend_sweep(sides))
    assert summary["model_adds_information"], "a strictly better model must beat the market"
    assert summary["best_w"] > 0.5, f"expected heavy weight on the model, got {summary['best_w']}"
    assert not summary["monotone_in_w"]


def test_blend_rejects_a_model_that_is_pure_noise():
    """A model with no information must land on w* = 0, monotonically."""
    rng = np.random.default_rng(1)
    truth = rng.uniform(0.15, 0.85, 4000)
    won = rng.random(4000) < truth
    noise = np.clip(rng.uniform(0.15, 0.85, 4000), 0.02, 0.98)
    sides = _sides([_side(float(n), float(t), bool(w))
                    for n, t, w in zip(noise, truth, won)])

    summary = selection.summarize_blend(selection.blend_sweep(sides))
    assert summary["best_w"] == 0.0
    assert not summary["model_adds_information"]
    assert summary["monotone_in_w"], "noise must make the forecast worse at every weight"


def test_blend_w_zero_is_exactly_the_market():
    sides = _sides([_side(0.5, 0.4, True), _side(0.5, 0.6, False)])
    df = selection.blend_sweep(sides)
    assert df.loc[df.w == 0.0, "vs_market"].iloc[0] == 0.0
    assert df.loc[df.w == 0.0, "n_bets"].iloc[0] == 0, "market vs itself has no edge"


def test_selection_audit_detects_the_winners_curse():
    """Flagged sides losing more than they claim must show as a negative gap."""
    # Model says 0.50 everywhere. On the sides it flags (market 0.35) it wins
    # only 30% of the time; on the sides it passes it wins 60%.
    flagged = [_side(0.50, 0.35, i < 30, odds=1 / 0.35) for i in range(100)]
    passed = [_side(0.50, 0.52, i < 60, odds=1 / 0.52) for i in range(100)]
    audit = selection.selection_audit(_sides(flagged + passed))

    assert audit["flagged"]["n"] == 100 and audit["passed"]["n"] == 100
    assert audit["flagged"]["gap"] == pytest.approx(-0.20)
    assert audit["passed"]["gap"] == pytest.approx(0.10)
    assert audit["selection_gap"] == pytest.approx(-0.30)


def test_selection_audit_reports_no_gap_when_selection_is_unbiased():
    sides = _sides([_side(0.50, 0.35, i < 50, odds=1 / 0.35) for i in range(100)]
                   + [_side(0.50, 0.52, i < 50, odds=1 / 0.52) for i in range(100)])
    audit = selection.selection_audit(sides)
    assert audit["selection_gap"] == pytest.approx(0.0)


def test_summarize_blend_flags_tempting_roi_against_its_own_log_loss():
    """A positive ROI at a weight log-loss rejects must be reported WITH that fact.

    The 2026-09-11 NFL run produced +10.19% ROI at w=0.05 on 32 bets -- from a
    weight that makes the forecast strictly worse than betting nothing. It is
    the single most quotable number in the table and it means nothing.
    """
    sides = _sides([_side(0.60, 0.50, True), _side(0.40, 0.50, False)] * 50)
    summary = selection.summarize_blend(selection.blend_sweep(sides))
    for row in summary["positive_roi_weights"]:
        assert "log_loss_vs_market" in row and "ci" in row and "n_bets" in row


def test_epl_sides_needs_a_season_to_calibrate_on():
    """One complete season is a holdout with nothing to fit the calibrator on."""
    games = pd.DataFrame(_epl_season("2024-25", 380))
    with pytest.raises(ValueError, match="2 seasons"):
        selection.epl_sides(games=games)


def test_nfl_sides_uses_the_same_walk_forward_as_the_sweep():
    """One walk-forward implementation, not two.

    Run 1's sweep lived in an uncommitted scratch file and could never be
    reconciled with a later reconstruction. A second copy of the loop is how
    that recurs, so nfl_sides must agree with run_nfl_config exactly.
    """
    from sportsedge.backtest.sweep import NflConfig, _chronological, run_nfl_config
    from sportsedge.storage import snapshots

    games = _chronological(snapshots.read_processed("nfl_games"),
                           (2018, 2019, 2020, 2021, 2022, 2023, 2024))
    cfg = NflConfig(k=20.0, home_advantage=55.0, use_mov=False, calibrate=False)
    ref = run_nfl_config(games, cfg)
    sides = selection.nfl_sides(games=games)

    assert int(sides["flagged"].sum()) == ref["n_bets"]
    assert sides["game_id"].nunique() == ref["n_games"]


def _epl_season(season, n, *, home_odds=2.0, draw_odds=3.5, away_odds=4.0):
    return [{"season": season, "game_date": f"{season[:4]}-{1 + i % 9:02d}-01",
             "game_id": f"{season}_{i}", "home_team": f"H{i % 20}", "away_team": f"A{i % 20}",
             "home_score": 1 + i % 2, "away_score": i % 2, "result": "H" if i % 2 else "D",
             "home_odds_decimal": home_odds, "draw_odds_decimal": draw_odds,
             "away_odds_decimal": away_odds} for i in range(n)]


def test_epl_holdout_skips_an_in_progress_season():
    """The holdout must be the last COMPLETE season, not simply the last one.

    Without this guard the audit held out the 30 games of 2026-27 played so
    far and reported that the model beat the market (w* = 0.75) -- a finding
    that reverses on a full season. cli._load_games documents the same trap.
    """
    games = pd.DataFrame(_epl_season("2023-24", 380) + _epl_season("2024-25", 380)
                         + _epl_season("2026-27", 30))
    sides = selection.epl_sides(games=games)
    assert set(sides["season"]) == {"2024-25"}, "must not score the in-progress season"
    assert sides["game_id"].nunique() == 380


def test_epl_holdout_refuses_when_no_season_is_complete():
    games = pd.DataFrame(_epl_season("2025-26", 40) + _epl_season("2026-27", 30))
    with pytest.raises(ValueError, match="played games"):
        selection.epl_sides(games=games)


def test_bootstrap_interval_covers_zero_for_a_worthless_model():
    """A tiny log-loss "improvement" must not be reported as information."""
    rng = np.random.default_rng(7)
    truth = rng.uniform(0.2, 0.8, 600)
    won = rng.random(600) < truth
    noise = np.clip(rng.uniform(0.2, 0.8, 600), 0.02, 0.98)
    sides = _sides([{**_side(float(n), float(t), bool(w)), "game_id": f"g{i}"}
                    for i, (n, t, w) in enumerate(zip(noise, truth, won))])

    summary = selection.summarize_blend(selection.blend_sweep(sides), sides)
    if summary["best_w"] > 0:
        lo, hi = summary["best_improvement_ci95"]
        assert lo < 0 < hi or not summary["improvement_significant"]


def test_bootstrap_interval_excludes_zero_for_a_genuinely_better_model():
    rng = np.random.default_rng(8)
    truth = rng.uniform(0.15, 0.85, 3000)
    won = rng.random(3000) < truth
    market = np.clip(truth + rng.normal(0, 0.10, 3000), 0.02, 0.98)
    sides = _sides([{**_side(float(t), float(m), bool(w)), "game_id": f"g{i}"}
                    for i, (t, m, w) in enumerate(zip(truth, market, won))])

    summary = selection.summarize_blend(selection.blend_sweep(sides), sides)
    assert summary["improvement_significant"], summary["best_improvement_ci95"]
