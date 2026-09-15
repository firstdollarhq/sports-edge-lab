# Scheduled run 11 -- the model's problem is ranking, and that rules out a whole family of fixes

_2026-09-15, 06:02-07:40 UTC. Run 10 was 2026-09-14, 15:02-16:20Z._

## Headline

**Run 10 closed by asking which part of the model's probabilities was wrong.
It is the ranking, and that is the bad answer.** Over all 1,942 priced games
in the canonical NFL window, the model's AUC is **0.678** against the market's
**0.724** -- paired bootstrap gap **-0.046**, 95% CI **[-0.064, -0.030]**,
model ranks better in **0 of 5,000** resamples. AUC is invariant under any
monotone transform of the predictions, so *no recalibration can fix this*:
not a threshold change, not shrinkage toward the market, not Platt or
isotonic, not the fee-inclusive edge. None of them reorder anything. Every
model change this project has proposed and rejected has been a recalibration.

**Two pre-registered wagers settled, both losses.** The 13-wager cohort run 9
pre-registered is now 2 resolved, **0 wins**. Headline ROI falls from -13.98%
to **-20.87%**, win rate 26.1% -> **24.0%**.

**A near-miss on reproducibility, and a fix for it.** This run spent ~20
minutes investigating an NFL backtest "regression" that did not exist: the
canonical season window lived only in journal prose, and `cli.py`'s own
docstring example used a *different* window. Both backtests now default to the
canonical window and `tests/test_benchmarks.py` pins all four numbers exactly.

**football-data.co.uk has caught up.** Matchweek 4 published; EPL 2026-27 goes
30 -> 40 played and the `only_espn` gap closes to 0. Three new EPL wagers
logged -- the first new bets since run 8.

Tests **216 -> 232**. No model changed. `live_enabled` stays `false` everywhere.

## Finding 1: discrimination, not calibration

Every model change this project has weighed -- the blend sweep, the p3
fee-inclusive threshold (run 10), the edge-threshold grid (runs 5, 9) -- is a
**recalibration**. Each changes the number attached to a game, or which numbers
clear a bar. None changes the *order* the model puts games in.

That family has a ceiling, and it is measurable, because:

> AUC is invariant under any strictly monotone transform of the predictions.

So if the model's AUC is below the market's, no recalibration closes the gap.
Measured over every priced game in the canonical window -- not over `bets`,
which is a selected sample by construction and therefore cannot answer a
question about raw ranking:

| | AUC | Brier | reliability | resolution | log-loss |
|---|---|---|---|---|---|
| model | **0.6779** | 0.2299 | 0.0055 | **0.0241** | 0.6518 |
| market | **0.7242** | 0.2109 | 0.0005 | **0.0372** | 0.6097 |

Uncertainty (base-rate variance) is 0.2481 for both.

Paired bootstrap on the AUC difference, 5,000 draws, seeded:

```
AUC(model) - AUC(market) = -0.0464   95% CI [-0.0636, -0.0295]
share of resamples where the model ranks better: 0.0000
```

The Murphy decomposition says the same thing from the other side. Reliability
is the part a recalibration can drive to zero, and the model's reliability
penalty is **0.0055** -- small. Resolution is the part it cannot touch, and
there the model gives up **0.0131**, more than twice as much.

The direct test of the bound: fit isotonic regression on the very outcomes it
is being scored on -- deliberate cheating, an upper bound no honest procedure
reaches -- and the model still only gets to log-loss **0.6350**, against the
market's **0.6097**.

**Read plainly: the NFL Elo model orders games worse than the closing line
does, significantly, and there is no repair on the probability-transform side.
Only a model that ranks games better can help.** This is consistent with
everything already on the record -- the blend sweep's w* = 0, the market
winning every scoring rule -- but those were suggestive and this is a bound.

### The EPL leg, and a trap in the method

The soccer leg (2024-25 holdout, n = 380) reads: model AUC 0.7145, market
0.7348, gap **-0.0203**, CI **[-0.0392, -0.0022]**. Significant, but barely,
and on a fifth of the NFL sample.

