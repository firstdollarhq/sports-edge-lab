# Scheduled run 17 -- the first settlement in six runs, and the untested knob was already at its best setting

_2026-09-18, 06:01-07:1xZ. One run today; run 16 ran 15:02-16:0xZ yesterday._

## Headline

**A bet settled, for the first time since run 11.** NFL week 2 opened with
Thursday night football and `DET @ BUF` resolved BUF 41-31. The model had
Detroit at **0.380** against a de-vigged market **0.355**, bought at 0.36, and
the contract **closed at 0.31**. Lost. Its CLV is **-13.89%** = **-3.94
ticks**, the largest negative reading in the book -- though only just, ahead of
an existing -12.50% (-3.55 ticks).

The closing reference sat **0.206h -- 12.4 minutes -- before kickoff**. That is
the `*/30` cron working, but it is **not** a first: 16 settled rows already
carried reference lags of 0.12h to 0.42h, and the whole real-close cohort now
sits inside 0.42h. The cron has been supplying genuine closes since run 9. What
was missing for five runs was not measurement quality, it was a settlement.

**A model parameter was swept for the first time in five runs, and rejected.**
`season_regression` is the one `NflConfig` field `sweep_nfl` never varied --
150 configurations across runs 1-16 all ran it at 0.33. Ten values, selected on
2021-2023 and confirmed on a held-out 2024: **none beats the de-vigged closing
line on log-loss or AUC in either phase**, and the incumbent 0.33 turns out to
be **already the AUC-optimal point of the grid**. Committed as
`cli sweep-season-regression` with six tests, so the rejection is a property of
the data and not a paragraph here.

**football-data.co.uk is back, and the committed table it was replaced with was
byte-identical to what the live source now returns.** Run
16's ESPN supplement never fired. The claim runs 15-16 rested on -- that the
committed table was missing no played game -- is now confirmed against the
primary source itself rather than against a cross-check.

**Run 14's "one league of two" is now two of two, weakly.** The EPL liquidity
gate's adverse-tick separation was **+1.6pp, CI [-0.4, +5.6]** on 3,540 pairs;
on 5,490 pairs it is **+2.57pp, CI [+0.72, +6.92]**. The interval has moved off
zero.

Ledger: **26 settled, 6 wins, 23.08%, ROI -23.91%** (was 25 / 6 / 24.00% /
-20.87% for five runs). 4 new shadow rows, all NFL -- the most in one session
since 09-11, because the week-4 board opened. Tests **295 -> 301**.

## Finding 1: the settlement, and what its CLV is and is not

