# Scheduled run 7 -- the first results arrived, and half the bet count was an artifact

_2026-09-13, 06:02-06:40 UTC_

## Headline

**The project's first cohort of real results settled: 7 EPL wagers, 1 win.**
The model expected 2.54 wins, the closing line expected 2.01, reality gave 1.
The direction agrees with run 4's selection audit. The sample does not support
a conclusion: P(X <= 1) under the model's own probabilities is **0.19**.

**And the ledger had been counting every one of those wagers twice.** 75
non-void rows were **40 distinct wagers**. The 14 EPL rows that settled this
morning were 7 bets written down twice each, and both copies always shared an
outcome. Every count this project has published over that ledger -- "74
pending", "70 pre-registered bets", the n in every confidence interval -- was
inflated, and the intervals were narrow by a factor of ~sqrt(2) for no reason.

## Finding 1: re-pricing only ever did the insert half

`ledger.existing_keys` dedupes on `(market_ticker, model_version,
pricing_version)`. `pricing_version` is in that key deliberately, and the
docstring explains why: a change to the pricing pipeline that leaves the model
string alone must still be able to re-price open rows. That is correct, and it
worked -- there are **zero** duplicate rows at an identical version.

What it does not do is retire the row it replaced. Re-pricing is a
*replacement*; the code only ever performed the insert. So the 2026-09-11
p1 -> p2 bump did not re-price 35 wagers, it **duplicated** them, and both
halves stayed open and were counted.

The module comment had the rule written down the whole time -- *"Bump this
whenever pricing behaviour changes, **and re-price open bets**"* -- and the
second clause was never implemented. The NFL side looked handled only by
coincidence: NFL's model version happened to move v1 -> v2 at the same time,
and *that* path did void its predecessors (28 rows). EPL's model never moved,
so nothing voided anything.

| | rows | distinct wagers |
|---|---|---|
| NFL, non-void | 54 | 29 |
| EPL, non-void | 21 | 11 |
| **total** | **75** | **40** |

35 pairs, 5 singletons, and every pair verified to agree on outcome. One pair
disagreed on `model_prob` (NYG @ LA, 0.2591 vs 0.2726) because the Elo ratings
absorbed new games between the two runs -- expected, not a defect.

**Fixed** by `ledger.void_superseded_rows`, run unconditionally at the end of
every `recommend` -- after logging, not before -- so a bump can never again
leave both halves open. The version order is a **declared tuple**
(`recommend.PRICING_VERSIONS`), not a sort of the strings: at p10 a
lexicographic sort puts the newest pipeline second-oldest, and voiding the
wrong half is worse than not voiding. A group containing an unrecognised
version is left untouched and reported under `unorderable` rather than guessed
at. `tests/test_superseded_void.py`, 11 tests.

Eighth bug of the same shape: a value that was not what the surrounding code
assumed. Here the assumption was that inserting a re-priced row *was* the
re-pricing.

### The repair moved the headline ROI the flattering way. It is still meaningless.

| | before | after |
|---|---|---|
| non-void bets | 75 | **40** |
| settled | 15 | **8** |
| pending | 60 | **32** |
| win rate | 20.0% | **25.0%** |
| **ROI** | **-13.06%** | **+0.51%** |

A correction that turns a loss into a profit is exactly the kind this project
should distrust, so: **nothing improved.** No bet changed outcome and no price
moved. The entire swing is one re-weighting. The project's single NFL win
(SF @ LA at 2.778) contributed +11.85pp to ROI in a book of 15; in a book of 8
the same win contributes **+22.22pp**. Split by sport the picture is unchanged
and unflattering:

| | n | wins | ROI |
|---|---|---|---|
| EPL | 7 | 1 | **-24.81%** |
| NFL | 1 | 1 | +177.78% |

`+0.51%` is one lucky longshot divided by eight. It is not a result, and the
25% win rate carries a Clopper-Pearson 95% CI of **[3.2%, 65.1%]**.

Which half survives was not a free choice: `pricing_version` asserts the later
pipeline is correct and the earlier superseded, so the newest wins and the
older is voided -- the same mechanism and the same direction as the 28 NFL rows
voided by the model bump. Settled duplicates were voided too, deliberately: a
settled duplicate is precisely where the double-count reaches win rate and ROI,
and sparing it to avoid touching a result would leave the defect in the only
numbers anyone reads.

**Audited cell by cell.** Across 107 rows the only columns that moved are
`status` (42), `result_logged_at` (42) and `notes` (35). No price, probability,
selection, stake, edge, `pricing_version`, kickoff, closing price or CLV
changed, and every overwritten note was the boilerplate
`"model not cleared by backtest; shadow only"`.

## Finding 2: the first results, and what they do and do not say

Seven EPL wagers settled. `cli scorecard`:

