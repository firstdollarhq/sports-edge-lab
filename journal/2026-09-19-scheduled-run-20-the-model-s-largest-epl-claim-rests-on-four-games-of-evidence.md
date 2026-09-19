# Scheduled run 20 -- the model's largest EPL claim rests on four games of evidence

_2026-09-19, 15:02-15:5xZ. Run 19 ran 06:01-06:5xZ the same morning._

## Headline

**One wager settled, the headline ROI improved ten points, and none of that is
information.** Aston Villa won at Tottenham: the `away` side, claimed 0.483
against a de-vigged market 0.266, paid 3.7037. Ledger **28 -> 29 settled, 7 ->
8 wins, 25.00% -> 27.59%, ROI -18.18% -> -8.23%**. A ten-point ROI move on a
single 3.70 winner is arithmetic, not progress, and run 19 said the same thing
about its own 5.7-point move on two rows. The variance of this statistic at
n=29 is the reason the project does not read it.

**The finding this run spent itself on is that Elo enters a newly-promoted
team at 1500 and the bet rule then buys the difference.** In a league with
promotion that is not a neutral prior -- a side that has just come up is on
average well below the division it is entering -- so the model's first weeks
of pricing a promoted team run off a rating the book has no evidence for.
Measured over the 8 teams making their first appearance in the EPL table
(2020-21 through 2025-26), the model's probability for the debutant side runs
**+0.0447 above the de-vigged market** against a realized **0.2434**. The
market's 0.2451 is almost exactly right, so the gap is the model's, and
**all 8 teams are biased the same way**.

**It is live right now.** Coventry and Hull are 2026-27 debutants with **four
games** of history each. Hull currently sits **14th in the Elo book at 1534**,
above Fulham, Crystal Palace and Tottenham. Three of the eight open EPL rows
are on a debutant fixture, including the largest claimed edge on the entire
EPL board: `Hull @ Newcastle` away at **+57.7%**.

**The correction was swept out-of-sample and REJECTED.** Seeding a promoted
side below the book fixes the bias and buys nothing: pooled over six seasons
the per-game log-loss change is **-0.000987 with a season-cluster CI of
[-0.00255, +0.00058]**, and ROI moves the **wrong** way, **-8.296% ->
-8.918%**. What survived is a counter, so the next promoted side is visible in
a run summary instead of being rediscovered in a year. Tests **323 -> 332**.

## Finding 1: Elo's 1500 start systematically overrates promoted sides

### The measurement

Walk the committed EPL table forward, score every season after the first
(calibrator fit on strictly prior seasons), and split each team-side by whether
the book had ever seen that team before.

| stratum | n | mean `p_model` | mean `p_market` | bias | realized |
|---|---|---|---|---|---|
| **debutant (never seen)** | 304 | 0.2898 | 0.2451 | **+0.0447** | **0.2434** |
| returning (stale rating) | 380 | 0.1918 | 0.2145 | -0.0227 | 0.1789 |
| established | 3876 | 0.4156 | 0.4078 | +0.0078 | 0.4131 |

The market is within **0.002** of realized on the debutant slice. The model is
**0.046** away. This is not a case of both sides being uncertain about a hard
subgroup -- the market prices it correctly and the model does not.

Cluster-bootstrapped over the 8 teams: **95% CI [+0.0253, +0.0634]**.

### It is the 1500 start, not a coincidence about which teams got promoted

The bias decays monotonically as the book accumulates evidence, which is the
signature of a rating initialised away from the truth and walking toward it:

| games into the debut season | n | bias | mean Elo |
|---|---|---|---|
| 0-4 | 40 | **+0.1016** | 1491 |
| 5-9 | 40 | +0.0738 | 1477 |
| 10-18 | 72 | +0.0413 | 1464 |
| 19-37 | 152 | +0.0237 | 1453 |

Every debutant finishes its first season below where it started, most of them
far below (Ipswich 1500 -> 1377, Fulham 1500 -> 1407, Luton 1500 -> 1396).