| | |
|---|---|
| bet | `5574242b`, `DET @ BUF`, away, placed 2026-09-14T06:09:57Z |
| model / de-vigged market | **0.3803** / 0.3550 |
| bought at | 0.36 (decimal 2.7778), claimed edge **+5.63%**, after fee +1.10% |
| closed at | 0.31 (decimal 3.2258), reference lag **0.206h** |
| result | BUF 41-31 DET -- **lost** |
| CLV | **-13.889%** = **-3.94 ticks** (book's largest negative; next is -12.50%) |

Verified before being recorded: `verify-settlements` agrees 34/34 NFL and
120/120 soccer, and both stats sources independently say 41-31 (`nflverse`
`2026_02_DET_BUF`, ESPN `401872932`, `STATUS_FINAL`).

**The price path is the interesting part.** 217 captures on this contract from
T-177h, first at 0.40:

```
T-177h 0.40   T-91h 0.36   T-74h 0.33   T-25h 0.32   T-3.2h 0.31   T-0.21h 0.31
```

A monotone five-tick walk away from the side the model bought, over four days,
with **zero reversal**. The model bought at 0.36 on day two of that walk.

**Three things this row does not license.**

It does not overturn run 13's "the line does not move". That finding is about
the *final hours* and about *means*: today's `line-movement` on a window that
now has real final-hour coverage still reports mean |move| of **0.0033** in
T-1h..T-2h and T-2h..T-4h, max **0.01**, and **0% moving >= 0.02** in either
bucket. This contract's five ticks were spent between T-177h and T-74h. The
close is now well measured *and* still quiet.

It does not make CLV a validated instrument here. Split the 17 real-close rows
by the sign of their CLV:

| cohort | n | wins | win rate | ROI |
|---|---|---|---|---|
| CLV < 0 | 6 | 2 | 33.3% | -22.87% |
| CLV = 0 | 8 | 1 | 12.5% | -34.21% |
| CLV > 0 | 3 | 1 | 33.3% | **-38.27%** |

There is **no ordering at all**, and the worst ROI sits on the *positive*-CLV
cohort. At n = 6/8/3 that is noise and must be read as noise -- it is not
evidence that CLV is inverted. What it is, is the first direct look at whether
this project's leading indicator leads anything, and the answer so far is
**nothing detectable**. The cohort's mean is **-1.888%**, SE **1.222%**, and
one tick is **3.525%**, so the mean is **0.54 of a tick** and the SE is
**0.35 of a tick**. Read the mean against the tick, as CLAUDE.md requires.

It does not mean the book is now informative. One settlement is one
settlement.

## Finding 2: season_regression, swept and rejected

`sweep_nfl` crosses `k x home_advantage x use_mov x calibrate` and pins
`season_regression` at 0.33. So the "150 configurations, none beat the market"
tally has never included a single alternative value for how much of last
season a team carries into this one.

**Why this one was worth a look when runs 11-12 retired everything else.** Run
11 closed off Platt, isotonic, shrinkage, threshold moves and fee-inclusive
edge with one argument: the deficit is discrimination (AUC 0.678 vs 0.724), and
AUC is invariant under any monotone transform of the forecast. Season
regression is **not** a monotone transform -- it changes the ratings, so it
reorders games and *can* move AUC. That argument does not reach it. Today's
board sharpened the motive: the two largest claimed edges were `MIA @ SF` away
at **+187.2%** (model 0.316, market 0.105) and `KC @ MIA` home at **+179.9%**
(model 0.504, market 0.173) -- late-September prices on teams whose ratings are
still mostly last season's.

**Design.** Ten values selected on 2021-2023; the value selected is confirmed
on **2024, untouched during selection**. Adding ten configurations to the
canonical 2021-2024 window would have been a tenth look at the window every
other sweep already used, which is the hazard this repo's own note about the
blend sweep's "bait" is about. Scored on log-loss **and** AUC, because run 12
found two feature tiers that improved log-loss while ranking worse.

Selection, 854 games (market log-loss 0.61901, market AUC 0.70994):

| `season_regression` | log-loss | AUC | AUC gap | ROI |
|---|---|---|---|---|
| 0.00 | 0.66594 | 0.64667 | -0.0633 | -8.65% |
| 0.10 | 0.66098 | 0.65208 | -0.0579 | -10.10% |
| 0.20 | 0.65875 | 0.65488 | -0.0551 | -11.59% |
| **0.25** | **0.65836** (best) | 0.65643 | -0.0535 | -11.21% |
| **0.33** (incumbent) | 0.65848 | **0.65804** (best) | **-0.0519** | -9.85% |
| 0.40 | 0.65914 | 0.65787 | -0.0521 | -8.06% |
| 0.50 | 0.66074 | 0.65707 | -0.0529 | -7.19% |
| 0.60 | 0.66288 | 0.65385 | -0.0561 | -6.58% |
| 0.75 | 0.66669 | 0.64487 | -0.0651 | -6.20% |
| 1.00 | 0.67389 | 0.61137 | -0.0986 | -6.65% |

**Beat the market: 0 of 10 on log-loss, 0 of 10 on AUC.**

Confirmation on held-out 2024, 285 games (market 0.58921 / 0.75676):

| | log-loss | AUC | ROI | 95% CI |
|---|---|---|---|---|
| incumbent 0.33 | 0.62481 | **0.73797** | -12.67% | [-29.75, +4.40] |
| log-loss pick 0.25 | **0.62208** | 0.73315 | -9.77% | [-26.95, +7.41] |

**Rejected, and for a better reason than "it lost".** Four reasons, in order of
how much they settle:

1. Nothing clears the gate. The gate is the de-vigged closing line, not a
   previous version of the model, and no value beats it on either metric in
   either phase.
2. **The value log-loss prefers ranks worse than the incumbent out of
   sample** -- 0.73315 against 0.73797. That is run 12's trap exactly, and
   adopting on log-loss alone would have walked into it a second time while
   the ROI column (-9.77% vs -12.67%, intervals overlapping across 37
   percentage points) supplied a comforting-looking reason.
3. **The incumbent is already the AUC optimum of the grid.** 0.33 was a
   convention, not a fitted value, and the sweep did not find a better setting
   that was rejected for being untested -- it found the untested knob was
   already where it should be.
4. **The AUC gap barely moves across the interior of the grid**: -0.0519 to
   -0.0651 for everything from 0.0 to 0.75. Season regression is not a lever on
   the thing that is wrong. That, not the failed adoption, is the finding
   worth keeping.

`config/leagues.yaml` and `PRICING_VERSION` untouched. Configurations tested
now **160**. `cli sweep-season-regression`, six tests in
`tests/test_season_regression_sweep.py`.

## Finding 3: the scorecard is not the pre-registered prediction, and the two have now visibly diverged

`scorecard` reports `p_at_most_model` = **0.0385** this run, down from run 11's
**0.0509**. Read carelessly that is "the pre-registered prediction now rejects
the model at 5%". **It is not, and this run is the first time the difference is
numerically visible.**

Run 4's pre-registration covers **36 specific wagers** -- 1 logged 09-10 and 35
logged 09-11. Reconstructed from `placed_at` again this run, it reproduces run
7's table digit-for-digit:

| leg | wagers | claimed | market-implied |
|---|---|---|---|
| NFL | 25 | 11.23 | 9.21 |
| EPL | 11 | 3.96 | 3.28 |
| **total** | **36** | **15.19** | **12.48** |

**Of those 36, exactly 25 have settled -- unchanged from run 11 -- and
P(X <= 6) under the model's claim is still 0.0509.** Today's settled row was
placed **09-14** and is not in the cohort. So the pre-registered test did not
advance at all this run; the scorecard's p-value fell because the scorecard
scores *every* settled row and a 26th arrived.

Two populations, drifting apart, one of them pre-registered. Recorded now
because a future run comparing 0.0385 against run 11's 0.0509 and reading a
trend would be comparing different cohorts, and because the pre-registered
number is the one that counts.

**The 36-cohort completes on 09-21.** All 11 open members are NFL, kicking off
09-20T17:00Z through 09-21T00:20Z, carrying **4.87 claimed** and **3.96
market-implied**. Run 9's 13-wager sub-pre-registration also reproduces
(5.74 claimed / 4.72 market; the 2 settled carried 0.871 / 0.762, leaving
exactly today's 4.87 / 3.96). **Score both at 36 and at 13 on 09-21, and do not
score them again before that.** Run 11 already warned that this sample has been
scored three times against the same hypothesis with no correction for looking;
this is the fourth opportunity and it is being declined.

### The one direction inside the cohort that keeps replicating

Splitting all 26 settled rows at the median claimed edge (17.1%):

| half | n | wins | claimed | realized - claimed | mean claimed edge | ROI |
|---|---|---|---|---|---|---|
| low-edge | 13 | 4 | 5.33 | **-1.33** | 11.3% | **-7.54%** |
| high-edge | 13 | 2 | 5.37 | **-3.37** | 29.6% | **-40.28%** |

Run 9 measured -0.55 / -2.89 at n = 12/11. Same direction, larger gap, on 3
more rows. This is run 4's selection-audit signature -- the bet rule picks the
sides where the model's error is most likely positive -- and it is now the most
consistently replicating result in the project. **It is still 13 and 13.**

## Finding 4: the dead source came back, and its return audits the outage

football-data.co.uk answers again on every path tried, HTTP **200**, 20,004
bytes for `mmz4281/2627/E0.csv`. The `www` -> apex redirect remains; the
apex -> `http://127.0.0.1/` loop that defined runs 15-16 is gone.

**The duration is a range, not a number.** First observed down ~09-16T06:00Z
(run 14), last confirmed down at run 16's check ~09-17T16:0xZ, and found back
up at 09-18T06:07Z. So it was down **at least ~34 hours and at most ~48**, and
the recovery moment falls in the 14-hour gap where nothing was looking. Saying
"~44 hours" would have been inventing a precision no check supports.

**`refresh-history` exits 0 for the first time in three runs**, and the useful
part is what it wrote: `data/processed/epl_games.csv` came back **unmodified**
-- 2,700 rows, 2,700 played, byte-identical to the table runs 15 and 16 served
from cache.

That retroactively audits the outage. Runs 15-16 licensed a degraded EPL run on
the claim that the committed table was missing no played game, and that claim
rested on ESPN -- which run 16 itself noted was, for a supplemented row, both
the filler and the checker. **The primary source has now confirmed it
directly.** Nothing served during the outage was wrong.

**Run 16's supplement never fired**, then or now. No EPL fixture fell between
09-14 and 09-19, so the gap it exists to close was 0 of 40 both runs.
`ingest/sources` reports `source: upstream`, `usable: true`, `degraded: false`
for both sports. **The 09-19 fixtures will now be served by a live primary
source, so the supplement's first real exercise did not happen and has been
deferred, not passed.** It remains untested against a real gap.

`espn-audit` clean: NFL **17/17** scores and kickoffs, EPL **40/40**.
`only_espn` is **6** on soccer, up from 1, and all six are `STATUS_SCHEDULED`
with no scores -- upcoming 09-19/09-20 fixtures, not a results gap. Checked
rather than assumed, because "the cross-check found six games the primary
lacks" is the shape of a real problem.

## Finding 5: the EPL liquidity gate's interval has moved off zero

Run 14 measured the gate for the first time and found it separated adverse
quote movement on NFL but not EPL, closing with "the EPL gate is unvalidated,
not refuted". On a sample 55% larger:

| | run 14 | run 17 |
|---|---|---|
| NFL pairs | 5,122 | **9,264** |
| NFL diff `p_adverse_tick` | +10.7pp, CI [+6.4, +16.4] | **+8.67pp, CI [+5.6, +13.0]** |
| EPL pairs | 3,540 | **5,490** |
| EPL diff `p_adverse_tick` | +1.6pp, CI **[-0.4, +5.6]** | **+2.57pp, CI [+0.72, +6.92]** |

NFL: rejected quotes raise their ask by a tick before the next capture 13.92%
of the time against 5.25% for accepted ones. EPL: 5.98% against 3.41%.

**Stated with its caveats, which are not small.** This is the **second look at
the same question on a growing sample**, which is the same optional-stopping
mechanism Finding 3 declines to exploit, and a CI whose lower bound is
**+0.72pp** is a weak positive that a third look could take back. The gate is
now *evidenced* on both leagues rather than *validated* on one; it is not
proven on EPL.

**Nothing was changed on the strength of it.** The gate's thresholds were
conservative defaults and they stay conservative defaults. Run 14's note holds:
an EPL null was never an argument for loosening EPL's thresholds, and an EPL
weak positive is not an argument for tightening them.

`rejection_lead_time` still shows the gate almost never fires near kickoff --
**2 of 2,026** NFL rejections and 88 of 1,036 EPL ones inside T-72h. It filters
early boards, which is where this ledger works.

## Bets

**1 settled** (Finding 1), **1 CLV filled**, 0 backfilled, 31 unresolved at the
time of settling.

**4 new shadow rows, all NFL** -- the most NFL rows in one session since
09-11's 24, because the **week-4** board (09-27/09-28) opened:

| matchup | side | model | fair | edge | after fee | kickoff |
|---|---|---|---|---|---|---|
| CIN @ PIT | home | 0.627 | 0.448 | **+36.3%** | +31.3% | 09-27 |
| LA @ DEN | home | 0.590 | 0.448 | +28.2% | +23.5% | 09-28 |
| TEN @ NYG | away | 0.365 | 0.299 | +17.8% | +12.4% | 09-27 |
| MIN @ TB | away | 0.506 | 0.475 | +3.2% | **-0.4%** | 09-27 |

**The board's two spectacular edges were not among them, because both were
duplicates of rows already open.** `MIA @ SF` away (model 0.316 vs fair 0.105,
**+187.2%**) restates a row placed 09-12; `KC @ MIA` home (0.504 vs 0.173,
**+179.9%**) restates one placed 09-16. They are worth naming anyway, because a
model claiming the market has Miami's win probability wrong by a factor of
three -- off ratings still mostly 2025's -- is the exact object run 4's
selection audit was written about, and is what motivated Finding 2.

**`MIN @ TB` is logged with a negative after-fee edge (-0.4%).** It clears the
3% gate on gross edge and fails it on the 7% fee assumption. That is the gate
behaving as specified rather than a defect -- `edge_after_fee_pct` is reported,
not enforced (README, "The fee is reported, not enforced") -- but it is the
first new row in some time where the two disagree about whether the bet exists
at all, and it is `shadow` like everything else.

NFL flagged **21 of 55** fillable (38.2%), logged 4, 17 duplicates. EPL flagged
**10 of 29** (34.5%), logged **0**, all 10 duplicates. `illiquid_skipped` 7 NFL
and 1 EPL, `in_play_skipped` 0, `superseded_voided` 0.

### A correction to run 16's account of the NFL board

This entry's first draft opened with "the first new NFL positions in ten
runs", carried over from run 16's "the ninth consecutive run in which the NFL
board produces no new position". **The ledger does not support either
sentence, and it was caught by checking before publishing rather than by
believing the previous entry.** Non-void NFL rows by logging session:

```
09-10 17:59Z  1     09-14 06:09Z  1     09-17 06:30Z  2
09-11 15:20Z 24     09-16 06:04Z  1     09-18 06:09Z  4
09-12 06/15Z  4     09-16 15:04Z  2
```

New NFL positions were logged on 09-12, 09-14, 09-16, 09-17 and today. Run 16
did log none itself -- its EPL-only row is right -- but the run *before* it, on
the same day, logged two. The true statement is the narrow one: **today logged
4, the most in a single session since 09-11.** Nothing else in run 16 depends
on the miscount, so that entry is left as written rather than edited; the
correction lives here.

| | run 16 | run 17 |
|---|---|---|
| settled | 25 | **26** |
| wins | 6 | 6 |
| pending | 32 | **35** |
| void | 67 | 67 |
| win rate | 24.00% | **23.08%** |
| ROI | -20.87% | **-23.91%** |
| mean CLV (real close) | -1.14% (n=16) | **-1.888% (n=17)** |
| mean CLV (stale) | +4.04% (n=9) | +4.04% (n=9) |

`clv_resolution`, as required: one tick is **3.5253%** of `clv_pct` at this
ledger's mean price paid (0.3462), median reading **0.000%**, mean |move|
**1.00 ticks**, **46.2% of settled rows never moved a tick**. The -1.888% mean
is **0.54 of a tick**. The stale cohort still holds **zero negative readings**
in 9 and is still the only cohort with a positive mean -- run 10's finding that
CLV here is a function of reference staleness rather than skill is undisturbed.

Scorecard on the 26 (Finding 3 on how to read the p-value): model log-loss
**0.6408** vs market **0.5875**, Brier 0.2254 vs 0.1982, model overstatement
**+18.07pp** vs market +11.08pp. The market still beats the model on every
scoring rule, on the bets the model chose.

**Ledger integrity:** `git diff --numstat` on `bets/ledger.csv` is **5
insertions, 1 deletion** -- 4 new rows plus the one settled row rewritten in
place, across a `settle` and two `recommend` calls that each rewrote the file.
Run 15's round-trip fix is holding. 61 non-void rows, all `shadow`, 0 live.

## Regression checks

All four canonical numbers reproduce digit-for-digit, on a container that
re-resolved every dependency from scratch:

| | run 17 | runs 5-16 | match |
|---|---|---|---|
| NFL log-loss | 0.6517617405253826 | 0.6517617405253826 | digit-for-digit |
| NFL ROI | -8.208908995992267% | -8.208908995992267% | digit-for-digit |
| NFL n_games / n_bets | 1942 / 1625 | 1942 / 1625 | exact |
| EPL 2425 holdout ROI | -5.11513157894739% | -5.11513157894739% | digit-for-digit |

**pandas resolved to 3.0.6 this run, not 3.0.5.** The four numbers held across
that bump. `pyproject.toml` pins nothing exactly and flags this as a standing
risk to the project's central claim; this is the first minor-version move since
`test_benchmarks.py` was written to catch one, and it caught nothing because
there was nothing to catch. Worth recording as the test doing its job rather
than as a non-event.

Tests **295 -> 301**: six for the season-regression sweep -- the gate in both
phases, the run-12 trap, the incumbent's AUC optimality, the flatness of the
AUC gap across the grid, the holdout containing no selection season, and a
guard that the incumbent is confirmed once rather than twice when it is also
the pick.

## Data sources

| Source | Status |
|---|---|
| nflverse | Live. 2,499 games, **2,244** played (+1: `2026_02_DET_BUF`). 11 week-2/3 rows revised. |
| **football-data.co.uk** | **BACK** after 34-48h down (range, see Finding 4). HTTP 200, every path. Committed table returned byte-identical. |
| Kalshi REST | Live. **62** NFL (+13, week-4 board opened) + 30 EPL contracts. |
| ESPN scoreboard | Live. NFL 65 rows / 17 played, EPL 56 / 40. Supplement available, did not fire. |

Capture cron healthy: snapshots every ~30 min through the night, latest 04:35Z
before this run, and the T-0.21h reference in Finding 1 came out of it. This
run's own capture wrote 62 NFL and 30 EPL contracts.

## Open questions / next steps

- **Score the pre-registered cohorts on 09-21 and not before** -- 36-wager
  (claimed 15.19 / market 12.48; 25 settled, 11 open carrying 4.87 / 3.96) and
  the 13-wager subset (5.74 / 4.72). Declining the fourth look is the point.
  **Do not quote `scorecard`'s `p_at_most_model` as the pre-registered result**
  (Finding 3).
- **The CLV cohort is at 17 real-close rows and needs ~13 more to resolve a
  quarter tick.** The 11 open pre-registered wagers all settle 09-20/09-21 with
  full final-hour capture coverage, so the next run after 09-21 should be the
  first with a CLV cohort worth a real interval -- and the first able to ask
  whether CLV predicts outcomes on more than 6/8/3 rows.
- **Run 16's ESPN supplement is still untested against a real gap**, and the
  source's recovery removed the 09-19 exercise that would have tested it. It is
  deferred, not validated. Do not treat it as proven machinery.
- **`season_regression` is closed.** 0.33 stays, it is already AUC-optimal, and
  the AUC gap is flat across the grid. Do not re-raise without a new reason;
  "we could try a finer grid" is not one when the interior of the coarse grid
  spans 0.013 of AUC.
- **Five runs of apparatus work ended this run, but the apparatus answer has
  not changed.** Run 17 did sweep a real parameter and did reject it on
  evidence. What it did not do is find a direction with a reason to expect a
  different outcome, and the reasons against are now four deep: AUC deficit
  -0.046 CI [-0.064, -0.030] (run 11), context features rank worse (run 12),
  the whole pre-kickoff window is quiet (run 13), and season regression does
  not move the gap (run 17). **The honest next step is the 09-21 cohort, not
  another parameter.**
- **`PRICING_VERSION` is free to move after 09-21**, unchanged since run 10.
- **Do not re-raise:** `*/30` capture cadence (run 13), the Odds API (run 2),
  football-data.org (run 3), recalibration in any form (run 11), context
  features (run 12), `season_regression` (run 17).
- **A GitHub mirror of the football-data CSVs is moot for now** -- the source
  is back. The constraint run 16 recorded (this session may read only
  `firstdollarhq/sports-edge-lab`) still holds and is still a fact about the
  runner, not about mirrors.
- **16 stale `claude/elegant-archimedes-*` branches** sit on the remote from
  previous sessions. Harmless, not cleaned up, noted so it is not rediscovered.
- NFL preseason markets are priced and settled by Kalshi but invisible to
  nflverse; labelled, not fixable.
- **Standing reminder:** 0 live bets. **26 settled shadow bets, 6 wins, ROI
  -23.91%.** The market beats the model on every scoring rule on the bets the
  model itself chose; the one row that settled this run is a side the market
  spent four days walking away from, and it was right to; CLV reads no
  detectable edge and shows no ordering against outcomes; and the
  claimed-edge overstatement gap widens with the size of the claim. **It is 26
  wagers. That still keeps all of it provisional, in both directions.**

## Process note

The stored scheduled prompt still carries "do not post, send, change, or
delete anything" and the unfilled `[which data sources?]` placeholder.
CLAUDE.md has overridden the first for repository work since 2026-09-11 and
settled the second since 2026-09-13. Noted once, per CLAUDE.md, and not
escalated.

**Escalations: none.** No charge and no signup form is outstanding.
