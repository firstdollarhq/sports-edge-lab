# Scheduled run 13 -- the CLV number is smaller than the smallest price the venue can quote

_2026-09-16, 06:01-07:5xZ. Run 12 was 2026-09-15, 15:02-16:5xZ._

## Headline

**Two things broke or resolved today, and neither is about the model.**

1. **ESPN's date-range API stopped working.** `refresh-history` warned for both
   sports and kept the previous tables. The `YYYYMMDD-YYYYMMDD` form this
   project's cross-check source was built on now returns HTTP 400 for every
   range, on both leagues. Fixed by walking whole months instead, after
   checking that months return the same event set day-by-day requests do.
   ESPN is live again and the audit reproduces run 12's counts exactly.

2. **CLV is retired as a line of evidence, with a number.** The 30-minute cron
   has finally put captures inside the final hour, which is what runs 7 and 12
   said had to happen before the question could be asked. The answer is that
   the line does not move -- and the same measurement says the CLV mean this
   project has quoted for three runs is **0.38 of one tick**.

**No bets settled. Two new shadow rows logged.** The ledger's headline numbers
are unchanged from runs 11 and 12: 25 settled, 6 wins, **24.0%**, ROI
**-20.87%**. `live_enabled` stays `false` everywhere.

Tests **248 -> 256**.

## Finding 1: the pre-kickoff line barely moves, so `*/30` stays

CLAUDE.md carried a standing instruction: once there are captures inside the
final hour, measure how much the line moves there, and go to `*/15` if it
moves a lot. Both conditions are now testable. NFL closing captures sit at a
median of **T-0.42h**, with 29 captures per contract over a median 74-hour
window.

Moves to the closing quote, in implied-probability points:

| bucket | NFL mean \|move\| | NFL n | EPL mean \|move\| | EPL n | share >= 0.02 |
|---|---|---|---|---|---|
| T-1h..T-2h | 0.0036 | 28 | 0.0050 | 6 | **0% both** |
| T-2h..T-4h | 0.0036 | 28 | 0.0067 | 3 | **0% both** |
| T-4h..T-8h | 0.0042 | 12 | 0.0100 | 3 | 8.3% / 0% |
| T-8h..T-24h | 0.0057 | 30 | 0.0080 | 30 | 3.3% / 20% |
| T-24h..T-168h | 0.0071 | 28 | 0.0110 | 30 | 7.1% / 20% |

And over the **whole** pre-kickoff window, first capture to close:

| | NFL | EPL |
|---|---|---|
| contracts | 30 | 30 |
| median first capture | T-74.1h | T-48.4h |
| mean \|net move\| | **0.0157** | **0.0107** |
| median \|net move\| | 0.010 | 0.010 |
| max \|net move\| | 0.100 | 0.040 |
| never moved one tick | **30.0%** | 20.0% |
| \|net\| >= 0.05 | 6.7% | 0.0% |

Kalshi quotes whole cents. The final two hours are therefore moving *less than
the smallest change the venue can express*, and the entire information flow
from three days out to kickoff is one to two probability points. **`*/15` would
resolve movement that is not there. Cadence stays at `*/30`**, and CLAUDE.md
now records that as answered rather than open.

**The honest caveat on the EPL column:** the final-hour bucket is 6 contracts
and the T-2h..T-4h bucket is 3. That is not a fact about the EPL market; it is
three games. The NFL final-hour figure rests on 28 contracts and is the one
worth leaning on. EPL's *median* closing capture is still T-7.28h -- the dense
captures reached the NFL slate more completely than the EPL one, and that is
worth re-checking after another weekend rather than asserting now.

### A contamination trap, walked into and caught

The first version of this analysis computed kickoff as `expiration - median
observed lag` and reported a mean |net move| of **0.128** with a **0.66**
maximum -- eight times the real figure. Those "moves" were contracts settling
to 0.99 and 0.02: in-play quotes, which know part of the result.