**A second-order effect makes 1500 the wrong number in a way that is easy to
miss.** `backtest_soccer` never calls `regress_to_mean`, and relegated teams
carry their low ratings out of the division, so the *surviving* EPL book drifts
upward: the current 20-team mean is about **1572**, not 1500. A debutant
entering at `default_rating` therefore enters ~72 points below today's league
mean -- which is why the measured bias is +0.045 rather than the +0.10 a naive
reading of "starts at the average" would predict. The prior is wrong and
partially self-correcting, which is the worst way for it to be wrong, because
it looks defensible.

### The bet rule amplifies it

| stratum | sides | flagged | flag rate | mean claimed edge | ROI |
|---|---|---|---|---|---|
| **debutant** | 304 | 190 | **62.5%** | **+35.8%** | -11.77% |
| established | 3876 | 1410 | 36.4% | +19.2% | -7.12% |

The model bets debutant sides at nearly twice the rate and claims nearly twice
the edge when it does. **The ROI gap is not the solid part of this** -- per
team it ranges from -81.67% (Fulham) to +44.09% (Sunderland) across 8 clusters,
which is noise. The bias and the flag rate are the solid part.

### Live, this morning

| bet | fixture | side | claimed | market | edge | debutant history |
|---|---|---|---|---|---|---|
| `9d078844` | Hull @ Newcastle | away | 0.252 | 0.156 | **+57.7%** | Hull, 4 games |
| `8b2b48e5` | Hull @ Newcastle | draw | 0.247 | 0.206 | +17.8% | Hull, 4 games |
| `3a2be772` | Coventry @ Nott'm Forest | away | 0.206 | 0.164 | +21.3% | Coventry, 4 games |

The single largest claimed edge on the EPL board belongs to the team the model
knows least about. That is the pathology stated as a live position rather than
as a backtest table.

## Finding 2: the correction works, changes nothing, and is rejected

### The first sweep was a no-op, and that was the informative part

The obvious experiment -- lower `default_rating` -- returned an **identical row
for every value from 1500 down to 1300**. Elo differences are
translation-invariant, and every team in the first season of the table is
unseen, so moving the default moves the whole scale and nothing else. The
parameter that matters is not the default; it is the gap between the default
and a book that has already moved.

So: a team entering an **already-populated** book starts at `1500 - penalty`.

### The sweep

Selection seasons 2020-21..2023-24 (6 debutant teams); holdout 2024-25..2025-26
(Ipswich, Sunderland), untouched until one value was picked.

| penalty | log-loss | ll (debutant games) | ROI | deb bias | deb flag rate |
|---|---|---|---|---|---|
| **0 (current)** | 0.610519 | 0.6228 | -12.38% | **+0.0394** | 56.1% |
| 50 | 0.609362 | 0.6153 | -12.36% | +0.0082 | 47.8% |
| **100 (selected)** | **0.609067** | 0.6142 | -12.40% | -0.0203 | 31.1% |
| 150 | 0.609680 | 0.6189 | -12.11% | -0.0456 | 19.7% |
| 200 | 0.611228 | 0.6288 | -12.18% | -0.0676 | 14.0% |

A smooth, single-minimum curve at **penalty = 100**, selected on
selection-season log-loss with the holdout untouched.

### The holdout, and the verdict

| | penalty 0 | penalty 100 |
|---|---|---|
| log-loss | 0.621114 | **0.621058** |
| log-loss, debutant games | **0.6305** | 0.6318 |
| ROI | **+1.32%** | -0.27% |
| debutant bias | +0.0606 | **+0.0154** |
| debutant flag rate | 81.6% | **36.8%** |

**The bias correction generalises. Nothing else does.** Out-of-sample log-loss
improves by **0.000056**, debutant-game log-loss gets slightly *worse*, and ROI
moves the wrong way.

Pooled over all six scorable seasons, with season as the cluster:

| comparison | effect | 95% CI | P(better) |
|---|---|---|---|
| per-game log-loss, pen100 - pen0 | **-0.000987** | **[-0.00255, +0.00058]** | 0.887 |
| ROI, pen100 - pen0 | **-0.622pp** | [-3.552, +2.169] | 0.349 |
| ROI, skip-debutants - pen0 | +0.371pp | [-2.241, +2.932] | 0.614 |

Per season, pen100 beats pen0 on overall log-loss in **3 of 6** seasons (4 of 6
on debutant games only). It improves the debutant bias in **6 of 6**.

