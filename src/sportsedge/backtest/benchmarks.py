"""The canonical backtest windows, and the numbers they are pinned to.

Every run since run 5 has reported the same four "digit-for-digit" regression
numbers, but the *seasons* those numbers came from lived only in journal prose.
`backtest-nfl` and `backtest-soccer` both required `--seasons` with no default,
and the example in `cli.py`'s own module docstring uses a different window than
the canonical one. Run 11 copied that example and got:

    NFL  2020-2024        log-loss 0.6543847397000941   ROI  -9.84%
    NFL  2018-2024        log-loss 0.6517617405253826   ROI  -8.21%   <- canonical
    EPL  2223-2425                                      ROI  -8.46%
    EPL  1920-2425                                      ROI  -5.12%   <- canonical

...and spent a chunk of the run investigating a regression that was not there.
A phantom regression is the cheap failure. The expensive one is the same
mistake in the other direction: a narrower window that happens to look better,
reported as an improvement.

The EPL number is the one to be careful with. Dropping just the oldest season
moves the holdout ROI from -5.12% to -2.73%, and dropping two moves it to
-12.17%. That is a 9-point swing from the choice of calibration window alone,
on a number whose 95% interval already straddles zero. No EPL ROI figure from
this project means anything without its window stated alongside it.

These constants are the window. `test_benchmarks.py` re-derives the pinned
values from the committed tables on every CI run, so a real drift in the
engine, the data, or a dependency fails the suite instead of being discovered
by eye three runs later.
"""
from __future__ import annotations

# --- canonical windows -------------------------------------------------------

NFL_SEASONS = (2018, 2019, 2020, 2021, 2022, 2023, 2024)
"""Matches sweep.DEFAULT_SEASONS, which has defaulted to this since run 5."""

EPL_SEASONS = ("1920", "2021", "2122", "2223", "2324", "2425")
"""Holdout is the last entry (2024-25); the rest calibrate. 2526/2627 are
excluded deliberately: 2026-27 is in progress, and holding out a 40-game
in-progress season instead of a completed 380-game one is the mistake
`_load_games` already carries a docstring about."""

EPL_LEAGUE = "E0"

# --- pinned results ----------------------------------------------------------
#
# Unchanged since run 5 (2026-09-12). Bit-exact, not rounded: these are the
# repr of the float the engine actually returns, so a one-ulp drift is a
# failure and has to be explained rather than absorbed.

NFL_LOG_LOSS = 0.6517617405253826
NFL_ROI_PCT = -8.208908995992267
NFL_N_GAMES = 1942
NFL_N_BETS = 1625

EPL_ROI_PCT = -5.11513157894739
EPL_N_BETS = 304
EPL_TEST_SEASON = "2024-25"