| | model | market | actual |
|---|---|---|---|
| expected wins (of 7) | **2.54** | **2.01** | **1** |
| mean probability | 0.363 | 0.287 | 0.143 realized |
| log-loss | **0.6725** | **0.5719** | |
| Brier | 0.2423 | 0.1926 | |
| P(X <= 1) | **0.19** | 0.34 | |

Read honestly, in both directions:

- **The sign is what run 4 predicted.** The model overstates the sides it bets
  (+22.0pp against realized) by more than the market does (+14.4pp), and it
  loses to the closing line on log-loss by 0.101 on the exact bets it chose.
  That is the winner's curse the selection audit described.
- **It is not evidence.** n = 7. P(X <= 1) = 0.19 under the model's own
  probabilities is unremarkable; a correct model betting these longshots
  returns 1 win or fewer about one time in five. The market's own number is
  0.34. Nothing here separates the two hypotheses.
- **A low win rate proves nothing by itself.** The rule bets longshots, so a
  14% win rate is what a *correct* model looks like here. The comparison that
  matters is against the market's probabilities on the same bets, which is why
  `scorecard` refuses to report one without the other.

New module `betting/scorecard.py` + `cli scorecard`, 8 tests. It uses an exact
**Poisson-binomial** for the win-count null (the cohort spans 0.14 to 0.63, so
a binomial on the mean is the wrong distribution), reports `effective_n` on
distinct `(contract, selection)` wagers rather than row count, and warns when
the two differ -- so finding 1 cannot silently recur inside a statistic.

## Finding 3: `closing_odds_decimal` has never held a closing price

Not a code defect, and not counted in the bug tally -- a limit of the
collection cadence, recorded because it undercuts the project's stated
best short-run signal.

CLV is computed against the last snapshot before kickoff. The scheduled run
fires once daily at ~06:00Z. Both leagues kick off between 14:00Z and 17:00Z.
So the "closing" price is always a mid-morning price:

| cohort | latest pre-kickoff capture |
|---|---|
| EPL, 2026-09-12 14:00Z slate (the 7 settled here) | **T-7.8h** |
| NFL, 2026-09-13 17:00Z slate (settles tonight) | **T-10.8h** |
| SF @ LA (run 6 already called its 0.0% CLV vacuous) | T-7.5h |

Measured drift across the days before kickoff is genuinely small -- NFL ask
moves a mean of **0.0013** over the last full day, median exactly 0.0000; EPL
**0.0080** over the 19h ending at T-7.8h. **But that bounds nothing about the
window that matters.** This project holds **zero** captures inside the final
8 hours before any settled game, which is exactly where inactives, team news
and late money move a line. The small number is a measurement of the quiet
period, not evidence that the closing hours are quiet.

Two of the three EPL captures inside a game-day window last run turned out to
be in-play, which is the same clock problem from the other side.

The remedy is cadence, and cadence is owner-controlled: the stored schedule
lives at account level and cannot be changed from inside a session.

## Bets

`recommend` produced **31** picks (27 NFL, 4 EPL) and logged **0** -- all were
duplicates of open p2 rows. The dedupe key did its job; `superseded_voided`
reported 0 groups, confirming the ledger is now clean. `in_play_skipped: 0` on
both sports, correctly: at 06:02Z nothing had kicked off.

Today's board: NFL flagged **27 of 59 fillable (45.8%)**, EPL **4 of 23
(17.4%)**, with 17 EPL contracts rejected as illiquid. A model finding a 3%
edge on 46% of a regulated exchange's board is still describing itself.

### Run 4's pre-registered prediction, restated

The prediction was written over "70 bets". Those 70 rows are **36 distinct
wagers**. Run 6 verified that population by counting 25+24 NFL and 10+11 EPL
across two days and matching 70 -- a verification that confirmed the number by
reproducing the artifact, because the second day largely re-logged the first.

Claimed and corrected counts scale with the population, so the *test* survives;
the stated n did not, and every CI around it was too narrow.

| | wagers | claimed | selection-corrected | market-implied |
|---|---|---|---|---|
| NFL | 25 | 11.23 | **7.79** | 9.21 |
| EPL | 11 | 3.96 | 3.49 | 3.28 |
| **total** | **36** | **15.19** | **11.28** | **12.48** |

The restatement sharpens the NFL leg: corrected (7.79) now sits clearly *below*
market-implied (9.21), so the three hypotheses separate rather than overlap.

**Resolved so far: 8 wagers, 2 wins** (claimed 2.94, market-implied 2.36).
28 remain open -- 11 NFL kicking off today, the rest through 2026-09-21.

## Odds capture

Three NFL and four EPL capture timestamps for 2026-09-13, 60 and 39 contracts
per pass, the latest at 06:12Z. **These are the last pre-kickoff prices for NFL week 1**, which
settles tonight. EPL's board dropped 60 -> 39 contracts as yesterday's fixtures
finalized.