**Rejected.** The repo's rule is that a change must beat the de-vigged closing
line out-of-sample, and this one does not beat *doing nothing* on any headline
metric. The surgical version -- keep the ratings, just decline to bet debutant
sides -- was measured too, and is also nothing: **+0.371pp of ROI, CI straddling
zero**, which is the same verdict run 18 reached about the edge cap.

### What the rejection actually teaches

This is the seventh mechanism tried against the model's deficit and the
seventh that does not close it, but it fails in a new and more specific way
than the others. Runs 11, 12 and 17 tested things that turned out not to be
*real* effects. **This one is real** -- +0.0447, 8 of 8 teams, a monotone decay
with a mechanical explanation, and a live instance on the board this morning --
**and correcting it still buys nothing.** That is evidence the deficit is not
concentrated in an identifiable subgroup waiting to be patched. The model is
not losing because of promoted teams; it is losing everywhere, and promoted
teams are simply where the losing is easiest to see.

## Finding 3: the counter that survived

`src/sportsedge/betting/history.py`. `recommend` now reports, per sport:

```
"thin_history": {"threshold_games": 20, "flagged": 1,
                 "flagged_pct": 25.0, "teams": {"Coventry": 4}}
```

A fixture counts as thin when **either** side is below the threshold, because
`elo_diff` is a difference and a thin rating contaminates the price whichever
way the bet was struck. Twenty games is half a season and is a **reporting
line, not a tuned parameter** -- the decay table is smooth, so any cut is
arbitrary. **It gates nothing**, and a test asserts the rec list comes back
unmodified so that a future run cannot quietly turn it into the filter this run
rejected. NFL reports 0 and always will; there is no promotion.

(Hull does not appear above only because its 14:00Z fixture had already kicked
off and the in-play gate had removed it from the board by the time `recommend`
ran.)

## Bets

**1 settled, 1 CLV filled, 0 backfilled, 1 new row logged, 35 pending.**

| bet | side | claimed | market | paid | closed | CLV | ticks | lag | result |
|---|---|---|---|---|---|---|---|---|---|
| `582906f3` | Aston Villa (away) | 0.483 | 0.266 | 3.7037 | 4.1667 | **-11.11%** | **-3** | T-125.3h | **won** |

Priced against a reference at **T-0.47h** -- a real close, from the `*/30`
cron, on a fixture that kicked off at 11:30Z while no session was running.

**1 new row logged**, NFL, 09-27: `SEA @ WAS` away (claimed 0.600 vs market
0.545, **+9.05%**, +5.72% after fee) -- a contract that had not opened when
run 19 priced the board. NFL flagged **24 of 58** fillable (41.4%), 23 of them
duplicates of open rows, `illiquid_skipped` 4, `in_play_skipped` 0. EPL flagged
**4 of 14** (28.6%), all 4 duplicates, `illiquid_skipped` 5, `in_play_skipped`
5 -- the 5 in-play skips are the 14:00Z fixtures, which is why Hull is absent
from `thin_history` below despite being the sharpest live instance of
Finding 1. `superseded_voided` 0.

None of the three debutant rows in Finding 1 was logged this run; all three
were already open, and **nothing was voided, re-priced or withheld on account
of that finding** -- the counter added this run gates nothing, and the bias it
measures was rejected as a correction.

| | run 19 | run 20 |
|---|---|---|
| settled | 28 | **29** |
| wins | 7 | **8** |
| pending | 35 | 35 |
| void | 67 | 67 |
| win rate | 25.00% | **27.59%** |
| ROI | -18.18% | **-8.23%** |
| mean CLV (real close) | -0.281% (n=19) | **-0.823% (n=20)** |
| mean CLV (stale) | +4.04% (n=9) | +4.04% (n=9) |

`clv_resolution`, with the tick beside it as CLAUDE.md requires: one tick is
**3.4023%** of `clv_pct` at this ledger's prices; median reading **0.000%**;
mean **1.3103** ticks absolute; **41.4%** of settled rows never moved a tick.
The -0.823% mean is **-0.242 of a tick**. **Every settled CLV in the ledger is
still an exact integer in ticks** (max deviation 8.4e-15, total -5 ticks over
the 20 real-close rows), which is the check that run 19's conversion is right.

