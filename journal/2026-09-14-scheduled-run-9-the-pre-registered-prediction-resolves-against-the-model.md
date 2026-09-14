# Scheduled run 9 -- the pre-registered prediction resolves, and it resolves against the model

_2026-09-14, 06:02-07:10 UTC. Run 8 was 2026-09-13 15:01-15:40Z._

## Headline

**Run 4's pre-registered prediction has resolved on 23 of its 36 wagers, and
the model's own claim is the hypothesis it falsifies.** NFL week 1 settled
overnight: 13 wagers, 4 wins, against a claimed 5.87 and a selection-corrected
4.09. The corrected number is right to within a tenth of a win.

**The CLV story from run 8 has inverted.** Mean CLV falls from **+4.04% to
+0.72%**, and the only cohort in the project that has ever been measured
against a genuine closing price -- the 13 NFL wagers, reference at **T-0.42h**
-- reads **-1.03%**. Run 8 wrote that its +4.04% was "not yet interpretable"
and listed the stale reference as the reason. That caution was correct, and
this run is what it looked like when the real number arrived.

**The final hour is measured, for the first time, on 26 contracts.** It barely
moves. `*/15` is **rejected** on that evidence; capture stays at `*/30`.

**The 94 unmatched NFL settled markets are explained and the item is closed.**
All 94 are preseason. No model changed, no backtest moved, `live_enabled`
stays `false` everywhere.

## Finding 1: the pre-registered prediction, resolving

The cohort is the 36 distinct wagers run 7 restated from run 4's "70 bets":
1 logged 2026-09-10 plus 35 logged 2026-09-11. It was reconstructed here from
`placed_at` rather than trusted, and it reproduces run 7's table exactly --
NFL 25 wagers claiming 11.23 against 9.21 market-implied, EPL 11 claiming 3.96
against 3.28. Digit-for-digit on both legs, which is the check that the right
36 rows are being scored.

23 of the 36 have now settled. **All 23 settled rows are pre-registered ones**;
the 8 wagers logged in runs 6-8 are all still open, so the scorecard and the
prediction are looking at the same population this run.

| leg | resolved | **actual** | claimed | selection-corrected | market-implied |
|---|---|---|---|---|---|
| NFL | 13 | **4** | 5.87 | **4.09** | 4.82 |
| EPL | 10 | **2** | 3.58 | 3.13 | 2.95 |
| **total** | **23** | **6** | **9.45** | **7.22** | **7.77** |

Exact Poisson-binomial P(X <= 6) under each hypothesis, over the 23 realized
wagers:

| hypothesis | expected | P(X <= actual) |
|---|---|---|
| model's own claim | 9.45 | **0.095** |
| selection-corrected | 7.22 | 0.377 |
| market-implied | 7.77 | 0.287 |

Read honestly: **none of these is a rejection at any conventional level**, and
0.095 is not 0.05. What the table says is that the observed result sits in the
tail of the model's claim and comfortably inside both of the other two. The
NFL leg is the sharp one, because that is where run 7 noted the three
hypotheses separate: corrected 4.09, market 4.82, claimed 5.87, **actual 4**.

This is one slate of one week of one season. It is the single most informative
thing the project has produced, and it is still 23 wagers.

### The direction within the cohort

Splitting the 23 at the median claimed edge (19.4%):

| half | n | wins | claimed | realized minus claimed | mean claimed edge |
|---|---|---|---|---|---|
| low-edge | 12 | 4 | 4.55 | **-0.55** | 12.5% |
| high-edge | 11 | 2 | 4.89 | **-2.89** | 31.7% |

The bigger the claimed edge, the bigger the overstatement. That is the
signature run 4's selection audit predicted, seen for the first time in
realized money rather than in backtest. At n = 11 and 12 it is a direction,
not a measurement, and it should not be quoted as one.

## Finding 2: CLV reverses once the reference is real

Run 8 reported mean CLV **+4.04%**, five positive, four exactly zero, **zero
negative**, and then spent four paragraphs explaining why it should not be
believed -- four of nine readings compared entry to a "close" twelve minutes
later, and the best reference in the set (T-1.2h) read exactly 0.00%.

With 23 settled rows and NFL's genuine T-0.42h references:

| | run 8 | run 9 |
|---|---|---|
| rows with CLV | 9 | **23** |
| mean CLV | **+4.04%** | **+0.72%** |
| median | -- | **0.00%** |
| positive / zero / negative | 5 / 4 / **0** | 7 / 12 / **4** |

Split by leg, which is the split that matters, because the two legs have
completely different reference quality:

| leg | n | reference lag | mean CLV |
|---|---|---|---|
| **NFL** | 13 | **T-0.42h** (real close) | **-1.03%** |
| EPL | 10 | T-7.75h (stale) | +3.00% |

