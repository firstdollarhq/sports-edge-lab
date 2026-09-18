"""The season_regression rejection, pinned so it stays rejected.

Run 17 swept the one `NflConfig` parameter `sweep_nfl` never varied. It was
worth sweeping because run 11's argument against every recalibration-shaped
change -- AUC is invariant under monotone transforms of the forecast -- does
not apply to it: season regression changes the ratings, so it reorders games.

It was rejected. These tests exist so the rejection is a fact about the
committed data rather than a paragraph in a journal entry, and so that a future
run proposing "let's try tuning season regression" is answered by a test name
instead of by three hours of re-derivation.

The two assertions that matter are the two that do the rejecting:

* nothing in the grid beats the de-vigged closing line, on either metric, in
  either phase -- which is the deployment gate, and
* the value log-loss prefers (0.25) ranks WORSE than the incumbent on the
  holdout -- the run-12 trap, and the reason this is scored on AUC at all.

~1s. Needs `data/processed/nfl_games.csv`, which is committed.
"""
import pytest

from sportsedge.backtest import sweep
from sportsedge.storage import snapshots


@pytest.fixture(scope="module")
def swept():
    try:
        snapshots.read_processed("nfl_games")
    except FileNotFoundError:  # pragma: no cover - only without committed tables
        pytest.skip("nfl_games not present; run refresh-history")
    return sweep.sweep_season_regression()


def test_nothing_in_the_grid_beats_the_closing_line(swept):
    """The deployment gate, asked of all ten values in both phases."""
    v = swept["verdict"]
    assert v["beat_market_log_loss_in_selection"] == 0
    assert v["beat_market_auc_in_selection"] == 0
    assert v["beat_market_log_loss_in_confirmation"] == 0
    assert v["beat_market_auc_in_confirmation"] == 0
    assert v["adopt"] is False


def test_the_log_loss_pick_ranks_worse_on_the_holdout(swept):
    """Run 12's trap, reproduced: better log-loss, worse ranking.

    If this ever flips, the grid is no longer demonstrating the trap and the
    journal's account of why AUC is reported alongside log-loss needs redoing.
    """
    v = swept["verdict"]
    assert v["selected_by_log_loss"] == 0.25
    assert v["log_loss_pick_ranks_worse_than_incumbent_on_holdout"] is True

    conf = swept["confirmation"]
    ll = conf[conf["season_regression"] == 0.25].iloc[0]
    inc = conf[conf["season_regression"] == 0.33].iloc[0]
    assert ll["log_loss"] < inc["log_loss"]      # log-loss prefers 0.25
    assert ll["auc_model"] < inc["auc_model"]    # ranking prefers 0.33


def test_the_incumbent_is_the_auc_optimum_of_the_grid(swept):
    """0.33 was a default, not a fitted value, and it is already AUC-best.

    Worth pinning because it is the reason there is nothing to adopt: the
    sweep did not find a better value that was rejected for being untested, it
    found that the untested knob was already at its best setting.
    """
    assert swept["verdict"]["selected_by_auc"] == 0.33
    assert swept["verdict"]["incumbent_is_auc_optimal_in_selection"] is True


def test_the_auc_deficit_is_flat_across_the_whole_grid(swept):
    """Season regression is not the lever on the thing that is actually wrong.

    Every value trails the market's ranking by roughly the same margin, so the
    -0.046 discrimination gap run 11 measured is not something this parameter
    reaches. That, not the failed adoption, is the finding.
    """
    lo, hi = swept["verdict"]["auc_gap_range_in_selection"]
    assert hi < 0, "some value would have out-ranked the market"
    assert lo < -0.09, "the 1.0 end of the grid should be much worse"
    # Excluding the degenerate full-reset end, the gap barely moves.
    sel = swept["selection"]
    interior = sel[sel["season_regression"] <= 0.75]
    assert interior["auc_gap_vs_market"].max() - interior["auc_gap_vs_market"].min() < 0.015


def test_confirmation_never_scores_a_selection_season(swept):
    """The holdout is the whole design; a leak would void the confirmation."""
    assert set(sweep.SEASON_REGRESSION_CONFIRM).isdisjoint(sweep.SEASON_REGRESSION_SELECT)
    # 2024 alone, not the canonical 2021-2024 window every other sweep uses.
    assert swept["confirmation"]["n_games"].nunique() == 1
    assert swept["selection"]["n_games"].nunique() == 1
    assert swept["confirmation"]["n_games"].iloc[0] < swept["selection"]["n_games"].iloc[0]


def test_incumbent_is_confirmed_once_even_when_it_is_also_the_pick(swept):
    """0.33 is both the incumbent and the AUC pick, and must not be run twice.

    A list-built candidate set would score it twice and put two identical rows
    in the confirmation table, which reads like an independent replication.
    """
    conf = swept["confirmation"]
    assert len(conf) == conf["season_regression"].nunique()
    role = conf[conf["season_regression"] == 0.33]["role"].iloc[0]
    assert "incumbent" in role and "selected-by-auc" in role
