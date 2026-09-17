# Scheduled run 16 -- the dead source is replaceable for the thing the model actually reads

_2026-09-17, 15:02-16:0xZ. Second run of the day; run 15 ran 06:01-07:5xZ._

## Headline

**The EPL rating path no longer depends on a host that has been down for 33
hours.** Run 15 gave this run a deadline of 09-19 -- the next EPL fixtures --
and two ways to meet it: wire EPL results from ESPN into the rating path, or
find another free mirror of the football-data files. The first is done and
verified on real data; the second is closed, see below.

**The verification is the part worth reporting.** Rebuilding the EPL ratings
from a committed table truncated to before 2026-09-11 -- the state the 09-19
fixtures would have left it in -- and filling the gap from ESPN reproduces the
real rating book **exactly: all 30 clubs, maximum difference 0.0**, no phantom
entity, and all 10 recovered scores matching what football-data.co.uk itself
had said. ESPN is a bit-for-bit substitute for the dead source in the one thing
the live model reads.

**What it costs, said plainly.** The gate that licenses a degraded run --
"usable iff ESPN reports no played game the table lacks" -- was worth something
because ESPN was an *independent* check on someone else's table. For a
supplemented row it is both the filler and the checker, so `usable` is
trivially true of rows that came from ESPN. The pre-fill gap is therefore kept
beside the post-fill gap and printed in the run log, so a supplemented run
can never read like a run that needed no supplement.

**No bets settled, for the fifth run running.** NFL week 2 opens
09-18T00:15Z, about nine hours after this run ended. Ledger unchanged from runs
11-15: **25 settled, 6 wins, 24.0%, ROI -20.87%**. One new shadow row. Nothing
in the model, the gate or `PRICING_VERSION` was touched.

Tests **286 -> 295**.

## Finding 1: the source is still down, and a mirror is not available to this session

Same redirect loop as run 15, re-checked on four paths:

```
https://www.football-data.co.uk/mmz4281/2627/E0.csv -> 302 -> https://football-data.co.uk/...
https://football-data.co.uk/mmz4281/2627/E0.csv     -> 302 -> http://127.0.0.1/...
http://www.football-data.co.uk/...                  -> 302 (same chain)
https://www.football-data.co.uk/  and  /englandm.php -> 302 (same chain)
```

`www` to apex, apex to loopback, every path, plain HTTP and HTTPS alike. 33
hours and unchanged.

**The mirror option is closed for a reason that is about this session, not
about the mirrors.** The obvious free mirrors of the football-data CSVs are
GitHub repositories, and this session's GitHub access is scoped to
`firstdollarhq/sports-edge-lab` alone -- reading another repository is outside
what it may do, whether through the API or through `raw.githubusercontent.com`.
That is a constraint on the runner, so it should not be recorded as a fact
about what sources exist. **A future run with wider access should re-check
it before concluding anything.** Nothing was fetched from one.

**This is not an escalation and needs nobody's permission.** CLAUDE.md's bar
for a source is free, no human-created account, verified against something
already held. ESPN clears it, is already here, and has now been verified for
this specific use rather than in general.

## Finding 2: ESPN results reproduce the primary source's ratings exactly

`models/live.build_soccer_model` reads `season`, `game_date`, `home_team`,
`away_team`, `home_score`, `away_score`, `result`. **Not one odds column.**
ESPN carries every one of those fields. So the question was never whether ESPN
could stand in for football-data.co.uk in general -- it cannot, it has no odds
-- but whether it can stand in for it *in the rating path*, which is the only
place a live price comes from.

`ingest/sources._supplement_from_espn` fills a results gap in the committed
table with ESPN's played games, in memory, at load time. Measured against the
real tables:

| | |
|---|---|
| committed table truncated to | before 2026-09-11 |
| played games thereby removed | **10** |
| recovered by the supplement | **10 of 10** |
| scores matching the real primary rows | **10 of 10** |
| clubs in the rating book | 30 both ways, none only on one side |
| **max abs rating difference vs. the real table** | **0.0** |
| odds columns on supplemented rows | all NaN |
| residual gap after the fill | 0 |

Pinned by `test_espn_results_reproduce_the_primary_ratings_exactly`, which runs
that truncation against the **committed** tables rather than a fixture. A
synthetic frame would have proved nothing here: the entire risk is that these
two particular sources disagree about a name, a date, an ordering or a score,
and only the real files can answer that.

### Three things the mechanism refuses to do