**The leg with a real closing price shows negative CLV. The leg with a
reference nearly eight hours early shows +3%.** That is the whole of run 8's
warning, confirmed: the positive CLV was substantially an artifact of
measuring against a price that was not the close.

Two further details, both recorded because they cut against any flattering
reading:

- **12 of 23 readings are exactly 0.00%.** The line did not move at all on
  more than half the book. A CLV programme measuring a market that does not
  move is measuring rounding.
- **CLV does not separate winners from losers here**: mean +0.98% on the 17
  losers and +0.01% on the 6 winners. If CLV were tracking skill in this
  sample it would point the other way.

The largest single reading in the set is still EPL: Arsenal @ Sunderland at
+16.67%, which run 8 verified by hand as a two-cent tick on a 12c contract.

## Finding 3: the final hour, measured

This was the item run 7 and run 8 both designated as the next run's headline,
and it lands. NFL week 1 gave 26 contracts whose last pre-kickoff capture sits
**25 minutes** before kickoff, against a median 7.75h for everything the
project held before the cron.

NFL, |change| in implied probability against a reference at T-0.42h:

| bucket | n | mean | median | max | share >= 2c |
|---|---|---|---|---|---|
| **T-1h..T-2h** | 26 | **0.0038** | 0.000 | 0.01 | **0%** |
| T-2h..T-4h | 26 | 0.0038 | 0.000 | 0.01 | 0% |
| T-4h..T-8h | 10 | 0.0040 | 0.000 | 0.02 | 10% |
| T-8h..T-24h | 28 | 0.0057 | 0.010 | 0.02 | 3.6% |
| T-24h..T-168h | 26 | 0.0065 | 0.010 | 0.02 | 3.8% |

**Decision: capture stays at `*/30`. `*/15` is rejected.** CLAUDE.md set the
bar as "once there are captures inside the final hour, measure how much the
line actually moves there; if it moves a lot, `*/15` costs nothing." It does
not move a lot. Not one of 26 contracts moved as much as two cents inside the
final two hours, and the median move is zero. Doubling the capture rate would
buy resolution on a quantity whose entire observed range is one cent.

The genuinely useful number in that table is the *gap between rows*: moving
the reference from T-8h to T-0.42h changes the measured price by about
0.6c on average. So the pre-cron CLV readings were not wildly wrong in
magnitude -- they were wrong in a way that is small, one-directional, and
about the same size as the entire effect being measured. That is worse than a
large error, not better, and it is exactly what Finding 2 shows.

This is still one NFL slate. It is 26 contracts instead of run 8's 3, and NFL
week 1 is a high-liquidity slate, so "quiet" remains the best case rather than
the typical one.

## Finding 4: the 94 unmatched NFL markets were preseason all along

`verify-settlements` has reported `unmatched_games: 94` on the NFL leg since
run 7 and nobody had said what they were. Run 8 recorded it as "pre-existing,
not investigated" rather than folding it into its "0 unmatched" soccer
headline, which was the right call and is why it was still visible to pick up.

Enumerated this run: **all 94 are August 2026 dates.** Every one is a
preseason game. nflverse carries regular season and playoffs only -- the 2026
table's first played game is 2026-09-09 -- so those markets have no
counterpart to check against and never will. Run 8's bug 12 filtered the same
preseason games out of the ESPN table for a related reason.

So the number was never a defect. But it was reported in a way that could hide
one: a real mapping failure on a covered date would have had to move a counter
that already read 94 before anyone noticed. `unmatched` was doing two jobs.

`verify_against_stats` now splits it, using per-season coverage windows derived
from the stats table itself (a single global min..max cannot work -- August
2026 sits inside the 2018..2026 span but outside every individual season):

| | NFL | soccer |
|---|---|---|
| checked / agreed | 30 / **30** | 117 / **117** |
| unmatched, out of coverage | **94** (all preseason) | 0 |
| unmatched, **in coverage** | **0** | **0** |
| mismatches | 0 | 0 |

`unmatched_in_coverage` is the number to watch, it should be 0, and it is.

**This is a reporting fix, not a bug fix, and the running tally stays at 12.**
No published number was ever wrong because of it. Inflating the bug count with
a legibility problem would misrepresent what the tally is for.

Five tests added, including one asserting that an in-coverage miss is *not*
absorbed into the out-of-coverage bucket -- the failure mode the old counter
had. **Tests 204 -> 209**, all network-free.

## Bets

`recommend` flagged **17 of 34** NFL contracts (50.0%) and 6 of 24 EPL
(25.0%), logging 2 new wagers and skipping 21 as duplicates of open rows.
`in_play_skipped: 0` and `illiquid_skipped: 9` on the EPL side, the standing
thin-book pattern.