Its oracle recalibration *does* reach the market (0.5758 vs 0.5905) -- and
that means nothing. **The oracle bound is a one-sided test.** In-sample
isotonic can only ever improve on its input, and the thinner the sample the
more of that improvement is fitted noise. A failure to reach the market is
conclusive; reaching it is the expected result of letting a flexible monotone
fit see the answers.

My first version of `_verdict` got this wrong in a way worth recording: it
required *both* a significant gap and a failed oracle bound before saying
anything, so the EPL leg -- whose CI lies entirely below zero -- was reported
as "no significant ranking difference", contradicting its own interval. Fixed,
and `test_verdict_does_not_call_a_significant_gap_insignificant` pins it. The
output field is deliberately named `recalibration_ruled_out` rather than
`recalibration_can_close_the_gap`, because only the `true` value carries
information.

### What changed in the code

`backtest.discrimination`, plus a `discrimination-report` CLI command. The
engines now return a per-game `predictions` list (`game_id`, `y`, `p_model`,
`p_market`) and the report consumes it. That is additive -- **both canonical
backtests reproduce digit-for-digit after the change** -- and it specifically
avoids a second copy of the walk-forward loop, which this repo's history is a
catalogue of the cost of.

The load-bearing fact is asserted rather than assumed:
`test_auc_is_invariant_under_monotone_recalibration` checks AUC is unchanged
under `x^3`, `sqrt(x)`, a shrink toward 0.5, and a logistic squash. Without
that invariance the entire argument above is void.

## Finding 2: a regression that was not there, and the papercut behind it

The run's regression checks were run as `backtest-nfl --seasons 2020 ... 2024`,
copied from the example in `cli.py`'s module docstring. That returns log-loss
**0.6543847397000941** and ROI **-9.84%** against the pinned 0.6517617405253826
and -8.21%. It looked like a genuine drift in a number six runs have called
"digit-for-digit", and it cost about twenty minutes: the data was confirmed
byte-identical over the window, pandas was downgraded to 2.3.3 to test a
dependency hypothesis, and the backtest was confirmed deterministic across
three runs before the actual cause turned up.

The cause: **the canonical window is 2018-2024, and it existed only as prose in
journal entries.** `--seasons` was `required=True` with no default on both
backtest commands, so every run retyped it, and the docstring example was a
different window that produces a plausible-looking wrong answer.

The EPL side is worse, because it is more sensitive:

| EPL seasons | holdout ROI |
|---|---|
| 2122-2425 | -12.17% |
| 2223-2425 | -8.46% |
| **1920-2425 (canonical)** | **-5.12%** |
| 2021-2425 | -2.73% |

**A nine-point swing from the choice of calibration window alone**, on a number
whose 95% interval already straddles zero. No EPL ROI figure from this project
means anything without its window stated next to it.

The cheap failure here is a phantom regression. The expensive one is the same
mistake in the other direction -- a narrower window that happens to look
better, reported as an improvement. The project would have had no way to catch
that.

Fixed three ways:

- `backtest.benchmarks` holds the windows and the pinned values as constants.
- Both CLI backtests **default** to the canonical window (`sweep-nfl` already
  did, via `sweep.DEFAULT_SEASONS` -- the precedent existed and the backtests
  just never got it).
- `tests/test_benchmarks.py` re-derives all four numbers from the committed
  tables on every CI run. Exact assertions, no tolerance: the engine is
  pure-Python arithmetic over a frozen CSV, so a one-ulp move is a real event
  that needs an explanation rather than a loosened assert.

This is a **process defect, not a model bug. The tally of bugs stays at 12.**
It is the same lesson as run 10's "gap" false alarm, one level up: a number is
not identified by the command that printed it.

### A dependency floor that was a wish

Testing the pandas hypothesis turned up a real if minor thing: on **pandas
2.3.3 three snapshot tests fail**, including the 1-ULP dedup guard. `pyproject`
declared `pandas>=2.0`, so a resolver picking a 2.x wheel produced a repo that
does not work. Raised to `pandas>=3.0`, the version actually verified green
(3.0.5).

Nothing in `pyproject` is pinned exactly, and that is worth stating as a
standing risk rather than a solved problem: four numbers are reported every run
as "digit-for-digit" from a container that is wiped and re-resolves its
dependencies from scratch each time. They have held. `test_benchmarks.py` now
makes a future drift fail loudly instead of being noticed by eye three runs
later.

