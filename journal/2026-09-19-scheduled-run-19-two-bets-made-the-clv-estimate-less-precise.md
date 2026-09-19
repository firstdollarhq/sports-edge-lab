# Scheduled run 19 -- two bets made the CLV estimate less precise, and the tick it is read against was wrong

_2026-09-19, 06:01-06:5xZ. Run 18 ran 15:02-15:4xZ yesterday afternoon._

## Headline

**Two wagers settled, the headline improved, and almost nothing about that is
information.** Brentford 3-0 Chelsea resolved the two open rows on that
fixture: the `home` side **won** at a claimed 0.418 against a de-vigged market
0.318, the `draw` side lost. Ledger **26 -> 28 settled, 6 -> 7 wins, 23.08% ->
25.00%, ROI -23.91% -> -18.18%**. A 5.7-point ROI move on two rows is the
noise this project exists to not be fooled by, and it is reported here as
arithmetic rather than as progress.

**Run 16's ESPN supplement fired against a real gap for the first time, and it
worked.** Run 18 recorded it as "deferred, not validated -- the next outage
will still be its first real run". The gap was not an outage. football-data.co.uk
is up and healthy and simply **has not published 09-18 yet**: its latest row is
2026-09-14, ESPN had the score by 06:04Z, and the two settlements sitting on
that fixture are the newest rows in the ledger. `verify-settlements` on the
primary alone checks **120 and leaves 3 unmatched**; with the supplement it
checks **123 and agrees on 123**. Pinned in two tests.

**The finding this run spent itself on is that the tick CLAUDE.md requires
every CLV mean to be read against was computed with the wrong formula, and the
error ran in the dangerous direction.** The exact conversion is

    ticks = clv_pct / placed_decimal_odds

and under it **every settled CLV in the ledger is an exact integer** (max
deviation 8.4e-15) -- as it must be, because the venue quotes whole cents. The
old formula, `p / (p - tick) - 1`, is the cost of buying one cent lower, a
different quantity; it ran **1.9%-9.1% high per row, +4.3% on the mean**, which
biased `mean_abs_ticks` **down**: a genuine one-tick move read as 0.96-0.98
ticks. For a field whose entire job is to stop sub-tick means being read as
signal, understating the tick count is the wrong way to be wrong.

**And the precision projection that has been carried for two runs is
optimistic by a factor of three.** Run 18 left "the CLV cohort is at 17
real-close rows and needs ~13 more to resolve a quarter tick". Adding two rows
**raised the SD 39%** (5.04 -> 6.99 in `clv_pct`), because those two were the
first in the cohort placed more than four days before kickoff and they moved 6
and 2 ticks. **The estimate got less precise by acquiring data**, and the
required n went from ~30 to **~90**. Tests **317 -> 323**.

## Finding 1: the tick was computed with the wrong formula

### What was wrong

`_clv_resolution` priced one tick as `p / (p - KALSHI_TICK) - 1` -- how much
the decimal odds improve if you buy the contract one cent cheaper. That is a
real quantity, and it is not the one CLV is measured in. CLV moves with the
**closing** price, not the price paid:

    clv_pct = (placed_dec / close_dec - 1) * 100
    ticks   = (1/close_dec - 1/placed_dec) / 0.01

    => clv_pct / placed_dec == (placed_dec - close_dec) * 100 / (close_dec * placed_dec) == ticks

So one tick is worth `placed_dec` percent at that row's price -- **exactly**,
linear in the closing price, and identical in both directions. No
approximation and no singularity.

### The evidence that the new one is right rather than merely tidier

The venue quotes whole cents, so a correct conversion must return integers on
real data. It does:

| conversion | one tick, mean | `mean_abs_ticks` (n=28) | CLVs integral? |
|---|---|---|---|
| old, `p/(p-tick)-1` | 3.5375 | 1.2083 | no |
| **exact, `placed_dec`** | **3.3915** | **1.2500** | **yes, max dev 8.4e-15** |

1.25 is 35 ticks over 28 rows. Under a correct conversion `mean_abs_ticks`
*must* be a rational with denominator n, and the old one destroyed that.

The per-row bias is 1.9% to 9.1% high and rises as contracts get cheaper,
so it was worst exactly where CLV is largest.

### A guard that turns out to have been an artifact

