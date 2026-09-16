# Scheduled run 14 -- the liquidity gate is checked for the first time, and works on one league of two

_2026-09-16, 15:01-16:5xZ. Run 13 was earlier the same day, 06:01-07:5xZ._

## Headline

**The filter that has gated every price this project ever recommended got
validated today, and the answer differs by league.**

`betting/liquidity.py` has decided which quotes are real since run 1. Its own
docstring calls its thresholds "deliberately conservative defaults, not tuned
values", and run 13 listed validating them as "the obvious next apparatus
question". Measured on 5,122 NFL and 3,540 EPL consecutive-capture pairs:

- **NFL: the gate separates.** A rejected quote raises its ask by at least one
  tick before the next capture **16.9%** of the time against **6.2%** for an
  accepted one -- **+10.7pp, CI [+6.4, +16.4]**. The 5% relative-width rule
  *in isolation* is **+18.1pp, CI [+7.6, +32.3]**.
- **EPL: nothing.** **+1.6pp, CI [-0.4, +5.6]**, and both powered strata
  straddle zero individually.

**A bug in my own measurement changed every number above, and it was caught by
a test written after the analysis rather than before.** `0.41 - 0.40` is
`0.009999999999999953`, so `delta >= 0.01` is **False** for an exact one-tick
rise on a venue that quotes whole cents. Details in Finding 2.

**No bets settled. Two new shadow rows logged.** Ledger unchanged from runs
11-13: 25 settled, 6 wins, **24.0%**, ROI **-20.87%**. `live_enabled` stays
`false` everywhere. **Nothing was changed on the strength of today's finding.**

Tests **256 -> 266**.

## Finding 1: the gate works on NFL, does nothing on EPL, and never fires near kickoff

### What could and could not be tested

The gate claims two jobs, in `liquidity.py`'s words: a wide relative book means
"the de-vigged fair probability we measure disagreement against is unreliable,
and size is unlikely to fill near the touch."

**Neither is directly testable and I should say so before the numbers.** This
project has never placed an order and cannot while `live_enabled` is false, so
there is no realized fill to compare a quote against. Run 13's open item asked
for validation "against realized fill quality"; **that is not an available
measurement and asking for it again next run would waste the run.**

What the committed snapshots *can* answer -- and the only reason they can is
the 30-minute cron, ~30 pre-kickoff captures per NFL contract -- is quote
persistence:

    P(the ask rises at least one tick before the next capture)

over consecutive captures of the same contract, 20-75 minutes apart. That is
the observable shadow of the first job, and it is narrower than the claim it
tests. The write-up says "persistence", not "fill quality", everywhere.

### The structural fact that shapes the whole analysis

**The gate rejects essentially nothing near kickoff: 0 of 1,084 NFL rejections
and 1 of 880 EPL ones sit inside T-72h.** Depth and volume build as a game
approaches, so the thresholds stop binding. This is not a footnote -- it means
a raw pass/fail comparison is largely a comparison of *early boards against
late ones*, and early boards move more for reasons that have nothing to do
with the gate. Every number below is therefore stratified by time to kickoff.

It also means the gate is not idle: **57% of this ledger's non-void rows were
priced more than 72h out** (median lead time 103.9h), which is exactly where
the gate lives.

### NFL

| stratum | rejected | accepted | diff | CI (clustered) |
|---|---|---|---|---|
| overall | 16.9% (n=1084) | 6.2% (n=4038) | **+10.7pp** | **[+6.4, +16.4]** |
| T-72h..T-120h | 91.7% (n=12) | 3.4% (n=956) | +88.3pp | *underpowered* |
| T-120h..T-168h | 49.7% (n=147) | 7.2% (n=2007) | **+42.4pp** | **[+33.4, +52.2]** |
| T-168h..T-216h | 32.4% (n=105) | 14.8% (n=345) | **+17.6pp** | **[+4.2, +33.7]** |
| T-216h..T-264h | 8.6% (n=35) | 8.0% (n=25) | +0.6pp | [-14.3, +41.7] |
| T-264h+ | 7.9% (n=785) | 2.1% (n=237) | **+5.8pp** | **[+3.2, +9.1]** |