A model flagging half of a regulated exchange's NFL board as +EV is still
mostly describing itself. Every row remains `shadow`.

**Ledger integrity: 46 non-void rows = 46 distinct wagers.** `void_superseded_rows`
is still holding; `superseded_voided` was 0 this run, correctly, since no
pricing version changed.

| | run 8 | run 9 |
|---|---|---|
| settled | 9 | **23** |
| wins | 2 | **6** |
| pending | 35 | 23 |
| win rate | 22.2% | **26.1%** |
| ROI | -10.66% | **-13.98%** |
| mean CLV | +4.04% | **+0.72%** |

Scorecard, all 23 settled: model log-loss **0.6535** against the market's
**0.6030**; model Brier 0.2318 against 0.2057. **The market beats the model on
every scoring rule, on the bets the model itself chose.** Model overstatement
+15.0pp, market overstatement +7.7pp.

## Regression checks

No model change was proposed, so nothing required backtesting for adoption.
Both were run as regression checks on the `verify_against_stats` change:

| | run 9 | runs 5-8 | match |
|---|---|---|---|
| NFL log-loss | 0.6517617405253826 | 0.6517617405253826 | digit-for-digit |
| NFL ROI | -8.208908995992267% | -8.208908995992267% | digit-for-digit |
| EPL 2425 holdout ROI | -5.11513157894739% | -5.11513157894739% | digit-for-digit |

As expected -- the change touches only verification reporting. Selection audit
also reproduces: NFL flagged gap **-0.137**, soccer **-0.045**, blend weight
w* = 0 for NFL (model adds nothing) and w* = 0.10 for soccer with
`improvement_significant: false`.

## Data sources

| Source | Status |
|---|---|
| nflverse | Live. 2,499 games, **2,242 played** (+13: NFL week 1). |
| football-data.co.uk | Live but **still has not published 2026-09-12**. E0 2026-27 stuck at 30 played, latest 2026-09-06 -- unchanged for a **fourth** run. |
| Kalshi REST | Live. 34 NFL + 24 EPL contracts on the board; 124 settled NFL markets, 117 settled EPL. |
| ESPN scoreboard | Live. NFL 15/15 scores and 15/15 kickoffs agree; EPL 30/30 and 30/30. 10 fixtures only in ESPN. |

`espn-audit` read this run per CLAUDE.md, not assumed. The 10 "only in ESPN"
EPL rows are precisely the football-data.co.uk gap, which is the reason run 8
wired ESPN up and the reason the EPL leg settled at all.

**Escalations: none.** No charge and no signup form is outstanding.

## Process note

The stored scheduled prompt still carries "do not post, send, change, or
delete anything" and the unfilled `[which data sources?]` placeholder.
CLAUDE.md has overridden the first for repository work since 2026-09-11 and
settled the second since 2026-09-13. Noted once, per CLAUDE.md, and not
carried into the summary.

## Open questions / next steps

- **The remaining 13 pre-registered wagers** (12 NFL, 1 EPL) settle through
  2026-09-21. Pre-registering the rest now, on the same three hypotheses:
  claimed **5.74**, selection-corrected **4.05**, market-implied **4.72**.
  Writing it down before the games, as before.
- **`edge_threshold_pct: 3.0` has never been derived from anything** (run 5).
  With 23 settled wagers and a visible edge-size gradient, this is the first
  run where deriving it from evidence is even arguable. Still too thin.
- **Move the edge threshold onto the fee-inclusive number** as a `p3` bump --
  deferred since run 5, and run 8 tied it to week 1 settling. Week 1 has now
  settled. This is the leading candidate for run 10's model change, and it
  must clear the deployment gate in backtest before adoption, not merely
  improve on p2.
- **CLV is measuring a market that does not move.** 12 of 23 readings are
  exactly zero and the full observed range inside two hours is one cent. Worth
  asking whether CLV can be a useful signal at this venue at all, rather than
  continuing to collect it by default.
- **NFL preseason markets are settled and priced by Kalshi but invisible to
  nflverse.** Not a defect, now labelled, but it does mean the project has no
  way to check a preseason settlement if one is ever bet.
- **The selection gap remains the thing to attack** (run 4), and for the first
  time there is out-of-sample evidence consistent with it rather than only
  backtest evidence.
- Kalshi's fee coefficient is still unread.
- The 5% relative-width liquidity gate remains unvalidated against realized
  fill quality.
- ESPN is an **undocumented** endpoint; `espn-audit` is read every run, not
  assumed.
- **Standing reminder:** 0 live bets. 23 settled shadow bets, 6 wins, ROI
  **-13.98%**, and the model loses to the closing line on every scoring rule
  on the bets it chose. That is the deployment gate doing its job, and it is
  still 23 wagers.