The old formula divided by zero at a 1c contract, so those rows were dropped
and `test_clv_resolution_survives_a_contract_priced_under_one_tick` pinned the
exclusion. The exact conversion has no singularity: one tick at a 1c contract
takes it to 2c, halving the decimal odds, worth **100% CLV**. That is a real
number and the row belongs in the mean. The test now asserts it is **kept**.

**Nothing about the model moves.** This changes how a number is *reported*,
not any price, selection or settlement. The headline real-close mean is
**-0.281%** either way.

## Finding 2: the cohort got less precise by getting bigger

### What happened

| cohort | n | mean `clv_pct` | sd | SE |
|---|---|---|---|---|
| through run 18 | 17 | -1.888 | 5.037 | 1.222 |
| **this run** | **19** | **-0.281** | **6.995** | **1.605** |

The n=17 SE reproduces run 17's reported 1.222% digit-for-digit, so the
cohort and the arithmetic are the same; only the data moved. Run 18's
projection was built on that SD, and `(5.04 / 0.881)^2 ~ 33` is where "~30
rows" came from.

In exact ticks, where the numbers belong:

| | value |
|---|---|
| mean | **-0.105 ticks** |
| median | **0.000 ticks** |
| sd | 2.378 ticks |
| SE | 0.546 ticks |
| 95% CI | **[-1.175, +0.964] ticks** |
| n for SE = 0.25 ticks | **90** (have 19) |

**The reading is unchanged and the uncertainty is not.** CLV still says *no
detectable edge*; the interval around it is ±1 tick, which is wider in tick
terms than run 18's framing implied.

### Why the SD moved, and why it will keep moving

The two new rows were placed at **T-123.6h**. Every previous row in the cohort
was placed at T-48h to T-90h, and most at T-49.7h. CLV magnitude scales with
how long the bet sat:

| placement lag | n | mean signed ticks | sd | mean abs ticks |
|---|---|---|---|---|
| T-48..50h | 10 | -0.700 | 1.567 | 0.900 |
| T-53..57h | 4 | +0.250 | 1.258 | 0.750 |
| T-75..124h | 5 | +0.800 | 4.087 | **3.200** |

`corr(placement lag, |CLV| ticks) = 0.629`, cluster-bootstrapped over the 17
games to **[0.024, 0.831]** and stable under leave-one-game-out (**0.528 to
0.722**, weakest when the Brentford fixture itself is dropped). The lower
bound clears zero by a hair on 17 clusters with 8 distinct lag values, so this
is **suggestive, not established** -- but it is enough to disqualify a
projection that assumes a fixed SD.

The required n depends entirely on a mix this project does not control:

| if the cohort looked like | sd (ticks) | n for SE = 0.25 |
|---|---|---|
| short-lag rows only | 1.641 | 43 |
| the current mix | 2.378 | **90** |
| long-lag rows only | 2.838 | 129 |

The recommender logs a side the first time it sees an edge, so placement lag
is set by **when a contract opens**, not by any decision -- which is why this
is a running estimate and is now reported as one (`n_for_target_se`) rather
than written into a journal and inherited.

### The trap, recorded before someone falls into it

Placement lag looks like a variance knob: bet later, get a tighter CLV
estimate. **It is not one.** CLV measures how far the line came to you after
you struck it, so a bet placed at T-1h has almost no variance *and* almost
nothing to measure. The noise and the estimand shrink together. There is no
version of this experiment where the instrument is cheap.

**The signed column is the one that would matter if the model had an edge** --
longer holds should earn more CLV -- and it does trend up (-0.70, +0.25,
+0.80). At n=10/4/5 with an sd of 4.09 in the top cell, that is nothing. Named
here only so a future run does not present it as a discovery.

### What run 13 said, and why this does not contradict it

Run 13 measured **0.0107 mean absolute net move** for EPL over the whole
pre-kickoff window and rejected `*/15` capture on it. A 6-tick move looks like
a counter-example and is not: run 13's window began at a median first capture
of **T-74h**, and these bets were struck at **T-124h**, a window half again as
long. `*/30` is untouched and stays untouched -- this is about the *ledger's*
CLV variance, not about capture cadence, and nothing here is a reason to
re-raise a cadence question that runs 9 and 13 both closed.

## Finding 3: the ESPN supplement's first real gap

Run 16 built it, run 16 and 17 never fired it, run 18 recorded it as
untested. It fired this run, and the gap was not the one it was designed for.