`line_movement.collect_quotes` already resolves kickoff from the stats source
precisely because Kalshi's expiration sits 3h (EPL) to 6h (NFL) after kickoff,
and its docstring says so in as many words. The ad-hoc script re-derived what
the module already had and got the contaminated answer the module exists to
prevent. Redone on `collect_quotes`, the numbers above agree with the `line-movement`
command. **Nothing was published from the bad pass, but it is recorded here
because it is the thirteenth instance of this project's recurring failure --
a value that is not what the surrounding code assumed -- and this time the
guard that caught it was an existing module's docstring.**

## Finding 2: the CLV mean is quantisation noise, and now says so in the report

Runs 10, 11 and 12 each quoted a mean CLV as an independent read on the model,
most recently **-1.14% over 16 real closes**. Finding 1 implies that number
cannot contain much. Measured directly:

| | all settled (n=25) | real close, lag <= 1h (n=16) |
|---|---|---|
| mean `clv_pct` | +0.728% | **-1.138%** |
| 95% CI (bootstrap, 20k) | [-1.237, +2.787] | **[-3.253, +0.643]** |
| **median `clv_pct`** | **+0.000%** | **+0.000%** |
| mean price paid | 0.346 | 0.374 |
| **one tick at those prices** | **3.55%** | **3.02%** |
| \|mean CLV\| in ticks | 0.20 | **0.38** |
| rows that never moved a tick | 48% | 50% |

`clv_pct` is `(placed_odds / closing_odds - 1) * 100` in decimal odds, so one
cent is worth ~2% at a 50c contract, ~3% at 35c and ~7% at 15c. **At the prices
this ledger actually paid, one tick is about three times the headline mean.**
Half the settled rows closed at exactly the price they were struck at, which is
why the median is not merely small but exactly zero. Both confidence intervals
straddle zero.

So `-1.14%` is not a measurement of the model. It is which side of a tick eight
rows happened to land on. **This does not rehabilitate the model** -- the
ROI, the win rate, the discrimination bound and the selection gap are all
untouched and all still negative. It removes one *apparently independent*
negative number from the pile, which matters in the other direction too: a
future run that saw CLV turn positive would have been entitled to call it
evidence, and it would not have been.

`ledger-summary` now prints a `clv_resolution` block next to the CLV mean --
tick value at the prices paid, median, mean |CLV| in ticks, and the share of
rows that never moved -- so the context travels with the number instead of
having to be re-derived. CLAUDE.md now says not to quote a CLV mean without it.
Three tests pin it, including the under-one-tick contract that has no cheaper
neighbour.

## Finding 3: ESPN's range parameter is gone; months replace it

`refresh-history` opened the run with:

```
[warn] ESPN nfl refresh failed (400 ... dates=20260801-20261007); keeping existing table
[warn] ESPN soccer refresh failed (400 ... dates=20260801-20261007); keeping existing table
```

Body: `{"code":400,"message":"Failed to get events endpoint."}`. Diagnosed by
probe rather than guess, because "undocumented endpoint returned 400" has
several causes implying different fixes:

| request | result |
|---|---|
| `dates=20260801-20261007` (67d) | 400 |
| `dates=20260801-20260810` (10d) | 400 |
| `dates=20260901-20260907` (7d) | 400 |
| `dates=20260914` (single day) | **200** |
| `dates=202609` (month) | **200** |
| `dates=2026` (year) | **200** |
| `dates=20260914,20260915` (list) | 400 |

Every range fails down to seven days, so it is the range **syntax**, not window
width and not rate limiting. Months and single days both survive; months win on
request count -- the default window is ~67 days, which is 3 requests by month
against 67 by day, twice per refresh.

**Fetching coarser than you filter is exactly how a quiet truncation hides**, so
month-vs-day equivalence was checked rather than assumed, over 2026-09 for both
sports: 48 NFL events and 30 EPL events by month, the same 48 and 30 by the
union of thirty day-requests, **zero ids in one and not the other**.