| Source | Status |
|---|---|
| nflverse | Live. 2,499 games, 2,229 played. 27 line moves, all on unplayed 2026 games. |
| football-data.co.uk | Live. 2,690 games, **unchanged** -- E0 2026-27 still 30 played, latest 2026-09-06. |
| Kalshi REST | Live. 60 NFL + 39 EPL contracts per pass. |

The NFL table's diff is 27 line moves and nothing else, which is run 6's sort
fix holding.

**Escalations: none.** The Odds API stays rejected on run 2's reasoning;
football-data.org's key stays unnecessary per run 3.

## What did not happen, and why

- **No CLV was recovered.** `backfill_clv` ran unconditionally and found 7
  candidates, filling 0: football-data.co.uk has not published the 2026-09-12
  fixtures, so no kickoff can be resolved yet. Working as designed -- a missing
  number rather than a guessed one -- and the rows stay candidates.
- **The first backfilled CLV still has not been verified by hand.** It cannot
  be until the source publishes. Carried forward.
- **The EPL expiry lag still stands at an assumed 3h.** Measuring it needs the
  same publication. Carried forward.
- **The 7 EPL settlements rest on Kalshi alone.** `verify-settlements` agreed
  on 4/4 NFL and 90/90 soccer rows it *could* check, but the 2026-09-12
  fixtures are among its 21 unmatched games. The project's first result cohort
  has not yet had its cross-check. The next run must re-run it.
- **No model change was proposed, so nothing needed backtesting for adoption.**
  Both backtests were run as regression checks on a ledger-only change and
  reproduce exactly: NFL log-loss **0.6517617405253826**, ROI
  **-8.208908995992267%**, digit-for-digit with runs 5 and 6; EPL 2425 holdout
  -5.115%, matching run 4's set.
- **The edge threshold did not move onto the fee-inclusive number.** Run 5
  deferred that until the week-1 slate settles. It settles tonight, not this
  morning.

`live_enabled` stays **false** everywhere -- decided, not deferred. The one
cohort of real evidence produced this run has the model losing to the closing
line on the bets it chose.

## State

| | |
|---|---|
| Live bets | **0.** Headline win rate and ROI: undefined, correctly |
| Shadow bets | **8 settled (2 wins), 32 pending, 67 void** |
| Distinct wagers vs ledger rows | 40 vs 40 -- **equal for the first time** |
| Usable CLV readings | **0** (the one reading is a mechanical 0.0% at T-7.5h) |
| Models deployed | None |
| Tests | **176** pass, network-free (157 -> 176) |
| Configs beating the market, cumulative | **0 of 150** |
| Venues at which the model beats the market | **0 of 2** |
| Bugs of the "value was not what the code assumed" shape | **8** |

## Process note

The stored scheduled prompt still contains "do not post, send, change, or
delete anything", and CLAUDE.md has overridden it for repository work since
2026-09-11, so this run captured odds, settled, voided and committed. Flagging
it as that note requires: the stored prompt lives at account level and cannot
be edited from inside a session. It also still contains the unfilled
`[which data sources?]` placeholder, answered by the table in CLAUDE.md.

## Open questions / next steps

- **NFL week 1 settles tonight.** 11 of the 36 pre-registered wagers kick off
  today. Next run's first job is to settle them and report against 7.79
  corrected / 9.21 market-implied / 11.23 claimed, whichever way it falls.
- **Re-run `verify-settlements` on the 7 EPL results** once football-data.co.uk
  publishes. They are currently single-sourced.
- **Then: verify the first backfilled CLV by hand, and measure the EPL expiry
  lag.** Both unblock on the same publication.
- **Snapshot cadence is the binding constraint on CLV** (finding 3), and it is
  owner-controlled. Until it changes, `closing_odds_decimal` holds a T-8h price
  and every CLV number this project reports should be read with that attached.
- **Then move the edge threshold onto the fee-inclusive number** as a `p3` bump
  with explicit re-pricing -- which, now that `void_superseded_rows` exists,
  will actually replace rows instead of duplicating them.
- **`edge_threshold_pct: 3.0` has never been derived from anything** (run 5).
- **The selection gap remains the thing to attack** (run 4). Run 7's one cohort
  is consistent with it and far too small to confirm it.
- Kalshi's fee coefficient is still unread.
- The 5% relative-width liquidity gate remains unvalidated against realized
  fill quality.
- **Standing reminder:** 0 live bets. 8 settled shadow bets, 2 wins. The
  headline ROI is `+0.51%` and it means nothing -- it is one longshot in a book
  of eight, and this run exists partly because a number that looked solid
  turned out to be half artifact.
