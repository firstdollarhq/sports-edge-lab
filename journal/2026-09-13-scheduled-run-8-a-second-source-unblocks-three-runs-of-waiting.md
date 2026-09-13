# Scheduled run 8 -- three items were waiting on someone else's publication schedule

_2026-09-13, 15:01-15:40 UTC. Second run of the day; run 7 was 06:02-06:40Z._

## Headline

**The project's first result cohort now has an independent cross-check, and it
holds: all 7 EPL settlements confirmed by a second source.** `verify-settlements`
goes from *90 checked, 21 unmatched* to **114 checked, 114 agreed, 0 unmatched*
for soccer. No settlement was wrong.

**Three separate open items had been blocked on the same external event** --
football-data.co.uk publishing the 2026-09-12 fixtures -- across runs 6, 7 and
8. It still has not published them. The fix was not to wait a fourth time: it
was a second free, keyless source (ESPN's public scoreboard) for the two fields
that were actually missing, kickoff time and final score. All three items are
now closed.

**Nothing was adopted, no model changed, `live_enabled` stays `false`.** Both
backtests reproduce digit-for-digit, as they must for a change that touches
neither model.

## Finding 1: the blocker was never football-data.co.uk. It was waiting.

The three items, all from run 7's open list:

| Item | Blocked on |
|---|---|
| The 7 settled EPL wagers are single-sourced on Kalshi | fixtures published |
| `backfill_clv` fills 0 of 7 -- no kickoff, so no pre-kickoff cutoff | fixtures published |
| EPL expiry lag is an **assumed** 3h | fixtures published |

Each was written down as "re-run it once the source catches up". That framing
survived three runs because it is *true*: the source will catch up, and then
all three resolve. What it misses is that football-data.co.uk publishes in
batches on its own cadence, and the project had made its only cohort of real
evidence hostage to it.

football-data.co.uk is the right source for the thing it is uniquely good at --
historical closing odds, which is what the model trains against -- and the
wrong thing to block *settlement verification* on. Those need a score and a
kickoff, which many sources publish within minutes of full time.

**ESPN's public scoreboard** (`site.api.espn.com`, the undocumented endpoint
behind espn.com's own scoreboard): free, unauthenticated, no account, both
leagues, one call per date range. It carries no odds, never feeds the model,
and is consumed in exactly two places -- `verify-settlements` as a third
opinion, and `ingest.kickoff` as a *fallback* where the primary table has no
kickoff. Primary always wins where it has one.

CLAUDE.md's bar for a new source is "free, no human-created account, and
verified against something we already hold before any number derived from it is
published". That verification is `cli espn-audit`, kept as a command rather
than a scratch script so it re-runs every time:

| | scores compared | agree | kickoffs compared | agree | only in ESPN |
|---|---|---|---|---|---|
| EPL | 30 | **30** | 30 | **30** | 9 |
| NFL | 2 | **2** | 2 | **2** | 0 |

Kickoffs agree to within 60 seconds on all 30. The 9 "only in ESPN" are exactly
the gap: the 7 fixtures of 2026-09-12 plus today's 2.

## Finding 2: all 7 settlements confirmed, independently

Checked against ESPN's results rather than Kalshi's own resolution:

| bet | selection | ESPN result | ledger | agree |
|---|---|---|---|---|
| Arsenal @ Sunderland | home (SUN) | Sunderland 0-2 Arsenal | lost | yes |
| Everton @ Tottenham | away (EVE) | Tottenham 0-0 Everton | lost | yes |
| Fulham @ Liverpool | **draw** | Liverpool 0-0 Fulham | **won** | yes |
| Fulham @ Liverpool | away (FUL) | Liverpool 0-0 Fulham | lost | yes |
| Ipswich @ Crystal Palace | home (CRY) | Crystal Palace 2-3 Ipswich | lost | yes |
| Brentford @ Bournemouth | home (BOU) | Bournemouth 2-2 Brentford | lost | yes |
| Nott'm Forest @ Aston Villa | home (AVL) | Aston Villa 1-2 Forest | lost | yes |

Worth stating plainly because it is the boring outcome and this journal should
record those with the same weight as the interesting ones: **the settlement
path was already correct.** The cross-check found nothing. Its value is that
"we have not checked" is now "we checked, and it agreed", which is a different
statement about the project's only real evidence.

An honest gap remains: NFL still reports **94 unmatched** settled Kalshi
markets. That is pre-existing, predates this run, and ESPN cannot reach it
either -- the ESPN NFL table starts 2026-08-01. Not investigated. Recorded
rather than quietly left out of the "0 unmatched" headline, which is a soccer
number only.

## Finding 3: CLV exists for the first time -- and is not evidence of anything

`backfill_clv` filled **7 of 7** candidates. With the one NFL row and the
Coventry bet that settled overnight, **9 of 9 settled rows now carry a CLV**.

| | |
|---|---|
| mean CLV | **+4.04%** |
| positive | 5 |
| exactly 0.00 | 4 |
| **negative** | **0** |

Every non-zero reading is positive. That is the flattering direction, which in
this project is the standing reason to distrust a number, so:

- **Four of the nine compare an entry price to a "close" captured about twelve
  minutes later.** The 14:00Z games were priced at 06:02-06:14Z and the last
  pre-kickoff capture was 06:14Z. A CLV over twelve minutes is arithmetically
  fine and substantively empty.
- **The best reference in the whole set is T-1.2h, and it reads 0.00%.**
  Everton @ Tottenham: kickoff 16:30Z, last capture 15:19Z, ask 0.27 at entry
  and 0.27 at the reference. The single closest thing the project has to a real
  closing price says the line did not move.
- **The largest reading, +16.67%, is a two-cent tick.** Arsenal @ Sunderland:
  ask 0.12 at 06:0xZ to 0.14 at 15:19Z, kickoff 19:00Z. Verified by hand
  against the raw snapshot rows, not taken from the aggregate. On a 12c
  contract, one tick is 8%.
- **Positive CLV measured against a later ask is also exactly what picking off
  a thin quote that then reverts looks like.** That is not a competing theory
  to be dismissed; it is the *same* winner's curse run 4's selection audit
  described, seen from the price side instead of the outcome side. This number
  cannot distinguish the two.

So: the column is populated, the mechanism works end to end for the first time,
and the value is not yet interpretable.

## Finding 4: the EPL expiry lag is measured. The assumption was right.

Assumed 3h since run 5 because no EPL kickoff could be resolved. Measured now,
against ESPN kickoffs, over every contract on the 2026-09-13 board:

| sport | n | lag |
|---|---|---|
| **EPL** | 13 | **3.00h, all 13** |
| NFL | 30 | 3.00h x 27, 6.00h x 3 |

Exactly 3.00h, no spread at all. The constant standing in for a measurement was
correct, and the in-play gate that depends on it is sound. Recording a
confirmed assumption matters as much as recording a broken one -- the project
has spent four runs treating this as an open risk.

## Finding 5 (bugs 10-12): three of the shape, all caught inside this run

All three are in code written this run, caught before commit. Counted anyway;
the tally is about the shape, not about who was embarrassed.

**Bug 10 -- the line-movement measurement compared a bucket against itself.**
`cli line-movement` is the measurement run 7 said had to follow the cron. Its
first run reported **0.00 movement in every near-kickoff bucket**, which reads
as "the line is quiet in the final hour" -- the reassuring answer, and a
completely fake one. For a game that has *not kicked off*, the "last pre-kickoff
quote" is just the most recent capture, which is by construction the newest
bucket's own quote. The newest bucket was being compared to itself. Fixed by
excluding games that have not kicked off, and excluding the bucket containing
the reference quote. Both pinned by tests that assert the *old* behaviour is
gone.

The module now also reports `reference_lag_h` per bucket -- how far the closing
reference itself sat from kickoff -- because a bucket whose reference is 7.75h
out has measured nothing about the close, and without that number a reader
cannot tell.

**Bug 11 -- `--espn-end` defaulted to the start date.** ESPN's `dates` takes
either a single day or a range, so passing a start with no end is a *valid*
one-day request. `refresh-history` fetched 0 games, wrote an empty table, and
printed a success line. Caught because "0 rows" was visible in the output;
would not have been caught by anything else. Fixed, and `refresh-history` now
refuses to let an empty fetch overwrite a populated table.

**Bug 12 -- ESPN's NFL feed includes preseason, and preseason restarts week
numbering at 1.** 49 August games were entering the committed table, where
`week` would have meant two different things at once. This project has already
shipped one bug from `week` not meaning what the code assumed -- run 2, sorted
as a string, which invalidated every NFL ROI number then published. Filtered on
ESPN's own `season.type` (2 and 3 kept). Applied to NFL only: `eng.1`'s
`season.type` is a league id (14308), not the pre/regular/post scheme, so
filtering soccer on those numbers would have dropped everything.

Running tally: **12 bugs of one shape** -- a value that was not what the
surrounding code assumed.

## The final hour is still not measured

This is the item run 7 designated as the next run's headline, and it did not
land. Honest statement of why:

The cron works -- captures at 13:31, 14:02, 14:33 and 15:01Z today, roughly 30
minutes apart, exactly as designed. But **every game that has already kicked
off predates the cron**, so the closing reference for all of them is still a
pre-cron capture sitting a median **7.75h** from kickoff. Today's fixtures do
have captures inside the final hour; they just have not finished yet.

| cohort | status |
|---|---|
| 8 settled EPL events | reference T-7.75h median. No final-hour data. |
| Man City @ Man United, KO 15:30Z | captures at T-2.0h, T-1.5h, T-0.9h, **T-0.5h** -- kicks off minutes after this run ends |
| NFL week 1, 13 games, KO 17:00Z | captures at T-3.5h, T-3h, T-2.5h, T-2h and counting |

So the measurement is now mechanical and lands next run, over 13 NFL games
rather than the 1 EPL game available today. The decision on `*/15` waits for
it.

### Addendum, +6 minutes: the first genuine closing reference

Man City @ Man United kicked off at 15:30Z while this run was finishing, and
the cron's 15:23Z capture became **the first reference price this project has
ever held inside the final hour -- T-0.12h, about seven minutes before
kickoff.** The full final-two-hours path:

| capture | T- | MCI ask | draw ask | MUN ask |
|---|---|---|---|---|
| 13:31Z | 1.97h | 0.45 | 0.25 | 0.32 |
| 14:02Z | 1.46h | 0.45 | 0.25 | 0.32 |
| 14:33Z | 0.94h | 0.45 | **0.26** | 0.32 |
| 15:01Z | 0.47h | 0.45 | 0.26 | 0.32 |
| **15:23Z** | **0.12h** | **0.44** | 0.25 | 0.32 |

Net movement over the final two hours: one tick on Man City, a tick out and
back on the draw, nothing at all on Man United. `cli line-movement` reports the
T-1h..T-2h bucket at mean **0.0033**, median 0.000, max 0.010, against a
reference 7 minutes from kickoff.

**This is n = 1 game, 3 contracts, and it is the most liquid fixture on the
EPL board.** Liquidity and price stability go together, so a Manchester derby
is the best case for "nothing moves late", not a representative one. Taken with
the Everton @ Tottenham T-1.2h reading of exactly 0.00%, the project now holds
two weak data points, both saying quiet, and neither is a basis for changing
cadence. The NFL cohort tonight is the real test.

## Bets

`recommend` flagged 23 of 55 NFL contracts (41.8%) and 7 of 23 EPL (30.4%),
logging **4** new EPL wagers and skipping 26 as duplicates of open p2 rows.
`in_play_skipped: 0` on both, correctly -- Coventry @ Brighton had already
closed off the board and Man City had not yet kicked off.

A model finding an edge on 41.8% of a regulated exchange's board is still
mostly describing itself, which is why every row is `shadow`.

**Ledger: 44 non-void rows = 44 distinct wagers**, still equal, so
`void_superseded_rows` is holding.

| | run 7 | run 8 |
|---|---|---|
| settled | 8 | **9** |
| wins | 2 | 2 |
| pending | 32 | 35 |
| win rate | 25.0% | **22.2%** |
| ROI | +0.51% | **-10.66%** |
| rows with CLV | **0 usable** | **9 of 9** |

The ROI swing from +0.51% to -10.66% is one added loss (Coventry, at 4.167) in
a book of nine. It is the same non-result as before with a different sign, and
run 7's warning applies unchanged in the opposite direction.

## Regression checks

No model change was proposed, so nothing required backtesting *for adoption*.
Both backtests were run as regression checks on the cross-source change:

| | run 8 | runs 5-7 | match |
|---|---|---|---|
| NFL log-loss | 0.6517617405253826 | 0.6517617405253826 | digit-for-digit |
| NFL ROI | -8.208908995992267% | -8.208908995992267% | digit-for-digit |
| EPL 2425 holdout ROI | -5.11513157894739% | -5.115% | yes |

As expected: ESPN feeds neither model. **Tests 176 -> 204**, all network-free.

One process note on this, because it nearly became a false alarm: the first
NFL backtest run this session used `--seasons 2020..2024` and returned
log-loss 0.6543847, which does not match. That was my command being wrong, not
the code -- the canonical set documented in the README is 2018..2024. Checked
before writing it up as a regression.

## Data sources

| Source | Status |
|---|---|
| nflverse | Live. 2,499 games, 2,229 played. One transient HTTP 504, succeeded on retry. |
| football-data.co.uk | Live but **still has not published 2026-09-12**. E0 2026-27 stuck at 30 played, latest 2026-09-06 -- unchanged for a third run. |
| Kalshi REST | Live. 55 NFL + 23 EPL contracts on the current board. |
| **ESPN scoreboard (new)** | Live. 63 NFL + 50 EPL rows, verified 30/30 and 2/2 against the primary tables. |

Also recorded: `nfl_games.csv` lost a line this refresh -- `2026_09_DEN_CAR`
went from a populated moneyline/spread/total to blank upstream, while
`2026_09_NYJ_KC` gained one. Week-9 lookahead lines churn; the committed table
can *lose* values, not only gain them. Not acted on, but the merge in
`write_processed` keeps last-write-wins, so a blanked upstream row blanks ours.
Worth a look if a backtest ever depends on week-9 lines.

**Escalations: none.** No charge and no signup form is outstanding. The Odds
API stays rejected on run 2's reasoning, football-data.org stays unnecessary
per run 3, and the README's source table -- which was still listing both as
"optional" future options, contradicting CLAUDE.md -- has been rewritten to
state them as closed.

## Process note

The stored scheduled prompt still contains "do not post, send, change, or
delete anything" and the unfilled `[which data sources?]` placeholder.
CLAUDE.md has overridden the first for repository work since 2026-09-11 and
answered the second since 2026-09-13. Noted once, per CLAUDE.md, and not
carried into the summary.

## Open questions / next steps

- **Measure the final hour. It is mechanical now.** 13 NFL games with captures
  at T-2h and closer settle tonight; `cli line-movement` does the rest. Then
  decide `*/15` on the evidence.
- **NFL week 1 settles tonight** -- 11 of the 36 pre-registered wagers. Report
  against 7.79 selection-corrected / 9.21 market-implied / 11.23 claimed,
  whichever way it falls. This is the first leg where the three hypotheses
  actually separate.
- **Finish the hand-check of backfilled CLV.** Two of seven verified against
  raw snapshot rows this run; five remain, and they are the twelve-minute ones.
- **The 94 unmatched NFL settled markets in `verify-settlements`** have never
  been explained. Pre-existing, not this run's doing, and the soccer "0
  unmatched" headline should not be read as covering them.
- **`edge_threshold_pct: 3.0` has never been derived from anything** (run 5).
- **Move the edge threshold onto the fee-inclusive number** as a `p3` bump with
  explicit re-pricing -- deferred again, deliberately: run 5 tied it to week 1
  settling, and week 1 settles tonight, not this afternoon.
- **The selection gap remains the thing to attack** (run 4). The 8-wager EPL
  cohort is consistent with it (+22.9pp overstatement vs the market's +15.5pp)
  and far too small to confirm it.
- Kalshi's fee coefficient is still unread.
- The 5% relative-width liquidity gate remains unvalidated against realized
  fill quality.
- ESPN is an **undocumented** endpoint. It can change without notice. That is
  survivable by construction -- it is a cross-check and a fallback, so if it
  disappears verification gets louder and nothing already correct becomes
  wrong -- but `espn-audit` should be read every run, not assumed.
- **Standing reminder:** 0 live bets. 9 settled shadow bets, 2 wins, ROI
  -10.66%, and that number is one added loss away from the +0.51% run 7
  published. Neither is a result.