**It never re-adds a fixture the table already has.** The gap counter
(`audit_against_primary`'s `only_espn`) and the gap filler (`unmatched_played`)
now share one matcher, `_aligned` + `_primary_hit`, extracted for exactly this
reason. Had the filler matched on raw calendar date while the counter matched
on kickoff within two days, a late kickoff dated locally by one source and in
UTC by the other would have been "missing", appended a second time, and
**double-counted that result in every rating downstream of it** -- silently.
That is this project's recurring failure and it was one plausible refactor
away. The audit's numbers are unchanged by the extraction: NFL 16/16 scores and
kickoffs, EPL 40/40, `only_espn` 1 on soccer (the unplayed 09-18 Brentford v
Chelsea fixture), `verify-settlements` 32/32 and 120/120, `unmatched_in_coverage`
0 -- identical to run 15's, before and after.

**It never imports a club the rating book has not seen.** If ESPN renamed
`Nott'm Forest`, its games would stop matching, arrive here as a gap, and be
imported under a name Elo has no rating for -- opening a *second* entity at the
default rating while the real one went stale, with nothing in the output to
show it. Such rows are left out, which leaves the residual gap standing, which
takes the league dark with the offending name written into the provenance. A
club whose first ever appearance is on ESPN alone is refused by the same rule;
one dark league is the cheaper error.

**It never reaches a backtest.** Backtests train and score against the closing
line, so an odds-free row is not a game they can use -- it is a hole for some
later `dropna` to interpret. `cli._load_games` reads the committed table
directly and never calls this module, the supplement is in memory only, and
nothing here writes to `data/processed/`. Asserted by
`test_supplement_does_not_reach_backtest_loader` as an invariant of the design
rather than of today's implementation.

### The change is dormant until it is needed

Today's run exercised none of it: no EPL fixture falls between 09-14 and 09-19,
so the gap was 0 of 40 played and the supplement did not fire. `recommend
--sports soccer` behaved exactly as in run 15. The first real exercise is
09-19, and the failure mode if something was still missed is the loud one --
residual gap, league dark -- not a quiet price.

## Finding 3: the outage is not costing us an irreplaceable record

Worth stating because the opposite is the natural assumption and it is what
CLAUDE.md says about snapshots. **EPL fixtures played during this outage will
never have a bookmaker-average closing line**, because that is what
football-data.co.uk supplies and it cannot be reconstructed after the fact.

But the closing *price* for those fixtures is being captured anyway. The 9 EPL
events at or after 09-19 already hold **5,049 captured quotes** in
`data/snapshots/soccer/`, from the `*/30` cron, and run 5 measured Kalshi and
the sportsbook pricing the same games the same way (corr **0.9955** over 28
games) with `backtest/kalshi_engine.py` already built to backtest at that
venue.

So the honest statement is: **the bookmaker column is lost for these fixtures
and the venue we would actually trade on is fully recorded.** Reconstructing an
EPL closing line from the snapshot store is real work and it is *not* urgent,
because nothing perishable is being lost while the cron runs -- it can be done
from committed data at any later date. That is the reason it was not done
today, rather than it being a thing this run ran out of room for.

## Bets

**Nothing settled.** 31 pending at the start, 0 resolved, 0 CLV filled, 0
backfilled. First pending row settles 09-18T00:15Z (BUF vs DET). Fifth
consecutive run with no settlement; the ledger has not moved since run 11.

**One new row logged**, `shadow`, out of 26 flagged recommendations across both
sports:

| matchup | side | model | fair | ask | edge | after fee | kickoff |
|---|---|---|---|---|---|---|---|
| Coventry @ Nott'm Forest | away | 0.206 | 0.170 | 0.17 | +21.3% | +15.9% | 2026-09-19 |

NFL flagged 17 of 49 contracts (34.7%) and logged **none** -- all 17 were
duplicates of open rows, the ninth consecutive run in which the NFL board
produces no new position. EPL flagged 9 of 27 (33.3%), 8 duplicates.
`illiquid_skipped` 15 NFL and 3 EPL, `in_play_skipped` 0, `superseded_voided` 0.

Ledger after this run:

| | run 15 | run 16 |
|---|---|---|
| settled | 25 | 25 |
| wins | 6 | 6 |
| pending | 31 | **32** |
| void | 67 | 67 |
| win rate | 24.00% | 24.00% |
| ROI | -20.87% | -20.87% |
| mean CLV (real close) | -1.14% (n=16) | unchanged, n=16 |

`clv_resolution` alongside, as required: one tick is **3.552%** of `clv_pct` at
this ledger's mean price paid (0.346), the median reading is **0.000%**, and
**48% of settled rows never moved a tick**. The -1.14% is **0.32 of a tick**
and is not a magnitude. (CLAUDE.md and the README quote the same figure as
"0.38 of a tick", from the rounder "~3%" tick in run 13's prose. The value
`ledger-summary` actually prints is 3.552%, which gives 0.32. Nothing turns on
the difference -- both say "under half a tick" -- but the printed number is the
one to quote, and the older prose is left alone rather than restated here.)

**The ledger round-trip fix from run 15 is holding**: today's `git diff` on
`bets/ledger.csv` is one added line and nothing else, across a `recommend` and
a `settle` that each rewrote the file.

**The pre-registered cohort was again not re-scored**, fifth run running, for
the same reason each time: nothing has settled. 11 wagers still to kick off,
the first tonight. **Score it at 36 on 09-21.**

## Regression checks

Four canonical numbers, from the committed tables on a container that
re-resolved every dependency from scratch:

| | run 16 | runs 5-15 | match |
|---|---|---|---|
| NFL log-loss | 0.6517617405253826 | 0.6517617405253826 | digit-for-digit |
| NFL ROI | -8.208908995992267% | -8.208908995992267% | digit-for-digit |
| NFL n_games / n_bets | 1942 / 1625 | 1942 / 1625 | exact |
| EPL 2425 holdout ROI | -5.11513157894739% | -5.11513157894739% | digit-for-digit |

`test_benchmarks.py` asserts these against a live backtest rather than leaving
them to be eyeballed, and passes. pandas resolved to 3.0.5 again.

Tests 286 -> 295: five for the supplement (the fill, the pre/post gap pair, the
NaN odds columns, the tolerance case that must not duplicate, the residual gap
that must still refuse), one for the rename guard, one real-data equivalence
test, two for `unmatched_played` against the audit's own count.

`refresh-history` exits **1** with the source it could not refresh, as designed.
(Checked properly this time: piping it into `tail` reports `tail`'s exit status,
which read as 0 on the first attempt this run and would have been recorded as a
regression that was not there.)

## Data sources

| Source | Status |
|---|---|
| nflverse | Live. 2,499 games, 2,243 played. 5 week-2 rows revised (spreads and prices moving). |
| **football-data.co.uk** | **DOWN ~33h.** Redirect loop to `http://127.0.0.1/`. Committed table used, ESPN-verified complete, and now ESPN-repairable. |
| Kalshi REST | Live. 49 NFL + 27 EPL contracts. |
| ESPN scoreboard | Live. NFL 65 rows / 16 played, EPL 50 / 40. Now also the EPL results fallback. |

Capture cron healthy: snapshots every ~30 minutes through the day, most recent
14:36Z before this run started.

## Open questions / next steps

- **09-19 is the first real exercise of the supplement.** Expect the EPL table
  to fall behind by a matchday and the fill to close it. If the residual gap is
  non-zero, the league goes dark and the provenance says why -- read
  `espn_supplement.unknown_teams` first.
- **Reconstructing an EPL closing line from the snapshot store** is now the
  standing way to keep the EPL backtest sample growing through the outage. Not
  urgent (Finding 3), real work, and worth doing if the source stays dead past
  a couple of matchdays.
- **A mirror of the football-data CSVs was not checked**, because this session
  may only read one GitHub repository. Not a finding about mirrors.
- **Run 15 was asked for a model idea with a stated reason to expect a
  different outcome, said it had none, and this run has none either.** That is
  **four consecutive runs of apparatus-only work**, which is now the most
  honest thing on this page. The apparatus was worth building -- a source died
  and the project kept running -- but nothing in runs 13-16 has moved the
  central question, and three separate lines of evidence (runs 11, 12, 15) say
  the ideas already tried should be expected to keep failing.
- **CLV needs ~14 more real-close rows** to resolve a quarter tick (30 total,
  16 now). Week 2 settles 09-18 to 09-22, which should roughly get there. Read
  it against `clv_resolution`; one tick is 3.552% at this ledger's prices.
- **The claimed-edge vs realized-return regression** (flagged cohort mean
  claimed edge 34%, realized ROI -20.9%) still waits on a larger settled book.
  Week 2 is the first chance to grow it since run 11.
- **After 09-21, `PRICING_VERSION` is free to move**, unchanged since run 10.
- **Do not re-raise:** `*/30` capture cadence (run 13), the Odds API (run 2),
  football-data.org (run 3), validating the gate against realized fill quality
  (run 14).
- NFL preseason markets are priced and settled by Kalshi but invisible to
  nflverse; labelled, not fixable.
- **Standing reminder:** 0 live bets. 25 settled shadow bets, 6 wins, ROI
  **-20.87%**, and the number has not moved in five runs. The market beats the
  model on every scoring rule on the bets the model itself chose; CLV reads no
  detectable edge at half-tick precision; the market does not move toward the
  model over the whole tradeable window. **It is still 25 wagers, and that is
  what keeps all of it provisional -- in both directions.**

## Process note

The stored scheduled prompt still carries "do not post, send, change, or
delete anything" and the unfilled `[which data sources?]` placeholder.
CLAUDE.md has overridden the first for repository work since 2026-09-11 and
settled the second since 2026-09-13. Noted once, per CLAUDE.md, and not
escalated.

**Escalations: none.** No charge and no signup form is outstanding.