`fetch_espn_games` now walks months and trims back to the requested window,
widened by one day at each end -- ESPN dates an event by US local date while
this table's `game_date` is UTC, and a Sunday-night NFL kickoff is Monday in
UTC, so a hard trim would drop exactly the late games at each boundary. A month
that fails is fatal rather than skipped, keeping this module's standing rule
that a missing fixture must never be able to look like an agreeing one; the
CLI already catches that and keeps the committed table.

**The fix is verified twice over.** The audit reproduces run 12 exactly -- NFL
16/16 scores and kickoffs agreed, EPL 40/40, `only_espn: 0` and
`only_primary: 0` on both. And more stringently: **both committed ESPN tables
came out byte-identical**, `git status` showing no modification at all after
the refresh. That is not a coincidence of rounding. `write_processed` routes
through `_keep_unchanged_rows`, which holds back the stored row whenever the
freshly fetched one is substantively the same, so an unmodified file means
every one of the 64 NFL and 50 EPL rows matched the range-fetched version
field for field. Same table, different transport.

This is the risk CLAUDE.md flags every run -- "ESPN is an **undocumented**
endpoint" -- arriving. It behaved as designed: a cross-check source degraded
loudly, nothing that was already correct became wrong, and the model never
touched it.

## Bets

**Nothing settled.** 24 pending at the start, 0 resolved, 0 CLV filled, 0
backfilled. NFL week 2 opens 09-17; today is the Wednesday before the slate.

**Two new rows logged**, both `shadow`, out of 24 flagged recommendations:

| matchup | side | model | fair | edge | after fee | kickoff |
|---|---|---|---|---|---|---|
| ARI @ SF | away | 0.275 | 0.193 | +37.4% | +30.1% | 2026-09-27T20:05Z |
| Man United @ Fulham | home | 0.289 | 0.272 | +3.3% | **-1.6%** | 2026-09-20T15:30Z |

The rest were duplicates of open rows: NFL 16 flagged of 45 fillable (35.6%),
EPL 8 of 26 (30.8%), `skipped_duplicate` 15 and 7. `illiquid_skipped` 19 NFL
and 4 EPL, `in_play_skipped: 0`, `superseded_voided: 0`. The NFL board doubled
to 64 contracts as week 2 came up.

**The Fulham row's negative after-fee edge is deliberate, not a leak.** The
3% gate tests the pre-fee number by design: run 10 backtested moving it onto
the fee-inclusive edge (p3) and rejected it on the evidence -- NFL got 1.39pp
*worse*, the two legs disagreed in sign at every fee rate from 0.01 to 0.10,
and the mechanism was that a fee-inclusive minimum is still a minimum on
*claimed* edge, so it selects harder for the model's own overstatement. The
row is logged with `edge_after_fee_pct` recorded so the cohort can be cut
either way later. `PRICING_VERSION` remains frozen until 09-21.

Ledger after this run:

| | run 12 | run 13 |
|---|---|---|
| settled | 25 | 25 |
| wins | 6 | 6 |
| pending | 24 | **26** |
| void | 67 | 67 |
| win rate | 24.00% | 24.00% |
| ROI | -20.87% | -20.87% |
| mean CLV (real close) | -1.14% (n=16) | -1.14% (n=16), **0.38 ticks** |

Integrity: **51 non-void rows = 51 distinct `bet_id` = 51 distinct
(game, selection, market).** Every row `shadow`.

**The pre-registered cohort was again deliberately not re-scored.** Run 11
recorded that the 36-wager pre-registration had by then been looked at three
times against a growing sample with no correction for having looked, and fixed
the honest read at 36 wagers on 09-21. Nothing settled today, so re-running
`scorecard` would have produced the identical `p_at_most_model` as a *fourth*
look. It was not run. **11 wagers still to kick off, 09-20 to 09-21T00:20Z.**

The largest claimed edge on the board is again **MIA @ SF away at +163.3%**
(model 0.316 against a 0.114 fair price) -- the same winner's-curse signature
run 4 and run 11 measured, still the biggest number on the screen, still an
existing open row rather than a new stake.

## Regression checks

All four canonical numbers reproduce digit-for-digit:

| | run 13 | runs 5-12 | match |
|---|---|---|---|
| NFL log-loss | 0.6517617405253826 | 0.6517617405253826 | digit-for-digit |
| NFL ROI | -8.208908995992267% | -8.208908995992267% | digit-for-digit |
| NFL n_games / n_bets | 1942 / 1625 | 1942 / 1625 | exact |
| EPL 2425 holdout ROI | -5.11513157894739% | -5.11513157894739% | digit-for-digit |

Re-derived by `test_benchmarks.py` from the committed tables, not read off a
screen. `verify-settlements` clean: NFL 32/32 agreed, soccer 120/120,
`unmatched_in_coverage: 0` both, 94 NFL unmatched all out-of-coverage
(preseason, which nflverse does not carry). `espn-audit` clean as tabulated in
Finding 3.

Tests 248 -> 256: five for the ESPN month walk (window arithmetic, a
year-boundary roll, a backwards window, the month-to-window trim, and the
late-kickoff boundary case), three for `clv_resolution`.

## Data sources

| Source | Status |
|---|---|
| nflverse | Live. 2,499 games, 2,243 played -- unchanged; week 2 starts 09-17. |
| football-data.co.uk | Live. E0 2026-27 at 40 played, unchanged. |
| Kalshi REST | Live. **64** NFL + 30 EPL contracts captured (week 2 board up). |
| ESPN scoreboard | **Broke and fixed this run.** See Finding 3. NFL 64 rows / 16 played, EPL 50 / 40. |

Capture cron healthy: snapshots every ~30 minutes through the night, most
recent commit 04:36Z, ~85 minutes before this run started.

**Escalations: none.** No charge and no signup form is outstanding. The ESPN
fix used the same free, keyless source it already had.

## Open questions / next steps

- **The honest null remains the leading hypothesis** and nothing today moved
  it. Run 12's negative result on free context features stands; this run added
  no model change, and deliberately so -- the two defects worth fixing were in
  the measurement apparatus, not the model.
- **Finding 1 is evidence against the one remaining idea run 12 named.** That
  idea was information the closing line prices *late* or *badly*. A line that
  moves less than one tick in its final two hours is not a line leaving late
  information unpriced. It does not rule out "prices badly", but "prices late"
  is now the weaker half of that pair, measured rather than assumed.
- **The EPL final-hour buckets are 3 and 6 contracts.** Re-measure after the
  09-19/20 slate before treating the EPL column as anything but suggestive.
- **Score the pre-registered cohort at 36 on 09-21 and treat that as the
  read.** Do not re-score the partial cohort; runs 12 and 13 did not.
- **After 09-21, `PRICING_VERSION` is free to move**, unchanged since run 10.
- The 5% relative-width liquidity gate remains unvalidated against realized
  fill quality. The dense snapshots are now rich enough to attempt this --
  quoted ask vs. the ask that persisted -- and it is the obvious next
  apparatus question.
- Nothing in `pyproject` is pinned exactly; `test_benchmarks.py` catches the
  consequences rather than preventing them.
- NFL preseason markets are priced and settled by Kalshi but invisible to
  nflverse; labelled, not fixable.
- **ESPN is undocumented and has now broken once.** `espn-audit` is read every
  run, which is how this was caught within a day. Expect it again.
- **Standing reminder:** 0 live bets. 25 settled shadow bets, 6 wins, ROI
  **-20.87%**. The market beats the model on every scoring rule on the bets the
  model itself chose; the model ranks games significantly worse than the
  closing line; the free information that was supposed to close that gap makes
  it wider; and as of today the one metric that had been mildly ambiguous is
  not ambiguous but simply too coarse to read. That is the deployment gate
  doing its job, and it is still 25 wagers.

## Process note

The stored scheduled prompt still carries "do not post, send, change, or
delete anything" and the unfilled `[which data sources?]` placeholder.
CLAUDE.md has overridden the first for repository work since 2026-09-11 and
settled the second since 2026-09-13. Noted once, per CLAUDE.md, and not
escalated.
