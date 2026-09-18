"""Tests for the context-feature experiment.

The load-bearing one is `test_elo_only_tier_ties_baseline_within_every_season`.
A logistic regression on elo_diff alone is a strictly monotone transform of
elo_diff, so it must rank games identically to baseline Elo. If it does not,
the harness is leaking -- a refit on the wrong side of a season boundary, a
feature standardised using the test set, a non-chronological sort -- and every
other number the report prints is void.

That invariance holds WITHIN a season and not across them, which run 12 found
by asserting the pooled version first and watching it fail. The model refits at
each season boundary, so the evaluation window is five different monotone
transforms; pooling them is not a monotone transform of anything. Both facts
are pinned below, because the pooled gap is not a bug to be fixed but a
confound to be measured -- and `test_pooled_control_moves_and_that_is_expected`
is what stops a future run from "fixing" it by loosening the real assertion.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from sportsedge.backtest import benchmarks
from sportsedge.backtest.context import run_tier, context_report
from sportsedge.backtest.discrimination import auc
from sportsedge.backtest.engine import backtest_nfl
from sportsedge.models.elo import NflEloModel
from sportsedge.models.features import (ContextFeatureModel, TIER_ELO_ONLY,
                                        TIER_SCHEDULE, TIER_QB, _is_outdoor, _f)
from sportsedge.storage import snapshots


def _nfl_games():
    df = snapshots.read_processed("nfl_games")
    wanted = {str(s) for s in benchmarks.NFL_SEASONS}
    return df[df["season"].astype(str).isin(wanted)]


# -- the control --------------------------------------------------------------

def test_elo_only_tier_ties_baseline_within_every_season():
    """The assertion the rest of the experiment rests on.

    Exact equality, not approx: within one fit this is the same monotone
    transform applied to the same numbers, so the ranks are identical or
    something is wrong.
    """
    out = context_report(_nfl_games(), tiers=(TIER_ELO_ONLY,))
    control = out["per_season_control"]
    assert control["seasons"], "control produced no seasons to check"
    for row in control["seasons"]:
        assert row["auc_elo_only"] == row["auc_baseline"], (
            f"season {row['season']}: a pure recalibration reordered games "
            f"within a single fit (delta {row['delta']!r})")
    assert control["ok"] is True
    assert out["control_ok"] is True


def test_pooled_control_moves_and_that_is_expected():
    """Guards the finding, not the code.

    The seasonal refit makes the POOLED control differ from baseline even
    though every season ties. That is the confound `vs_elo_only` exists to
    remove; if a future change makes it vanish, the refit boundary has moved
    and the yardstick needs revisiting rather than quietly still being used.
    """
    out = context_report(_nfl_games(), tiers=(TIER_ELO_ONLY,))
    effect = out["pooled_seasonal_refit_auc_effect"]
    assert effect is not None
    assert effect != 0.0
    # Two orders of magnitude short of the -0.046 model-vs-market gap: real,
    # but nowhere near large enough to rescue the recalibration family.
    assert abs(effect) < 0.01


# -- the context model must not disturb the baseline --------------------------

def test_attaching_a_context_model_leaves_the_canonical_numbers_untouched():
    """`context_model` is observational. If it can move a headline number it is
    not observational, and six runs of 'digit-for-digit' claims are affected."""
    games = _nfl_games()
    plain = backtest_nfl(games, NflEloModel())
    withctx = backtest_nfl(games, NflEloModel(),
                           context_model=ContextFeatureModel(TIER_QB))
    assert withctx["log_loss"] == plain["log_loss"] == benchmarks.NFL_LOG_LOSS
    assert withctx["roi"]["roi_pct"] == plain["roi"]["roi_pct"] == benchmarks.NFL_ROI_PCT
    assert withctx["n_games"] == plain["n_games"] == benchmarks.NFL_N_GAMES
    assert len(withctx["bets"]) == len(plain["bets"]) == benchmarks.NFL_N_BETS
    # The Elo path itself must be bit-identical game by game, not merely
    # equal in aggregate.
    assert ([p["p_model"] for p in withctx["predictions"]]
            == [p["p_model"] for p in plain["predictions"]])


# -- no lookahead -------------------------------------------------------------

def test_no_prediction_before_a_fit_exists():
    """Burn-in games must return None, not a prediction from an empty fit."""
    m = ContextFeatureModel(TIER_SCHEDULE, min_train_games=400)
    row = pd.Series({"home_team": "KC", "away_team": "DEN", "home_rest": 7,
                     "away_rest": 7, "div_game": 1, "neutral_site": 0,
                     "roof": "outdoors", "temp": 40.0, "wind": 10.0,
                     "home_qb_id": "A", "away_qb_id": "B"})
    assert m.predict(row, 50.0) is None
    for _ in range(399):
        m.observe(row, 50.0, 1)
    assert m.start_season() is False
    assert m.predict(row, 50.0) is None


def test_fit_refuses_a_single_class():
    """400 home wins and no losses is not a fit, it is a constant."""
    m = ContextFeatureModel(TIER_SCHEDULE, min_train_games=10)
    row = pd.Series({"home_team": "KC", "away_team": "DEN", "home_rest": 7,
                     "away_rest": 7, "div_game": 0, "neutral_site": 0})
    for _ in range(50):
        m.observe(row, 10.0, 1)
    assert m.start_season() is False


def test_qb_change_never_reads_a_future_start():
    m = ContextFeatureModel(TIER_QB, min_train_games=10)
    g1 = pd.Series({"home_team": "KC", "away_team": "DEN",
                    "home_qb_id": "mahomes", "away_qb_id": "wilson"})
    # First sighting of either team is an absence of evidence, not a change.
    assert m.features(g1, 0.0)[-2:] == [0.0, 0.0]
    m.observe(g1, 0.0, 1)
    g2 = pd.Series({"home_team": "KC", "away_team": "LV",
                    "home_qb_id": "mahomes", "away_qb_id": "carr"})
    assert m.features(g2, 0.0)[-2] == 0.0          # same starter
    g3 = pd.Series({"home_team": "KC", "away_team": "LV",
                    "home_qb_id": "backup", "away_qb_id": "carr"})
    assert m.features(g3, 0.0)[-2] == 1.0          # starter changed


def test_predictions_carry_context_only_when_a_model_is_attached():
    games = _nfl_games()
    plain = backtest_nfl(games, NflEloModel())
    assert "p_context" not in plain["predictions"][0]
    withctx = backtest_nfl(games, NflEloModel(),
                           context_model=ContextFeatureModel(TIER_SCHEDULE))
    assert "p_context" in withctx["predictions"][0]


# -- feature encoding ---------------------------------------------------------

def test_indoor_games_carry_no_weather():
    m = ContextFeatureModel("weather", min_train_games=10)
    indoor = pd.Series({"home_team": "DET", "away_team": "CHI", "home_rest": 7,
                        "away_rest": 7, "div_game": 1, "neutral_site": 0,
                        "roof": "dome", "temp": np.nan, "wind": np.nan})
    feats = dict(zip(m.feature_names, m.features(indoor, 0.0)))
    assert feats["is_outdoor"] == 0.0
    assert feats["wind_mph"] == 0.0
    assert feats["temp_dev"] == 0.0


def test_roof_states_map_to_exposure():
    assert _is_outdoor("outdoors") is True
    assert _is_outdoor("open") is True       # retractable, and it was open
    assert _is_outdoor("closed") is False
    assert _is_outdoor("dome") is False
    assert _is_outdoor(None) is False
    assert _is_outdoor(np.nan) is False


def test_missing_values_fall_back_rather_than_producing_nan():
    """A NaN reaching the fit poisons the whole coefficient vector silently."""
    m = ContextFeatureModel(TIER_QB, min_train_games=10)
    sparse = pd.Series({"home_team": "KC", "away_team": "DEN"})
    feats = m.features(sparse, 25.0)
    assert not any(np.isnan(v) for v in feats)
    assert _f(pd.NA, 7.0) == 7.0
    assert _f(np.nan, 7.0) == 7.0
    assert _f(None, 7.0) == 7.0


def test_short_week_flag_matches_rest_days():
    m = ContextFeatureModel(TIER_SCHEDULE, min_train_games=10)
    thursday = pd.Series({"home_team": "A", "away_team": "B", "home_rest": 4,
                          "away_rest": 7, "div_game": 0, "neutral_site": 0})
    feats = dict(zip(m.feature_names, m.features(thursday, 0.0)))
    assert feats["home_short_week"] == 1.0
    assert feats["away_short_week"] == 0.0
    assert feats["rest_diff"] == pytest.approx((4 - 7) / 7.0)


def test_unknown_tier_is_rejected():
    with pytest.raises(ValueError):
        ContextFeatureModel(tier="vibes")


# -- the ingest actually carries the columns ----------------------------------

def test_committed_nfl_table_carries_the_context_columns():
    df = snapshots.read_processed("nfl_games")
    for col in ("home_rest", "away_rest", "div_game", "neutral_site",
                "roof", "surface", "temp", "wind", "home_qb_id", "away_qb_id"):
        assert col in df.columns, f"{col} missing from the committed table"
    # Neutral-site games exist and Elo currently hands all of them a full home
    # advantage; that is the concrete error `neutral_site` is there to express.
    assert df["neutral_site"].sum() > 0


def test_weather_columns_do_not_exist_before_kickoff():
    """The weather tier cannot be priced with, and this is why.

    Run 12's docstring called the tier "mildly optimistic", as though a live
    model would hold a forecast in place of the observation. Run 18 measured
    it on the committed table: nflverse populates `temp` and `wind` only after
    a game is played, so at pricing time the column is not worse, it is empty.
    Run 12 rejected the tier on AUC regardless, so nothing downstream rests on
    this -- it is pinned so a future run proposing to revisit weather learns
    the feature is absent before it spends a session fitting it.

    `roof` and `surface` are asserted alongside precisely because they are the
    counter-example: schedule-known, available in advance, and legitimately
    usable.
    """
    df = snapshots.read_processed("nfl_games")
    played = df["home_score"].notna()
    unplayed = df[~played]
    if unplayed.empty:  # pragma: no cover - only out of season
        pytest.skip("no unplayed games in the committed table")

    assert unplayed["temp"].notna().sum() == 0
    assert unplayed["wind"].notna().sum() == 0
    # Populated for a good share of played games, so the zero above is about
    # timing rather than the columns being empty everywhere.
    assert df[played]["temp"].notna().mean() > 0.3
    # The tier that IS knowable in advance.
    assert unplayed["surface"].notna().mean() > 0.9
    assert unplayed["roof"].notna().mean() > 0.5


def test_auc_helper_agrees_with_a_hand_computed_case():
    y = [0, 0, 1, 1]
    assert auc(y, [0.1, 0.2, 0.3, 0.4]) == pytest.approx(1.0)
    assert auc(y, [0.4, 0.3, 0.2, 0.1]) == pytest.approx(0.0)
    assert auc(y, [0.5, 0.5, 0.5, 0.5]) == pytest.approx(0.5)


# -- the overfitting objection, tested rather than argued ---------------------

def test_regularization_is_actually_applied():
    """If C did not reach the fit, the sweep would be fifteen copies of one row."""
    games = _nfl_games()
    loose = run_tier(games, TIER_SCHEDULE)
    tight_model = ContextFeatureModel(TIER_SCHEDULE, C=0.001)
    backtest_nfl(games, NflEloModel(), context_model=tight_model)
    tight_model.start_season()
    loose_coefs = loose["coefficients"]
    tight_coefs = tight_model.coefficients
    context_terms = [f for f in loose_coefs if f != "elo_diff"]
    for f in context_terms:
        assert abs(tight_coefs[f]) < abs(loose_coefs[f]), (
            f"{f}: penalty did not shrink the coefficient")


def test_neutral_site_coefficient_opposes_home_advantage():
    """A sanity check on direction, not a result.

    Elo hands the nominal home team a flat +55 on every game including the
    ~54 where nobody is home. If the fit did NOT learn a negative neutral-site
    term, the feature is not being read the way the ingest intends.
    """
    res = run_tier(_nfl_games(), TIER_SCHEDULE)
    assert res["coefficients"]["neutral_site"] < 0