**Three of the four powered strata exclude zero and all four point the same
way.** The one that does not (T-216h..T-264h) is 35 quotes against 25.

The **5% relative-width rule alone** -- evaluated only on rows that clear every
other check, so it is not credited with volume's rejections -- is **24.3% vs
6.2%, +18.1pp, CI [+7.6, +32.3]**. That interval is wide because the rejected
arm is 70 quotes from **15 contracts**, and it is reported with that attached.

### EPL

| stratum | rejected | accepted | diff | CI (clustered) |
|---|---|---|---|---|
| overall | 6.1% (n=880) | 4.5% (n=2660) | +1.6pp | [-0.4, +5.6] |
| T-72h..T-120h | 4.6% (n=308) | 3.0% (n=1477) | +1.6pp | [-1.3, +10.5] |
| T-120h..T-168h | 6.9% (n=563) | 7.1% (n=904) | -0.2pp | [-3.6, +4.0] |
| width rule alone | 5.3% (n=151, **6 contracts**) | 4.5% (n=2660) | +0.8pp | [-4.9, +14.1] |

Every interval straddles zero. On EPL this gate is currently removing about a
third of contracts without any detectable difference in what those contracts
then do.

### The bootstrap has to cluster, and it changes the answer

~30 captures of one contract are not 30 independent observations. Resampling
quotes gave the NFL width rule CI **[+5.8, +24.2]**; resampling **contracts**
gives **[+5.4, +27.6]** -- about 40% wider, and on the EPL overall comparison
the naive interval [-0.3, +5.1] was near enough to excluding zero to be
tempting. The clustered one is not. **The conclusion survives clustering on
NFL; on EPL, clustering is part of why there is no conclusion.**

### What this does NOT license

**Nothing was changed.** In particular the EPL null is *not* an argument for
loosening EPL's thresholds:

- This instrument says what a quote **does**, not what a looser gate would do
  to ROI. Letting 880 more quotes through is a pricing change, and a pricing
  change is decided by backtest -- the same standard that rejected the
  fee-inclusive threshold in run 10 after it looked obviously right.
- `PRICING_VERSION` is frozen until 09-21 by run 10's decision, which has not
  expired.
- The EPL rejected arm is **24 contracts** and the width-rule arm is **6**.
  That is a small number of football matches, not a fact about the league.

The honest state: **the NFL gate earns its keep; the EPL gate is unvalidated
rather than refuted**, and the distinction matters because "we measured nothing"
and "we measured no effect" get confused in exactly the direction that suits
whoever wants to loosen a filter.

## Finding 2: an exact one-tick move did not count as a move

The first version of this module asked `(next_ask - ask) >= 0.01`. On a venue
that quotes whole cents that should be the commonest event in the data. It is
also, in binary floating point, **sometimes false**:

```
0.41 - 0.40 = 0.009999999999999953   ->  not a tick
0.33 - 0.32 = 0.010000000000000009   ->  a tick
```

So one-cent moves were counted or dropped **depending on the price**, which
makes the error price-dependent rather than merely low. Every published figure
moved when it was fixed:

| | before | after |
|---|---|---|
| NFL rejected | 14.9% | 16.9% |
| NFL accepted | 5.5% | 6.2% |
| NFL width rule, diff | +14.5pp | **+18.1pp** |
| EPL width rule, diff | **-1.4pp** | **+0.8pp** |

**The EPL width-rule figure changed sign.** Both readings straddle zero, so the
conclusion is the same either way -- but the pre-fix number would have been
written up as "EPL's width rule points the wrong way", which is a sentence
about a floating-point artifact. Nothing was published from the bad pass.

Two things worth recording about *how* it was caught. It was found by a test
written **after** the analysis, asserting a hand-computed expectation on four
synthetic quotes -- the analysis itself looked entirely plausible and its
NFL conclusion was directionally right. And the fix is not a tolerance: prices
are integers on this venue, so the difference is converted to whole ticks and
compared as an integer. The test now checks **every adjacent cent pair from
0.01 to 0.98** rather than the one that happened to fail.

