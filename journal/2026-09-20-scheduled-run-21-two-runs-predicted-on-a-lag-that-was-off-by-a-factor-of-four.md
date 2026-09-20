# Scheduled run 21 -- two runs predicted on a lag that was off by a factor of four

_2026-09-20, 06:01-06:5xZ. Run 20 ran 15:02-15:5xZ the previous afternoon._

## Headline

**The ledger's ROI turned positive for the first time, and it is not a
result.** Four EPL wagers settled. One of them, `Coventry @ Nott'm Forest`
away, paid **5.8824**. Ledger **29 -> 33 settled, 8 -> 10 wins, 27.59% ->
30.30%, ROI -8.23% -> +3.98%**. Strip that one row and the ledger reads
**-5.23%**. Run 20 said the same thing about its own ten-point move on one
3.70 winner, and run 19 about its 5.7-point move on two rows; the statistic is
being reported because the project reports it, not because it means anything
at n=33. **No deployment gate moves** -- the gate keys on out-of-sample
backtest against the de-vigged closing line, not on the shadow ledger, and EPL
still fails it at -5.115%.

**The finding this run spent itself on is that runs 19 and 20 both built a
falsifiable prediction on a placement lag that is wrong by a factor of four,
and the correct number inverts the prediction.** Both entries state that the
11 open pre-registered wagers were "placed at T-48h to T-56h" and should
therefore *lower* the CLV standard deviation when they settle. The ledger says
they were struck at **T-217.7h to T-225.0h**. Under the lag-variance mechanism
those same entries invoke, the longest-lag rows in the book should **raise**
the SD. The prediction was not merely unsupported; it pointed the wrong way.

**The relationship it rests on also weakened this run, on exactly the rows
that should have confirmed it.** `corr(lag, |ticks|)` fell **0.628 (n=20) ->
0.4223 (n=24)** and the cluster bootstrap widened back to **[0.054, 0.722]**
from run 20's [0.207, 0.818]. Run 20 wrote that it was "no longer hanging on a
hair". Four rows put it back on one.

What survived is a diagnostic -- `ledger-summary` now computes placement lag
per cohort instead of leaving it to prose -- and a replacement pre-registration
written before today's 17:00Z kickoffs. Tests **332 -> 338**.

## Finding 1: the lag was never computed, so it was wrong for two runs

### What the entries say, and what the ledger says

Run 19, in its own words:

> The 11 open pre-registered wagers settle 09-20/21 with full final-hour
> coverage and were placed at T-48h to T-56h, so they should *lower* the SD --
> which is the prediction to check next run, and a falsifiable one.

Run 20 carried it forward verbatim. Reconstructing the cohort from `placed_at`
exactly as the README specifies (1 row 09-10 + 35 rows 09-11):

| quantity | runs 19-20 said | ledger says |
|---|---|---|
| open rows | 11 | **11** |
| claimed wins | 4.87 | **4.8692** |
| market-implied (de-vigged) | 3.96 | **3.9578** |
| **placement lag** | **T-48h to T-56h** | **T-217.7h to T-225.0h** |

Everything in that prediction is right except the one quantity it turns on.
The 11 rows were all struck at `2026-09-11T15:20:50Z` against kickoffs from
09-20T17:00Z to 09-21T00:20Z -- nine days, not two.

### Where T-48h to T-56h came from

It is a real number from the same ledger, attached to the wrong cohort. The
**settled** real-close cohort runs from a minimum of **48.15h** with a median
of **53.07h**:

| cohort | n | min | median | max |
|---|---|---|---|---|
| settled, real close | 24 | **48.1h** | **53.1h** | 142.6h |
| **pending** | 32 | 9.3h | **217.7h** | 278.0h |

"T-48h to T-56h" is the settled cohort's range read off and handed to the open
book. The two ranges **do not overlap**: every open pre-registered row sits
beyond the longest settled lag in the project.

### Why it survived two runs

**Nothing computed it.** `ledger-summary` reported the SD, the SE, the
interval and `n_for_target_se`, and `_clv_precision`'s own docstring explains
at length that the cohort's variance is a function of placement lag -- but the
lag itself appeared in no tool output. It lived in prose, was copied from run
19's entry into run 20's, and each copy made it more load-bearing.