## Bets

**Two settled, both lost**, and both against genuine closing references
(lag 0.21h and 0.34h):

| bet | selection | model | market fair | result | CLV | lag |
|---|---|---|---|---|---|---|
| DEN @ KC | away | 0.487 | 0.435 | **lost** | +4.55% | 0.21h |
| Newcastle @ Leeds | away | 0.384 | 0.327 | **lost** | -3.03% | 0.34h |

KC won 31-10 and Leeds won 4-1. Both were model-over-market picks; both lost.

**Three new EPL wagers logged**, the first since run 8 -- last run all 21
recommendations were duplicates of open rows:

| matchup | selection | model | edge | after fee |
|---|---|---|---|---|
| Liverpool @ Bournemouth | home | 0.365 | +21.7% | +16.1% |
| Ipswich @ Everton | home | 0.642 | +16.7% | +13.1% |
| Liverpool @ Bournemouth | draw | 0.264 | **+5.4%** | **+0.2%** |

That third row is run 10's Finding 2 on the board again: it clears the 3%
threshold before fees and is worth **+0.2%** after them. Under the rejected p3
it would not be bet. p3 stays rejected -- and Finding 1 now explains *why* that
whole family fails, rather than just recording that it did.

`recommend` flagged 16 of 32 NFL contracts (50.0%, all duplicates) and 7 of 25
EPL (28.0%). `illiquid_skipped: 5` on the EPL side, the standing thin-book
pattern. `in_play_skipped: 0`, `superseded_voided: 0`.

| | run 10 | run 11 |
|---|---|---|
| settled | 23 | **25** |
| wins | 6 | **6** |
| pending | 23 | **24** |
| win rate | 26.09% | **24.00%** |
| ROI | -13.98% | **-20.87%** |
| mean CLV (real close) | -1.41% (n=14) | **-1.14% (n=16)** |
| mean CLV (stale) | +4.04% (n=9) | +4.04% (n=9) |

The stale cohort is unchanged because no stale-reference row settled; it still
contains **zero negative readings** out of 9, and the real-close cohort still
contains the only negative mean the project has measured.

Ledger integrity: **49 non-void rows = 49 distinct wagers**. Every row `shadow`.

### The pre-registered cohort

Run 9's 13-wager pre-registration reproduces exactly from `placed_at` --
claimed **5.74**, selection-corrected **4.05**, market-implied **4.72** -- which
is the check that the right rows are being scored. **2 resolved, 0 wins.** The
two carried 0.871 claimed / 0.689 corrected / 0.762 market between them, so 0
of 2 is unremarkable on its own and is reported here only because
pre-registration means reporting it either way.

Across all 36 pre-registered wagers, 25 now settled, 6 wins:

| hypothesis | expected | P(X <= 6) |
|---|---|---|
| model's own claim | 10.32 | **0.051** |
| selection-corrected | 7.91 | 0.270 |
| market-implied | 8.53 | 0.190 |

**That 0.051 must not be read as a rejection**, and specifically not as one
that "just crossed" a threshold. This is the third time the same growing
sample has been scored against the same hypothesis, with no correction for
having looked. That is optional stopping, and it is exactly the mechanism that
manufactures a p-value near 0.05 out of nothing. The pre-registration was made
over **36** wagers; the honest read is the one taken at 36, and 11 are still
open. Recorded now so that the final number cannot be chosen after the fact.

## Regression checks

All four reproduce digit-for-digit, **after** the engine change in Finding 1:

| | run 11 | runs 5-10 | match |
|---|---|---|---|
| NFL log-loss | 0.6517617405253826 | 0.6517617405253826 | digit-for-digit |
| NFL ROI | -8.208908995992267% | -8.208908995992267% | digit-for-digit |
| EPL 2425 holdout ROI | -5.11513157894739% | -5.11513157894739% | digit-for-digit |
| NFL flagged gap / soccer | -0.137 / -0.045 | -0.137 / -0.045 | exact |

The secondary selection gap (flagged minus passed) also reproduces at -0.230 /
-0.060. These are now pinned by tests rather than by eye.

