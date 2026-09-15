# Scheduled run 12 -- the information Elo is missing is not in the free columns

_2026-09-15, 15:02-16:5xZ. Run 11 was earlier the same day, 06:02-07:40Z._

## Headline

**Run 11 said the model has to rank better or stop, and named what was left to
try. Run 12 tried it, and it does not work.** Rest, short weeks, divisional
games, neutral sites, roof, weather and starting-QB changes -- all of it
already in the nflverse payload, all of it discarded by the ingest until today
-- make the NFL model's ranking **worse**, not better:

| tier | AUC | vs elo-only control | vs market |
|---|---|---|---|
| elo_only (control) | 0.6839 | -- | -0.0449 [-0.065, -0.025] |
| schedule | 0.6728 | **-0.0111 [-0.017, -0.005]** | -0.0560 [-0.076, -0.036] |
| weather | 0.6712 | **-0.0126 [-0.020, -0.006]** | -0.0576 [-0.078, -0.037] |
| qb | 0.6768 | -0.0071 [-0.017, +0.003] | -0.0520 [-0.072, -0.032] |
| *baseline Elo* | *0.6853* | | |
| *market* | *0.7288* | | |

n = 1,408 games (2020-2024; the earlier seasons are burn-in for the fit).
**Nothing is adopted. `live_enabled` stays `false` everywhere.**

**The overfitting objection is tested, not argued.** Sweeping the L2 penalty
over 15 (tier, C) settings finds **no setting at which context beats the
control**. The best of the fifteen is `qb` at C = 0.1: **-0.0045**, CI
[-0.0130, +0.0039] -- a confidence interval straddling zero, i.e. at its very
best this information is indistinguishable from not having it.

**A methodological finding, caught by the control failing.** A logistic on
`elo_diff` alone is a monotone transform of `elo_diff` and must rank
identically to baseline Elo. Pooled, it did not: 0.68389 vs 0.68532. Not a
leak -- the model refits each season, so the window is *five different*
monotone transforms, and pooling five monotone transforms is not monotone in
anything. Per season the control ties at **exactly 0.0, all five**.

**No bets settled and no new bets logged.** All 23 recommendations were
duplicates of open rows. The ledger is unchanged from run 11: 25 settled, 6
wins, **24.0%**, ROI **-20.87%**.

Tests **232 -> 248**.

## Finding 1: the free context columns make the ranking worse