`clv_precision_real_close`: n **20**, mean **-0.250 ticks**, median 0.000, sd
**2.403**, SE **0.537**, 95% CI **[-1.303, +0.803]**, `n_for_target_se`
**92**.

**Run 19's falsifiable prediction was not testable this run and remains open.**
It predicted that the 11 open pre-registered wagers -- placed at T-48h to
T-56h -- would *lower* the CLV SD when they settle. They kick off **09-20 and
09-21** and none has settled. The one row that did settle was struck at
**T-125.3h**, the long-lag end, and moved **3 ticks**; the SD rose 2.378 ->
2.403 and the required n went 90 -> 92. Run 19's `corr(lag, |ticks|)` is
**0.628 at n=20**, against 0.629 at n=19 -- the new row landed almost exactly
on the relationship rather than testing it, and the cluster bootstrap over the
18 games **tightened to [0.207, 0.818]** from run 19's [0.024, 0.831]. Run 19
called the relationship "suggestive, not established" because its lower bound
cleared zero by a hair; one row moved that bound to 0.21. It is still 18
clusters and 9 distinct lag values, so **established is still too strong** --
but it is no longer hanging on a hair.

| lag bucket | n | mean signed ticks | sd | mean abs ticks |
|---|---|---|---|---|
| T-45..52h | 10 | -0.700 | 1.567 | 0.900 |
| T-52..60h | 4 | +0.250 | 1.258 | 0.750 |
| T-60..130h | **6** | +0.167 | 3.971 | **3.167** |

All of that is consistent with the lag-variance mechanism and none of it is
the test run 19 registered, which needs the short-lag rows. Score that
prediction next run.

**The pre-registered cohort was not scored -- the seventh declined look.** It
reconstructs from `placed_at` exactly as run 19 left it: **36 wagers (25 NFL,
11 EPL), 25 settled, 6 wins, 11 open**, all NFL, carrying **4.87 claimed /
3.96 market-implied**, kicking off 09-20 and 09-21. This run's settlement was
placed 09-14 and is **not** in the cohort, so **P(X <= 6) is still 0.0509** and
nothing about the prediction moved. **Score on 09-21.** `scorecard`'s
`p_at_most_model` is still not that number.

## Regression checks

All four canonical numbers reproduce digit-for-digit, before and after this
run's changes:

| | run 20 | runs 5-19 | match |
|---|---|---|---|
| NFL log-loss | 0.6517617405253826 | 0.6517617405253826 | digit-for-digit |
| NFL ROI | -8.208908995992267% | -8.208908995992267% | digit-for-digit |
| NFL n_games / n_bets | 1942 / 1625 | 1942 / 1625 | exact |
| EPL 2425 holdout ROI | -5.11513157894739% | -5.11513157894739% | digit-for-digit |

Nothing in this run touches a model, a price, a selection or a settlement --
the only production change is an additive diagnostic key on `recommend`'s
output -- so these were expected to hold, and the check is that they did.

pandas resolved to **3.0.6** again, numpy 2.4.6, scikit-learn 1.9.1.

Tests **323 -> 332**. Nine: five for the counter's behaviour (both-sides rule,
absent team counts as zero, established fixtures do not flag, empty input, and
that it mutates nothing and returns counts rather than a filtered board), and
four that re-derive the measurement itself from the committed table -- the
market being right where the model is not, all 8 teams biased the same way,
and the decay from +0.10 to +0.02. The measurement tests exist so the finding
is reproducible from the repo rather than living only in this entry; if the
decay ever goes flat, the explanation in `history.py` is wrong and needs
rewriting rather than patching.

## Data sources

| Source | Status |
|---|---|
| nflverse | Live. 2,499 games, 2,244 played. |
| football-data.co.uk | Live but **still lagging**: 2,700 / 2,700 played, latest row **2026-09-14** -- unchanged since run 19, now 5 days behind. |
| Kalshi REST | Live. 62 NFL + 24 EPL contracts captured this session. |
| ESPN scoreboard | Live. NFL 17/17 scores and kickoffs agree, EPL 40/40 agree. 42 EPL fixtures played vs the primary's coverage through 09-14. |