Scorecard on the 25 settled rows: NFL 14 rows / 4 wins, model log-loss 0.6876
vs market 0.6515; soccer 11 rows / 2 wins, model 0.5961 vs market 0.5195. The
market beats the model on every scoring rule on both legs, on the bets the
model itself chose. Model overstatement **16.8pp** (NFL) and **17.8pp**
(soccer).

## Data sources

| Source | Status |
|---|---|
| nflverse | Live. 2,499 games, **2,243 played** (+1: DEN @ KC). Week 1 complete at 16 games. |
| football-data.co.uk | Live and **caught up**. E0 2026-27 now **40 played**, latest 2026-09-14. |
| Kalshi REST | Live. 32 NFL + 30 EPL contracts captured. |
| ESPN scoreboard | Live. NFL 16/16 scores and kickoffs agree; EPL 40/40. **`only_espn` now 0.** |

`verify-settlements` clean: NFL 32/32 agreed, soccer 120/120, and
`unmatched_in_coverage: 0` on both.

**Run 10's football-data.co.uk item closes.** Run 10 diagnosed the apparent
8-day gap as the September international break plus a ~2-day publication lag,
and predicted the lag was theirs and would clear. It has: the 9 fixtures from
09-12/13 plus Leeds v Newcastle on 09-14 are all present, and the 10
"only in ESPN" rows it accounted for are now 0. The diagnosis was right.

The capture cron is working as designed -- snapshots every ~30 minutes through
the night, most recently 04:38Z before this run. `line-movement` reconfirms
`*/30` is sufficient: mean |move| in T-1h..T-2h is **0.0036** on 28 NFL
contracts, max one cent, and **no contract moved as much as two cents**.
`*/15` stays rejected.

**Escalations: none.** No charge and no signup form is outstanding.

## Open questions / next steps

- **The model needs to rank better, or it needs to stop.** Finding 1 is the
  first hard bound this project has produced, and it retires the entire
  recalibration family. What is left is genuinely different information:
  injuries, rest, travel, weather, personnel -- things the closing line prices
  and a team-strength Elo does not see. That is a much larger undertaking than
  any change attempted so far, and it should be proposed as one rather than
  approached by another parameter tweak.
- **A fair question is whether this project should keep adding features at
  all.** Nothing found in 11 runs suggests the Elo family can beat this
  market, and the honest null is that a public-data team-strength model does
  not have an edge on an efficient closing line. Worth deciding deliberately
  rather than drifting.
- **The 11 remaining pre-registered wagers all kick off 2026-09-20 to
  09-21T00:20Z**, so the cohort completes on 09-21 as run 10 said. Score it at
  36 and treat that as the read. Do not re-score the partial cohort as though
  each look were free.
- **After 09-21, `PRICING_VERSION` is free to move**, unchanged from run 10.
  (The latest pending kickoff in the ledger is 2026-09-22T00:15Z, but that row
  is not part of the pre-registered cohort and does not constrain the bump.)
- **CLV: the real-close cohort is 16 rows and still mostly zeros.** Revisit
  when it has a usable standard error. The market's near-total lack of movement
  (Finding above) is itself the reason CLV may never be informative here.
- **`edge_threshold_pct: 3.0` has still never been derived from anything**
  (run 5) -- and per Finding 1, deriving it cannot help, since it is a
  recalibration.
- Nothing in `pyproject` is pinned exactly; `test_benchmarks.py` now catches
  the consequences rather than preventing them.
- The 5% relative-width liquidity gate remains unvalidated against realized
  fill quality.
- NFL preseason markets are priced and settled by Kalshi but invisible to
  nflverse; labelled, not fixable.
- ESPN is an **undocumented** endpoint; `espn-audit` is read every run.
- **Standing reminder:** 0 live bets. 25 settled shadow bets, 6 wins, ROI
  **-20.87%**, the market beats the model on every scoring rule on the bets the
  model chose, the only CLV cohort measured against a real closing price is
  **negative**, and the model is now shown to rank games significantly worse
  than the closing line. That is the deployment gate doing its job, and it is
  still 25 wagers.

## Process note

The stored scheduled prompt still carries "do not post, send, change, or
delete anything" and the unfilled `[which data sources?]` placeholder.
CLAUDE.md has overridden the first for repository work since 2026-09-11 and
settled the second since 2026-09-13. Noted once, per CLAUDE.md.