Run 11's bound was about AUC, so the answer had to be about AUC. A tier that
improves log-loss but not AUC has done nothing that was not already ruled out
-- and note that two tiers *do* improve log-loss slightly (0.6463, 0.6492
against baseline Elo's 0.6497) while ranking worse. That is precisely the trap
run 11's bound exists to catch, and it would have read as an improvement under
any metric this project used before run 11.

### What was added

nflverse ships all of this per game and `fetch_nfl_games` was keeping none of
it. Ten columns now carried, in three tiers by how honest they are:

- **schedule** -- `rest_diff`, `home_short_week`, `away_short_week`,
  `div_game`, `neutral_site`. Schedule facts, known weeks ahead. **Zero
  lookahead risk**; the only tier whose result could have been deployed as-is.
- **weather** -- adds `is_outdoor`, `wind_mph`, `temp_dev`. nflverse records
  the conditions the game was *played* in; a model pricing at T-8h has a
  forecast. Optimistic, so an upper bound on what weather could contribute.
- **qb** -- adds `home_qb_change`, `away_qb_change` ("did this team's starting
  QB change since its last game"). nflverse names who actually started.
  Inactives post ~90 minutes out, so nearly knowable, but not knowable when
  this project prices. Also optimistic.

The tiers are reported apart deliberately: a gain appearing only in `weather`
or `qb` would be a gain that may not survive a real pricing clock. **In the
event it does not matter, because there is no gain in any tier** -- but the
structure is what would have made a gain readable, and it stays.

### The coefficients are sensible, which is the interesting part

This is not a case of the fit learning nonsense:

```
elo_diff         +0.8097
rest_diff        +0.3191
home_short_week  +0.1751
away_short_week  -0.1193
div_game         -0.0862
neutral_site     -0.4534
```

`neutral_site` at **-0.4534** is exactly right in direction and roughly right
in size: Elo hands the nominal home team a flat +55 rating points on every
game, including the 54 in this table where nobody is home, and the fit learns
to take most of that back. `rest_diff` is positive, extra rest helps. Nothing
here is crazy.

**And it still ranks worse.** The reason is arithmetic rather than mysterious:
the neutral-site correction is real but applies to 54 of 2,499 games (2.2%),
so the most it can buy is a rounding error on pooled AUC, while the variance
the other five coefficients add is spread across every game in the sample.
Being right about 2% of games does not pay for being noisier about 100% of
them.

### The overfitting objection, measured

The obvious objection is that the fit is chasing noise in a few hundred
training games and would work with shrinkage. `context-report
--sweep-regularization`:

| tier | C=0.001 | C=0.01 | C=0.1 | C=1 | C=10 |
|---|---|---|---|---|---|
| schedule | -0.0375 | -0.0064 | -0.0074 | -0.0111 | -0.0117 |
| weather | -0.0399 | -0.0092 | -0.0091 | -0.0126 | -0.0134 |
| qb | -0.0373 | -0.0060 | **-0.0045** | -0.0071 | -0.0076 |

(gap vs the elo-only control; `any_setting_beats_control: false`.)

One caveat on reading the small-C end, stated because it would otherwise look
like the sweep proves more than it does: **the penalty is not selective**, so
it crushes `elo_diff` along with the context terms. That is why C = 0.001
collapses every tier toward 0.5 -- those rows are "the whole model, shrunk",
not "context, shrunk", and they say nothing about the features. The
informative region is the middle, where `elo_diff` survives roughly intact.
There the gap is still negative in every cell.

### What this does and does not establish

It establishes that **a linear logistic on the pre-kickoff context nflverse
ships does not improve this model's ranking, at any penalty strength, on 1,408
games.** That is a real answer to run 11's question and it is the answer the
honest null predicted.

It does not establish that no use of this information could ever help. A
non-linear fit, interactions, or a genuinely different information source
(injury reports beyond QB, personnel, line movement as a feature) are not
tested here. But the cheap version of "add the features the market prices and
Elo cannot see" has now been tried with the data already in hand, and it made
things worse. **The next proposal in this direction should have to say why it
expects a different outcome**, rather than assuming this one was merely
under-powered.

## Finding 2: a per-season refit is not a monotone transform of anything

The experiment's control was designed to be load-bearing: a logistic on
`elo_diff` alone is a strictly monotone transform of `elo_diff`, so it must
reproduce baseline Elo's AUC exactly. If it does not, something is leaking and
every other number in the report is void.

It failed on the first run: **0.6838887761315202 against 0.6853176375076111.**

The cause is not a leak. The model refits at each season boundary, so the five
evaluation seasons are priced by five *different* monotone transforms, and
pooling them is not a monotone transform of anything -- the between-season
recalibration reorders games across season boundaries. Measured per season:

| season | n | AUC elo-only | AUC baseline | delta |
|---|---|---|---|---|
| 2020 | 269 | 0.7169707020453289 | 0.7169707020453289 | **0.0** |
| 2021 | 285 | 0.6827368628610865 | 0.6827368628610865 | **0.0** |
| 2022 | 284 | 0.6476814516129032 | 0.6476814516129032 | **0.0** |
| 2023 | 285 | 0.6450110198357043 | 0.6450110198357043 | **0.0** |
| 2024 | 285 | 0.7379745577419996 | 0.7379745577419996 | **0.0** |

Exact zeros, not approximate ones. Two consequences, both acted on:

1. **The control is asserted per season**, which is where the invariance
   actually holds and therefore where a real leak would show up.
2. **The yardstick for the features is the elo-only tier, not raw Elo.** Both
   carry the seasonal-refit effect; only one carries the features. Scoring
   context against raw Elo would have silently credited the features with the
   refit -- here worth **-0.0014 AUC**. Small, and pointed the other way, so
   it would have made the result look *better* than it is, not worse. This
   project has been bitten twelve times by a value that was not what the
   surrounding code assumed; this one was caught before it was published, by a
   control written specifically to catch it.

**This does not qualify run 11's bound.** That argument was about a single
fixed transform of a fixed prediction vector and is untouched. The effect
measured here is two orders of magnitude short of the -0.046 model-vs-market
gap, and negative. But the sentence "recalibration cannot reorder anything"
is, stated that loosely, false when the recalibration is refit on a schedule,
and it is worth having that written down precisely rather than as a slogan.

`test_pooled_control_moves_and_that_is_expected` pins the finding so a future
run cannot "fix" the discrepancy by loosening the real assertion.

## Bets

**Nothing settled.** 24 pending, 0 resolved, 0 CLV filled, 0 backfilled. The
next kickoffs are 2026-09-17 onward; run 11 settled NFL week 1 overnight and
today is the quiet Tuesday between slates.

**Nothing logged.** All 23 flagged recommendations were duplicates of open
rows: NFL 16 of 32 contracts (50.0%), EPL 7 of 25 (28.0%),
`illiquid_skipped: 5` on the EPL side (the standing thin-book pattern),
`in_play_skipped: 0`, `superseded_voided: 0`.

The ledger is therefore identical to run 11:

| | run 11 | run 12 |
|---|---|---|
| settled | 25 | 25 |
| wins | 6 | 6 |
| pending | 24 | 24 |
| void | 67 | 67 |
| win rate | 24.00% | 24.00% |
| ROI | -20.87% | -20.87% |
| mean CLV (real close) | -1.14% (n=16) | -1.14% (n=16) |
| mean CLV (stale) | +4.04% (n=9) | +4.04% (n=9) |

Ledger integrity: **49 non-void rows = 49 distinct wagers.** Every row
`shadow`.

**The pre-registered cohort was deliberately not re-scored.** Run 11 recorded
that the 36-wager pre-registration has now been looked at three times against
the same growing sample with no correction for having looked, and instructed
that the honest read is the one taken at 36, on 09-21. Nothing settled today,
so the scorecard's `p_at_most_model` is still 0.0509 -- the *same* look as run
11, not a new one. Reporting it as though the number had been re-earned would
be exactly the optional stopping run 11 flagged.

The biggest claimed edge on today's board is **MIA @ SF away at +163.3%**
(model 0.316 against a 0.114 fair price, 12c ask). That is the winner's-curse
signature this project has measured twice -- run 4's selection audit, run 11's
median split -- showing up as the largest number on the screen. It is logged
as a duplicate of an existing open row, so nothing new was staked on it.

## Regression checks

All four canonical numbers reproduce digit-for-digit **after regenerating
`nfl_games.csv` with ten new columns**, which was the specific risk of this
run's ingest change:

| | run 12 | runs 5-11 | match |
|---|---|---|---|
| NFL log-loss | 0.6517617405253826 | 0.6517617405253826 | digit-for-digit |
| NFL ROI | -8.208908995992267% | -8.208908995992267% | digit-for-digit |
| NFL n_games / n_bets | 1942 / 1625 | 1942 / 1625 | exact |
| EPL 2425 holdout ROI | -5.11513157894739% | -5.11513157894739% | digit-for-digit |

These are re-derived by `test_benchmarks.py` from the committed tables on
every CI run, not read off a screen. A further test pins that attaching a
context model leaves the Elo path **bit-identical game by game**, not merely
equal in aggregate -- the context model rides the existing walk-forward loop
rather than copying it, and this is the assertion that it rides rather than
steers.

`verify-settlements` clean: NFL 32/32 agreed, soccer 120/120,
`unmatched_in_coverage: 0` on both, 94 NFL unmatched all out-of-coverage
(preseason, which nflverse does not carry).

## Data sources

| Source | Status |
|---|---|
| nflverse | Live. 2,499 games, 2,243 played. Unchanged since run 11 -- week 2 starts 09-17. |
| football-data.co.uk | Live. E0 2026-27 at 40 played, unchanged. |
| Kalshi REST | Live. 32 NFL + 30 EPL contracts captured. |
| ESPN scoreboard | Live. NFL 16/16 scores and kickoffs agree; EPL 40/40. `only_espn: 0`. |

The capture cron is healthy: snapshots every ~30 minutes, ten commits between
10:03Z and 14:36Z today, most recently ~26 minutes before this run started.

**Escalations: none.** No charge and no signup form is outstanding. The ten
new columns came from a source already in use, free, no key -- nothing new was
needed to run this experiment, which is part of why it was worth running
before anything more expensive.

## Open questions / next steps

- **The honest null is now the leading hypothesis, and it should be stated as
  one.** Twelve runs, 150+ configurations, a hard AUC bound against
  recalibration, and now a negative result on the obvious non-Elo information.
  Nothing found so far suggests a public-data team-strength model beats this
  closing line. That is a finding, not a failure -- but continuing to add
  features without a reason to expect a different outcome would be.
- **What would actually be a different bet:** information the closing line
  prices *late* or prices *badly*, rather than information it prices
  perfectly. Every feature tested today is on the market's screen too. The
  only asymmetries this project has measured are in its own favour nowhere,
  and the line-movement work says the final hour barely moves -- which is
  itself evidence the market is not leaving anything on the table here.
- **The 11 remaining pre-registered wagers kick off 2026-09-20 to
  09-21T00:20Z.** Score the cohort at 36 on 09-21 and treat that as the read.
  Do not re-score the partial cohort; today's run did not.
- **After 09-21, `PRICING_VERSION` is free to move**, unchanged from runs 10
  and 11.
- **CLV: the real-close cohort is 16 rows and still mostly zeros.** Unchanged.
- The 5% relative-width liquidity gate remains unvalidated against realized
  fill quality.
- Nothing in `pyproject` is pinned exactly; `test_benchmarks.py` catches the
  consequences rather than preventing them.
- NFL preseason markets are priced and settled by Kalshi but invisible to
  nflverse; labelled, not fixable.
- ESPN is an **undocumented** endpoint; `espn-audit` is read every run.
- **Standing reminder:** 0 live bets. 25 settled shadow bets, 6 wins, ROI
  **-20.87%**, the market beats the model on every scoring rule on the bets
  the model itself chose, the only CLV cohort measured against a real closing
  price is negative, the model ranks games significantly worse than the
  closing line, and the free information that was supposed to close that gap
  makes it wider. That is the deployment gate doing its job, and it is still
  25 wagers.

## Process note

The stored scheduled prompt still carries "do not post, send, change, or
delete anything" and the unfilled `[which data sources?]` placeholder.
CLAUDE.md has overridden the first for repository work since 2026-09-11 and
settled the second since 2026-09-13. Noted once, per CLAUDE.md, and not
escalated.
