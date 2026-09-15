"""The four numbers every run reports as "digit-for-digit" are now checked.

Runs 5-10 each re-ran the backtests by hand and compared the output to a
number copied out of the previous journal entry. That works right up until
someone runs a different season window and reads the difference as a
regression (run 11, ~20 minutes) -- or, worse, as an improvement.

These tests re-derive the pinned values from the committed tables. They are
deliberately exact: the engine is pure-Python arithmetic over a frozen CSV, so
there is no tolerance to spend. If one of these fails, something real changed
-- the engine, the committed data, or a dependency's float behaviour -- and it
needs an explanation in the journal, not a loosened assertion.

~3s for both. They need `data/processed/*.csv`, which are committed for exactly
this reason (see .gitignore).
"""
import pytest

from sportsedge.backtest import benchmarks
from sportsedge.backtest.engine import backtest_nfl, backtest_soccer
from sportsedge.models.elo import NflEloModel, SoccerEloModel
from sportsedge.storage import snapshots


def _load(table, wanted):
    try:
        df = snapshots.read_processed(table)
    except FileNotFoundError:  # pragma: no cover - only without committed tables
        pytest.skip(f"{table} not present; run refresh-history")
    return df[df["season"].astype(str).isin(wanted)]


def test_nfl_canonical_backtest_is_unchanged():
    wanted = {str(s) for s in benchmarks.NFL_SEASONS}
    games = _load("nfl_games", wanted)

    result = backtest_nfl(games, NflEloModel())

    assert result["n_games"] == benchmarks.NFL_N_GAMES
    assert result["log_loss"] == benchmarks.NFL_LOG_LOSS
    assert result["roi"]["n_bets"] == benchmarks.NFL_N_BETS
    assert result["roi"]["roi_pct"] == benchmarks.NFL_ROI_PCT


def test_epl_canonical_backtest_is_unchanged():
    wanted = {f"20{s[:2]}-{s[2:]}" for s in benchmarks.EPL_SEASONS}
    games = _load("epl_games", wanted)

    result = backtest_soccer(games, SoccerEloModel())

    assert result["test_season"] == benchmarks.EPL_TEST_SEASON
    assert result["roi"]["n_bets"] == benchmarks.EPL_N_BETS
    assert result["roi"]["roi_pct"] == benchmarks.EPL_ROI_PCT


def test_both_models_still_lose_to_the_market():
    """The deployment gate, as a test rather than a habit.

    `live_enabled` may only be flipped when a league's model beats the
    de-vigged closing line out-of-sample. Neither does. If one ever starts to,
    this test fails and the flip becomes a deliberate, reviewed act instead of
    a side effect of some other change.
    """
    assert benchmarks.NFL_ROI_PCT < 0
    assert benchmarks.EPL_ROI_PCT < 0


def test_cli_backtest_defaults_are_the_canonical_windows():
    """Guards the actual bug: an example window masquerading as the real one."""
    from sportsedge.cli import build_parser

    parser = build_parser()
    nfl = parser.parse_args(["backtest-nfl"])
    epl = parser.parse_args(["backtest-soccer"])

    assert nfl.seasons == list(benchmarks.NFL_SEASONS)
    assert epl.seasons == list(benchmarks.EPL_SEASONS)
    assert epl.league == benchmarks.EPL_LEAGUE