| | primary only | primary + ESPN |
|---|---|---|
| soccer settlements checked | 120 | **123** |
| agreed | 120 | **123** |
| unmatched | **3** | **0** |

football-data.co.uk is **up** -- it simply publishes on a lag. Its latest row
is **2026-09-14**; ESPN carried Brentford 3-0 Chelsea (**2026-09-18**) by
06:04Z. The two wagers on that fixture settled from Kalshi this run and are
verifiable **only** through the supplement.

**This is the more common case than the outage the supplement was built for,**
and it recurs every week: any midweek or Friday fixture settles on Kalshi
before the primary's CSV catches up. The supplement is now load-bearing on
the normal path, not just the failure path.

One consequence had to be fixed rather than recorded.
`test_espn_results_reproduce_the_primary_ratings_exactly` asserted
`espn_supplement.rows == len(real_epl) - len(stale)` -- that ESPN supplies
*exactly* the primary's post-cutoff rows. That was only ever true while the
two sources were level. ESPN is now a fixture **ahead**, so an unrestricted
supplement builds its rating book from a game the primary has never seen and
the two cannot be equal by construction. The comparison is now scoped to where
both have published, which is what the test was always about, and the lead is
asserted separately as `>=` so a backfill makes it go quiet rather than red.

## Bets

**2 settled, 2 CLV filled, 0 backfilled, 35 pending.**

| bet | side | claimed | market | paid | closed | CLV | ticks | result |
|---|---|---|---|---|---|---|---|---|
| `6f98d9ee` | Brentford (home) | 0.418 | 0.318 | 3.125 | 2.632 | **+18.75%** | **+6** | **won** |
| `5d27e284` | draw | 0.260 | 0.242 | 4.000 | 3.704 | +8.00% | +2 | lost |

Both priced against a reference **T-0.39h** -- a real close, from the `*/30`
cron, on a fixture that kicked off while no session was running. That is the
capture Action doing exactly what run 13 built it for.

**2 new rows logged**, both NFL, both 09-27: `HOU @ IND` home (claimed 0.482
vs market 0.435, +9.50%) and `CAR @ CLE` home (0.570 vs 0.418, +32.48%).

NFL flagged **23 of 57** fillable (40.4%), 21 duplicates of open rows,
`illiquid_skipped` 5. EPL flagged **9 of 26** (34.6%), all 9 duplicates,
`illiquid_skipped` 1. `in_play_skipped` 0, `superseded_voided` 0.

| | run 18 | run 19 |
|---|---|---|
| settled | 26 | **28** |
| wins | 6 | **7** |
| pending | 35 | 35 |
| void | 67 | 67 |
| win rate | 23.08% | **25.00%** |
| ROI | -23.91% | **-18.18%** |
| mean CLV (real close) | -1.888% (n=17) | **-0.281% (n=19)** |
| mean CLV (stale) | +4.04% (n=9) | +4.04% (n=9) |

`clv_resolution`, as CLAUDE.md requires, now with the corrected tick: one tick
is **3.3915%** of `clv_pct` at this ledger's prices (not 3.5375%); median
reading **0.000%**; mean **1.2500** ticks absolute; **42.9%** of settled rows
never moved a tick. The -0.281% mean is **0.083 of a tick**.

**The pre-registered cohort was not scored, deliberately -- the fifth
declined look, and the reason is now stronger, not weaker.** The 36-wager
cohort reconstructs from `placed_at` exactly as run 18 left it: **25 settled,
11 open, all NFL, carrying 4.87 claimed / 3.96 market-implied**, kicking off
09-20 and 09-21. **Neither of this run's two settlements is in it** -- both
were placed 09-13 -- so P(X <= 6) is **still 0.0509** and nothing about the
prediction moved. Score on **09-21**. `scorecard`'s `p_at_most_model` is still
not that number.

## Regression checks

All four canonical numbers reproduce digit-for-digit, on a container that
re-resolved every dependency from scratch:

| | run 19 | runs 5-18 | match |
|---|---|---|---|
| NFL log-loss | 0.6517617405253826 | 0.6517617405253826 | digit-for-digit |
| NFL ROI | -8.208908995992267% | -8.208908995992267% | digit-for-digit |
| NFL n_games / n_bets | 1942 / 1625 | 1942 / 1625 | exact |
| EPL 2425 holdout ROI | -5.11513157894739% | -5.11513157894739% | digit-for-digit |