`espn-audit` clean: **0 score and 0 kickoff disagreements on either sport**.
`verify-settlements` **34/34 NFL and 126/126 soccer**, 0 unmatched in coverage
-- soccer up from 123 last run, and the three newest rows are verifiable
**only** through the ESPN supplement. Run 19 called the supplement
load-bearing on the normal path; five days of primary lag is that claim
holding.

Capture cron healthy -- snapshots every ~30 min, latest 15:02Z before this
session started.

## Open questions / next steps

- **Score the pre-registered cohort on 09-21.** 36 wagers, 25 settled, 6 wins,
  11 open NFL carrying 4.87 claimed / 3.96 market-implied, P(X <= 6) = 0.0509.
  Seventh opportunity to look early, seventh refusal. **Do not quote
  `scorecard`'s `p_at_most_model` as the pre-registered result.**
- **Run 19's SD prediction is still open and is the next falsifiable thing.**
  The 11 pre-registered wagers were placed at T-48h to T-56h and settle
  09-20/21; they should *lower* the CLV SD. The cohort is at **20 real-close
  rows**, sd 2.403 ticks, `n_for_target_se` **92**. Quote the current run's
  number, never an old journal's.
- **The lag-variance relationship strengthened without being tested.**
  `corr(lag, |ticks|)` 0.628 at n=20, cluster bootstrap **[0.207, 0.818]** over
  18 games, up from [0.024, 0.831] over 17. Still 18 clusters and 9 distinct
  lag values -- **suggestive, not established**, but no longer hanging on a
  hair. The 11 short-lag rows settling 09-20/21 are the real test.
- **Do not re-raise the promotion prior.** Swept this run, selected at 100 on
  four seasons, rejected on a two-season holdout and on a six-season pooled
  cluster bootstrap: log-loss CI [-0.00255, +0.00058], ROI **worse**. The
  *bias* is real and documented in `betting/history.py`; the *fix* is not
  worth having. A thicker reason would be a promoted-team feature with
  information Elo lacks (division-below form), which is a data-source question,
  not a parameter question.
- **Read CLV in ticks, and quote `n_for_target_se` beside the mean.** One tick
  is 3.4023% at this ledger's prices. The mean is -0.250 ticks, CI ±1.05 ticks.
- **Placement lag is not a variance knob** (run 19). Unchanged.
- **Do not re-raise:** `*/30` capture cadence (runs 9, 13, 19), the Odds API
  (run 2), football-data.org (run 3), recalibration (run 11), context features
  (run 12), `season_regression` (run 17), an upper edge cap (run 18), weather
  (runs 12, 18).
- **Seven reasons deep on why the model loses.** AUC deficit -0.046 CI [-0.064,
  -0.030] (run 11); context features rank worse (run 12); the pre-kickoff
  window is quiet (run 13); season regression does not move the gap (run 17);
  the selection pathology is mostly an identity (run 18); **and now: a real,
  mechanical, live subgroup bias whose correction changes nothing (run 20)**.
  The seventh is the most informative of them, because it rules out the hope
  that the deficit lives in a patchable subgroup. **No bet-rule change remains
  with a reason to expect a different outcome.** The honest next step is still
  the 09-21 cohort.
- **`PRICING_VERSION` is free to move after 09-21**, unchanged since run 10.
- NFL preseason markets are priced and settled by Kalshi but invisible to
  nflverse; labelled, not fixable.
- **Standing reminder:** 0 live bets. **29 settled shadow bets, 8 wins, ROI
  -8.23%.** The ROI improved ten points this run **on one wager**. That is not
  evidence of anything. The market still beats the model on every scoring rule
  on the bets the model itself chose, and it is **29 wagers**, which keeps all
  of it provisional.

## Process note

The stored scheduled prompt still carries "do not post, send, change, or
delete anything" and the unfilled `[which data sources?]` placeholder.
CLAUDE.md has overridden the first for repository work since 2026-09-11 and
settled the second since 2026-09-13. Noted once, per CLAUDE.md, and not
escalated.

One environment artifact worth a line so it is not re-diagnosed: the session
container clones **shallow**, which made the default branch and this session's
branch appear to have **no common ancestor** (two distinct roots, 50 and 51
commits). `git fetch --unshallow` resolved it to what it actually was -- the
default branch one snapshot ahead. A future run seeing "unrelated histories"
should unshallow before concluding anything.

**Escalations: none.** No charge and no signup form is outstanding.