**This is the fourteenth instance of this project's recurring failure -- a
value that is not what the surrounding code assumed.** The previous thirteen
were mostly semantic (a scrambled week order, an expiration mistaken for a
kickoff, a season label that was a string on one side and an int on the other).
This one is arithmetic, and it is the first that a reader could not have caught
by reading the code carefully, only by running it.

## Finding 3: the module published a confidence interval over one contract

Caught in the same pass. The first draft emitted, for the EPL T-0h..T-72h
stratum, a 95% CI of **[-0.061, -0.025]** on a rejected arm of **one quote from
one contract**, and **[0.000, 0.250]** on an arm of eight. A cluster bootstrap
over one cluster resamples the same rows and returns a tight interval that is a
restatement of its input -- it reads as a result and contains no information.

Cohorts below **20 quotes or 3 contracts in either arm** now report
`"underpowered"` and no interval. The point estimate and both arm counts stay
visible, so a reader can see the cohort is thin rather than having the row
disappear. Pinned by two tests, one either side of the threshold.

This is the same class of defect as run 13's `clv_resolution` work: a number
that is arithmetically correct and rhetorically misleading. The remedy is the
same -- ship the context next to the number so it cannot be quoted alone.

## Bets

**Nothing settled.** 26 pending at the start, 0 resolved, 0 CLV filled, 0
backfilled. NFL week 2 opens 09-17T00:15Z; the first pending row settles then.

**Two new rows logged**, both `shadow`, out of 27 flagged recommendations:

| matchup | side | model | fair | edge | after fee | kickoff |
|---|---|---|---|---|---|---|
| NYJ @ DET | away | 0.269 | 0.236 | +12.0% | +6.3% | 2026-09-27T17:00Z |
| KC @ MIA | home | 0.504 | 0.185 | **+165.2%** | +151.0% | 2026-09-27T17:00Z |

The rest were duplicates of open rows: NFL 18 flagged of 47 fillable (38.3%),
EPL 9 of 27 (33.3%), `skipped_duplicate` 16 and 9. `illiquid_skipped` 17 NFL
and 3 EPL, `in_play_skipped: 0`, `superseded_voided: 0`. The NFL board fell
from 64 to 47 contracts as week 1 markets expired.

**KC @ MIA at +165.2% is the same winner's-curse signature runs 4, 11 and 13
recorded**, now on a week-4 contract: the model says 0.504 where the market's
fair price is 0.185. The largest claimed edge on the board has been a
freshly-listed, thinly-traded contract in every run that has looked, which is
the pattern Finding 1 has now independently measured from the other side --
early boards are where the gate rejects, and early boards are where the model
finds its biggest "edges". **Those two facts have not been joined up with a
number yet and that is the obvious next piece of work.**

Ledger after this run:

| | run 13 | run 14 |
|---|---|---|
| settled | 25 | 25 |
| wins | 6 | 6 |
| pending | 26 | **28** |
| void | 67 | 67 |
| win rate | 24.00% | 24.00% |
| ROI | -20.87% | -20.87% |
| mean CLV (real close) | -1.14% (n=16), 0.38 ticks | unchanged, n=16 |

Integrity: **53 non-void rows = 53 distinct `bet_id` = 53 distinct
(game, selection, market).** Every row `shadow`.

**The pre-registered cohort was again not re-scored**, for the third run
running. Run 11 fixed the honest read at 36 wagers on 09-21; nothing settled
today, so running `scorecard` would have been a fifth look at a partial cohort
with no correction for having looked. **11 wagers still to kick off, the first
at 09-18T00:15Z.**

## Regression checks

All four canonical numbers reproduce digit-for-digit:

| | run 14 | runs 5-13 | match |
|---|---|---|---|
| NFL log-loss | 0.6517617405253826 | 0.6517617405253826 | digit-for-digit |
| NFL ROI | -8.208908995992267% | -8.208908995992267% | digit-for-digit |
| NFL n_games / n_bets | 1942 / 1625 | 1942 / 1625 | exact |
| EPL 2425 holdout ROI | -5.11513157894739% | -5.11513157894739% | digit-for-digit |

Re-derived by `test_benchmarks.py` from the committed tables. `espn-audit`
clean: NFL 16/16 scores and kickoffs agreed, EPL 40/40, `only_espn: 0` and
`only_primary: 0` both. `verify-settlements` clean: NFL 32/32, soccer 120/120,
`unmatched_in_coverage: 0`, 94 NFL unmatched all out-of-coverage (preseason).