This is the second time this project has carried a hand-written number between
runs and had it turn out wrong -- run 19 caught the tick conversion the same
way. The pattern is the same: a quantity that is cheap to compute, quoted from
memory because it was quoted last time.

### The prediction runs backwards

The mechanism runs 19 and 20 cited is that CLV magnitude scales with placement
lag. Taking it at face value, 11 rows at T-220h are the **longest-lag rows the
ledger has ever held** -- 1.5x beyond the settled maximum -- and should carry
the **largest** moves, raising the SD. The written prediction says the
opposite. Whichever way the rows land tomorrow, the prediction as recorded
cannot be scored, because it does not follow from the premise it was derived
from.

## Finding 2: the lag-variance relationship weakened on the rows that should have confirmed it

Four rows settled. Three of them were long-lag, which is where the
relationship makes its strongest claim:

| bet | lag | \|ticks\| | predicted by the relationship |
|---|---|---|---|
| `3a2be772` Coventry away | 49.3h | 1 | short lag, small move -- consistent |
| `2e4b2951` Ipswich home | 103.9h | **0** | long lag, **no move at all** |
| `9d078844` Hull away | 142.6h | 2 | longest lag in the book, small move |
| `8b2b48e5` Hull draw | 142.6h | 1 | longest lag in the book, small move |

| | run 20 (n=20) | run 21 (n=24) |
|---|---|---|
| `corr(lag, \|ticks\|)` | 0.628 | **0.4223** |
| cluster bootstrap 95% CI | [0.207, 0.818] | **[0.054, 0.722]** |
| clusters | 18 games | 21 games |
| sd (ticks) | 2.403 | **2.2518** |
| `n_for_target_se` | 92 | **81** |

The bucket means are now **non-monotone** at the top -- 48-60h **0.87**,
60-100h **2.67**, 100-143h **2.33** -- so the linear fit is being held up by a
middle bucket of n=3.

Run 20's framing ("no longer hanging on a hair") was a statement about a lower
bound that had cleared zero by 0.207 at n=20. At n=24 it clears by 0.054.
**Suggestive, and now barely that.** The honest reading is that this
relationship has been re-estimated four times and has moved every time, which
is what n=24 across 21 clusters buys.

## Finding 3: the replacement pre-registration, written before kickoff

Written 2026-09-20 at ~06:30Z. The 11 rows kick off from **17:00Z today** --
about ten and a half hours from now -- so this is recorded before any of them
can be observed.

Combining 11 arriving rows with the current cohort (n=24, sd 2.2518) is
monotone in one quantity, the RMS |ticks| of the arrivals, with a **crossover
at RMS ~ 2.3**:

| RMS \|ticks\| of the 11 | combined sd | `n_for_target_se` | verdict |
|---|---|---|---|
| 1.00 | 1.935 | 60 | SD falls |
| 1.27 (cohort's current mean abs) | 1.984 | 63 | SD falls |
| 2.00 | 2.161 | 75 | SD falls |
| **2.33** | **2.260** | **82** | **crossover** |
| 3.00 | 2.488 | 100 | SD rises |
| 4.54 (linear extrapolation to T-220h) | 3.113 | 156 | SD rises |

**Predicted: RMS |ticks| above 2.3, and the real-close SD rises above
2.2518.**

**This is an extrapolation and is labelled as one.** T-220h is 1.5x beyond the
cohort's longest settled lag, and the bucket means are already non-monotone at
the top, so the fit's 4.54 is the optimistic end of the claim rather than its
centre. **If RMS lands below 2.3, the lag-variance relationship has failed
out-of-sample at long lag**, and the explanation behind `n_for_target_se`'s
instability needs rewriting rather than patching. That is the falsifiable half.

All 11 kickoffs (17:00Z, 20:05Z, 20:25Z, 09-21T00:20Z) fall inside the capture
cron's `0-4,10-23` window, so real closes should be available for all of them.

## Finding 4: run 20's rejected correction resolved live, and made money

All three debutant rows from run 20's Finding 1 settled:

| bet | fixture | side | claimed | paid | result | net |
|---|---|---|---|---|---|---|
| `9d078844` | Hull @ Newcastle | away | 0.252 | 6.2500 | **lost** | -1.000 |
| `8b2b48e5` | Hull @ Newcastle | draw | 0.247 | 4.7619 | **lost** | -1.000 |
| `3a2be772` | Coventry @ Nott'm Forest | away | 0.206 | 5.8824 | **won** | **+4.882** |

**Net +2.882 units on three wagers.** Run 20's rejected correction would have
declined all three, so adopting it would have turned this ledger's +3.98% into
**-5.23%**.

**This does not reopen the promotion prior, and it is written down so that it
cannot be used to.** The rejection rests on six seasons out-of-sample with a
season-cluster CI on log-loss of [-0.00255, +0.00058] and ROI moving the wrong
way. Three wagers cannot overturn that, and run 20 explicitly anticipated this
variance -- its own per-team ROI ranged from -81.67% to +44.09%. The
temptation this creates is the exact bias the project exists to resist: a
rejected change that would have cost 9 points of ROI is *more* tempting to
reopen than one that changed nothing, and the evidence is no better than it
was yesterday. **The bias measurement stands, and so does its verdict.**

## Finding 5: the optional-stopping argument, demonstrated instead of asserted

Runs 11 through 20 all warned that `scorecard`'s `p_at_most_model` is a
running statistic with no correction for looking, and is not the pre-registered
result. This run it can be shown rather than argued:

| run | `scorecard` `p_at_most_model` | pre-registered P(X <= 6), 25 of 36 |
|---|---|---|
| 11 | 0.0509 | 0.0509 |
| 17 | **0.0385** | **0.0509** |
| 19, 20 | not recorded numerically | **0.0509** |
| **21** | **0.1581** | **0.0509** |

The scorecard's p-value has moved **0.0385 -> 0.1581 on four settled wagers**,
while the pre-registered reading sat still the whole time because none of the
four belongs to the cohort. **A run that had stopped at 0.0385 and called it a
rejection would be un-rejecting it today.** That is optional stopping caught in
the act, on this project's own numbers.

**The cohort was not scored -- the eighth declined look.** It reconstructs
exactly as run 20 left it: **36 wagers (25 NFL, 11 EPL), 25 settled, 6 wins,
11 open**, all NFL, carrying **4.8692 claimed / 3.9578 market-implied**. The
four rows that settled this run were placed 09-13 through 09-17 and are **not**
in it, so **P(X <= 6) is still 0.0509**. The 11 open rows kick off today and
tomorrow. **Score on 09-21**, which is now the first run at which the full 36
exist.

## Finding 6: the EPL leg leads the market on log-loss, on 18 rows

Worth recording because it is the first time, and worth not over-reading:

| leg | rows | wins | model LL | market LL | gap | ROI |
|---|---|---|---|---|---|---|
| NFL | 15 | 4 | 0.6736 | **0.6373** | +0.0364 | -17.38% |
| **EPL** | 18 | 6 | **0.6141** | 0.6261 | **-0.0120** | +21.78% |
| all | 33 | 10 | 0.6411 | **0.6312** | +0.0100 | +3.98% |

Pooled, the market is still ahead, and its expected-wins figure (**10.78**) is
far closer to the actual **10** than the model's (**13.21**). The EPL leg is
18 self-selected wagers; the six-season EPL holdout still returns **-5.115%**.
**This is not a signal and is not treated as one.** It is logged because a run
that only records the legs that lose is not keeping an honest journal.

## Bets

**4 settled, 4 CLV filled, 0 backfilled, 1 new row logged, 32 pending.**

| bet | side | claimed | paid | closed | CLV | ticks | lag | result |
|---|---|---|---|---|---|---|---|---|
| `8b2b48e5` | Hull draw | 0.247 | 4.7619 | 4.5455 | +4.76% | **+1** | T-142.6h | lost |
| `9d078844` | Hull away | 0.252 | 6.2500 | 5.5556 | +12.50% | **+2** | T-142.6h | lost |
| `2e4b2951` | Ipswich home | 0.642 | 1.8182 | 1.8182 | 0.00% | **0** | T-103.9h | **won** |
| `3a2be772` | Coventry away | 0.206 | 5.8824 | 6.2500 | -5.88% | **-1** | T-49.3h | **won** |

All four priced against references at **T-0.45h to T-0.46h** -- real closes,
from the `*/30` cron, on fixtures that kicked off while no session was running.

**1 new row logged**, EPL: `Man United @ Fulham` draw (claimed 0.262 vs market
0.244, **+4.7%**, **-0.5% after fee**). NFL flagged **24 of 59** fillable
(40.7%), all 24 duplicates of open rows, `illiquid_skipped` 3, `in_play_skipped`
0. EPL flagged **3 of 10** (30.0%), 2 duplicates, `illiquid_skipped` 2,
`in_play_skipped` 0. `superseded_voided` 0. `thin_history` reports **0** on
both sports -- Coventry's row settled and Hull's fixtures are past, so the
counter run 20 added has nothing to flag this morning.

| | run 20 | run 21 |
|---|---|---|
| settled | 29 | **33** |
| wins | 8 | **10** |
| pending | 35 | **32** |
| void | 67 | 67 |
| win rate | 27.59% | **30.30%** |
| ROI | -8.23% | **+3.98%** |
| mean CLV (real close) | -0.823% (n=20) | **-0.212% (n=24)** |
| mean CLV (stale) | +4.04% (n=9) | +4.04% (n=9) |

`clv_resolution`, with the tick beside it as CLAUDE.md requires: one tick is
**3.5569%** of `clv_pct` at this ledger's prices; median reading **0.000%**;
mean **1.2727** ticks absolute; **39.4%** of settled rows never moved a tick.
The -0.212% mean is **-0.060 of a tick**. **Every settled CLV in the ledger is
still an exact integer in ticks** (max deviation 8.4e-15), which is the
standing check that run 19's conversion is right.

`clv_precision_real_close`: n **24**, mean **-0.125 ticks**, median 0.000, sd
**2.2518**, SE **0.4596**, 95% CI **[-1.026, +0.776]**, `n_for_target_se`
**81**.

`placement_lag_real_close` (new): n 24, **48.1h / 53.1h / 142.6h**.
`placement_lag_pending` (new): n 32, **9.3h / 217.7h / 278.0h**.

## Regression checks

All four canonical numbers reproduce digit-for-digit, **run before and after
this run's change**:

| | run 21 | runs 5-20 | match |
|---|---|---|---|
| NFL log-loss | 0.6517617405253826 | 0.6517617405253826 | digit-for-digit |
| NFL ROI | -8.208908995992267% | -8.208908995992267% | digit-for-digit |
| NFL n_games / n_bets | 1942 / 1625 | 1942 / 1625 | exact |
| EPL 2425 holdout ROI | -5.11513157894739% | -5.11513157894739% | digit-for-digit |

The only production change is two additive diagnostic keys on
`ledger-summary`'s output, so these were expected to hold; the check is that
they did, on both sides of the edit.

pandas resolved to **3.0.6** again, numpy 2.4.6, scikit-learn 1.9.1.

Tests **332 -> 338**. Six, in `tests/test_placement_lag.py`: that the settled
and pending lag ranges are reported apart and do not overlap (the exact
confusion that produced the error), that a missing kickoff reports no lag
rather than T-0, that an empty ledger is clean, that the diagnostic mutates no
row -- asserted so a later run cannot quietly turn placement lag into a filter,
which run 19 already established it must not be -- and two that re-derive the
correction from the committed ledger, so it is reproducible from the repo
rather than living only in this entry.

## Data sources

| Source | Status |
|---|---|
| nflverse | Live. 2,499 games, 2,244 played, latest 2026-09-17. |
| football-data.co.uk | **Intermittent** -- 504s on 2 of 5 attempts; succeeded on retry. Still lagging: 2,700 / 2,700 played, latest row **2026-09-14**, now **6 days** behind. |
| Kalshi REST | Live. 59 NFL + 10 EPL contracts priced this session. |
| ESPN scoreboard | Live (one transient TLS EOF, clean on retry). NFL 17/17 scores and kickoffs agree, EPL 40/40 agree. |

`espn-audit` clean: **0 score and 0 kickoff disagreements on either sport**.
`only_espn` is **10** on soccer -- the primary's six-day lag, quantified.
`verify-settlements` **34/34 NFL and 138/138 soccer**, 0 unmatched in coverage
-- soccer up from 126 last run. The ESPN supplement remains load-bearing on
the normal path, not just the outage path.

Capture cron healthy: 11 captures today, median inter-capture gap **32.2 min**.
The single 96-minute gap is the by-design 05:00-09:59Z window where `*/30
0-4,10-23` does not fire, not a dropped run.

## Open questions / next steps

- **Score the pre-registered cohort on 09-21.** 36 wagers, 25 settled, 6 wins,
  11 open NFL carrying **4.8692 claimed / 3.9578 market-implied**, P(X <= 6) =
  **0.0509**. Eighth opportunity to look early, eighth refusal. **Do not quote
  `scorecard`'s `p_at_most_model`** -- it is at **0.1581** today against
  0.0385 at run 17, which is exactly why.
- **Score run 21's SD pre-registration against the table in Finding 3.**
  Predicted RMS |ticks| **above 2.3** and SD **above 2.2518**. Crossover 2.33.
  Quote the current run's `n_for_target_se`, never an old journal's.
- **Run 19's SD prediction is withdrawn, not scored.** It was derived from a
  lag that is wrong by a factor of four and pointed the wrong way. Do not
  record it as having been tested.
- **The lag-variance relationship is weaker than run 20 left it.**
  `corr(lag, |ticks|)` **0.4223** at n=24, cluster bootstrap **[0.054, 0.722]**
  over 21 games, down from 0.628 / [0.207, 0.818]. Bucket means non-monotone at
  the top. **Suggestive, barely.** Re-estimate it next run rather than quoting
  this one.
- **Do not reopen the promotion prior on the strength of +2.882 units.** Run 20
  rejected it on six seasons out-of-sample; three wagers is not evidence, and a
  rejected change that *would* have been profitable is the most tempting kind
  to reopen for the worst reason.
- **The EPL leg leading on log-loss is 18 self-selected rows** against a
  six-season holdout of **-5.115%**. Not a signal. Revisit only if it survives
  the cohort completing.
- **Read CLV in ticks, and quote `n_for_target_se` beside the mean.** One tick
  is **3.5569%** at this ledger's prices. The mean is **-0.125 ticks**, CI
  ±0.90 ticks.
- **Placement lag is not a variance knob** (run 19). Unchanged, and now
  asserted by a test.
- **Compute quantities rather than quoting them.** Two runs' reasoning rested
  on a hand-copied lag. Both hand-copied numbers this project has caught -- the
  tick conversion (run 19) and this lag -- were cheap to compute and quoted
  from the previous entry instead. If a number appears in a journal entry and
  in no tool's output, that is the thing to check first.
- **football-data.co.uk is intermittent as well as lagging.** 504s on 2 of 5
  attempts this run, and 6 days behind. It is not down and needs no
  replacement; if the lag reaches a fortnight or retries stop succeeding, the
  ESPN supplement already covers settlement and the question becomes whether
  the *odds* columns need a second source. Not yet.
- **Do not re-raise:** `*/30` capture cadence (runs 9, 13, 19), the Odds API
  (run 2), football-data.org (run 3), recalibration (run 11), context features
  (run 12), `season_regression` (run 17), an upper edge cap (run 18), the
  promotion prior (run 20), weather (runs 12, 18).
- **Seven reasons deep on why the model loses**, unchanged by this run, which
  tested no model change. **No bet-rule change remains with a reason to expect
  a different outcome.** The honest next step is still the 09-21 cohort.
- **`PRICING_VERSION` is free to move after 09-21**, unchanged since run 10.
- NFL preseason markets are priced and settled by Kalshi but invisible to
  nflverse; labelled, not fixable.
- **Standing reminder:** 0 live bets. **33 settled shadow bets, 10 wins, ROI
  +3.98%** -- **positive for the first time, on one 5.88 winner, and worth
  nothing.** Strip that row and it is -5.23%. The market still beats the model
  pooled on every scoring rule, on the bets the model itself chose, and it is
  **33 wagers**, which keeps all of it provisional.

## Process note

The stored scheduled prompt still carries "do not post, send, change, or
delete anything" and the unfilled `[which data sources?]` placeholder.
CLAUDE.md has overridden the first for repository work since 2026-09-11 and
settled the second since 2026-09-13. Noted once, per CLAUDE.md, and not
escalated.

**Escalations: none.** No charge and no signup form is outstanding.