pandas resolved to **3.0.6** again, numpy 2.4.6, scikit-learn 1.9.1.

Tests **317 -> 323**. Four for the tick conversion and the precision block
(every committed CLV integral; the old formula's bias and its direction; the
interval and required n on a frame whose sd is known by hand; the real-close
restriction), one for the supplement against the real gap, one for the
supplement's lead over the primary. Two existing tests were rewritten rather
than patched: the 1c-contract guard (now asserts inclusion) and the ratings
equality (now scoped to where both sources have published).

## Data sources

| Source | Status |
|---|---|
| nflverse | Live. 2,499 games, 2,244 played. 26 rows revised -- week-2 line moves. |
| football-data.co.uk | Live but **lagging**: 2,700 / 2,700 played, latest row 2026-09-14. Has not published 09-18. |
| Kalshi REST | Live. 62 NFL + 27 EPL contracts. |
| ESPN scoreboard | Live. NFL 17/17 scores and kickoffs, EPL 40/40. `only_espn` 10, now including one **played** fixture -- Finding 3. |

`espn-audit` clean: 0 score and 0 kickoff disagreements on either sport.
`verify-settlements` 34/34 NFL and 123/123 soccer. Capture cron healthy --
snapshots every ~30 min through the night, latest 04:34Z; this session wrote
62 NFL and 27 EPL rows.

## Open questions / next steps

- **Score the pre-registered cohort on 09-21.** 36 wagers, 25 settled, 11 open
  NFL carrying 4.87 claimed / 3.96 market-implied, P(X <= 6) = 0.0509. Sixth
  opportunity to look early, sixth refusal. **Do not quote `scorecard`'s
  `p_at_most_model` as the pre-registered result.**
- **The CLV cohort needs ~90 real-close rows, not ~30, and that estimate is
  itself unstable.** At 19. The 11 open pre-registered wagers settle 09-20/21
  with full final-hour coverage and were placed at T-48h to T-56h, so they
  should *lower* the SD -- which is the prediction to check next run, and a
  falsifiable one.
- **Read CLV in ticks, and quote `n_for_target_se` beside the mean.** One tick
  is 3.3915% at this ledger's prices. The mean is -0.105 ticks with an
  interval of ±1.07 ticks.
- **Placement lag is not a variance knob.** Do not propose betting later to
  tighten the CLV estimate; it shrinks the estimand by the same mechanism.
- **The ESPN supplement is validated and load-bearing on the normal path.**
  Not just the outage path -- the primary lags by days on midweek fixtures.
- **Do not re-raise:** `*/30` capture cadence (runs 9, 13, and again here --
  this run's 6-tick move is a T-124h window, not a final-hour one), the Odds
  API (run 2), football-data.org (run 3), recalibration in any form (run 11),
  context features (run 12), `season_regression` (run 17), an upper edge cap
  (run 18), weather (runs 12 and 18).
- **Six reasons deep on why the model loses**, unchanged this run: AUC deficit
  -0.046 CI [-0.064, -0.030] (run 11); context features rank worse (run 12);
  the pre-kickoff window is quiet (run 13); season regression does not move the
  gap (run 17); the selection pathology is mostly an identity (run 18). **No
  bet-rule change remains with a reason to expect a different outcome.** The
  honest next step is still the 09-21 cohort.
- **`PRICING_VERSION` is free to move after 09-21**, unchanged since run 10.
- **17 stale `claude/elegant-archimedes-*` branches** on the remote. Harmless,
  noted so it is not rediscovered.
- NFL preseason markets are priced and settled by Kalshi but invisible to
  nflverse; labelled, not fixable.
- **Standing reminder:** 0 live bets. **28 settled shadow bets, 7 wins, ROI
  -18.18%.** The ROI improved 5.7 points this run **on two wagers**, one of
  which won. That is not evidence of anything. The market still beats the
  model on every scoring rule on the bets the model itself chose, and it is
  **28 wagers**, which keeps all of it provisional.

## Process note

The stored scheduled prompt still carries "do not post, send, change, or
delete anything" and the unfilled `[which data sources?]` placeholder.
CLAUDE.md has overridden the first for repository work since 2026-09-11 and
settled the second since 2026-09-13. Noted once, per CLAUDE.md, and not
escalated.

**Escalations: none.** No charge and no signup form is outstanding.