ESPN's month-walk fix from run 13 held on its second run -- no warnings, both
committed ESPN tables unmodified.

Tests 256 -> 266: ten for `fill_quality` (the inherited bucket-width trap, the
`keep_cols` pass-through, tick arithmetic across all 97 adjacent cent pairs,
the blackout-gap exclusion, the in-play exclusion, the underpowered guard on
both sides of its threshold, width-rule isolation, and the empty-history case).

`line_movement.collect_quotes` grew a `keep_cols` argument so the new module
gets its order-book columns from there **rather than re-deriving kickoff for
itself**. That is a direct application of run 13's lesson: an ad-hoc
re-derivation of kickoff is how that run got a mean move eight times too large
from contracts that had already settled.

## Data sources

| Source | Status |
|---|---|
| nflverse | Live. 2,499 games, 2,243 played. Week 2 sportsbook lines moving; 7 rows revised. |
| football-data.co.uk | Live. E0 2026-27 at 40 played, unchanged. |
| Kalshi REST | Live. **47** NFL + 27 EPL contracts (week 1 expired off the board). |
| ESPN scoreboard | Live. NFL 64 rows / 16 played, EPL 50 / 40. Month walk held. |

Capture cron healthy: snapshots every ~30 minutes, most recent commit 14:36Z,
~25 minutes before this run started.

**Escalations: none.** No charge and no signup form is outstanding.

## Open questions / next steps

- **Join up Finding 1 with the winner's-curse pattern.** The gate rejects early
  boards; the model's largest claimed edges appear on early boards; both
  observations are now several runs old and neither has been expressed as a
  number against the other. Concretely: does claimed edge decay with
  time-to-kickoff, and does it decay faster on contracts the gate rejects?
  **This is the next piece of work and it needs no new data source.**
- **The EPL gate is unvalidated, not refuted, and loosening it is a backtest
  question.** Do not treat run 14's null as licence. 24 contracts.
- **Do not ask again for validation "against realized fill quality".** It is
  not measurable in a paper-trading project and will not become measurable by
  waiting. Quote persistence is the available proxy and it has now been run.
- **The honest null remains the leading hypothesis.** Nothing today touched the
  model; both findings are in the measurement apparatus, as in run 13. Two
  consecutive runs of apparatus-only work is worth noticing -- it is the right
  call when the apparatus is wrong, and it is also what a project with no model
  ideas left looks like. **Run 15 should either produce a model idea with a
  stated reason to expect a different outcome, or say plainly that it has
  none.**
- **CLV needs ~14 more real-close rows to resolve a quarter tick** (30 total,
  16 now). Week 2 settles 09-18 to 09-22 and should add most of them. Read it
  against `clv_resolution`, never alone.
- **Score the pre-registered cohort at 36 on 09-21 and treat that as the read.**
  Do not re-score the partial cohort; runs 12, 13 and 14 did not.
- **After 09-21, `PRICING_VERSION` is free to move**, unchanged since run 10.
- Nothing in `pyproject` is pinned exactly; `test_benchmarks.py` catches the
  consequences rather than preventing them.
- NFL preseason markets are priced and settled by Kalshi but invisible to
  nflverse; labelled, not fixable.
- **ESPN is undocumented and broke once (run 13).** `espn-audit` runs every
  run. Expect it again.
- **Standing reminder:** 0 live bets. 25 settled shadow bets, 6 wins, ROI
  **-20.87%**. The market beats the model on every scoring rule on the bets the
  model itself chose; the model ranks games significantly worse than the
  closing line; the free information meant to close that gap made it wider; and
  CLV reads no detectable edge at half-tick precision. Today's finding is that
  one *filter* in the apparatus does its job on one league. **A working filter
  is not an edge.** It is still 25 wagers.

## Process note

The stored scheduled prompt still carries "do not post, send, change, or
delete anything" and the unfilled `[which data sources?]` placeholder.
CLAUDE.md has overridden the first for repository work since 2026-09-11 and
settled the second since 2026-09-13. Noted once, per CLAUDE.md, and not
escalated.
