# Scheduled run 15 -- the biggest edges live on a book that has not opened yet, and the rest of them never decay

_2026-09-17, 06:01-07:5xZ._

## Headline

**The EPL primary data source went dark, and the run continued anyway** --
football-data.co.uk now answers every request, on every path, with a redirect
to `http://127.0.0.1/`. It is an upstream misconfiguration, not a rate limit
and not something a key would fix. It took out `refresh-history` mid-run and
`recommend --sports soccer` entirely. Both now degrade instead of raising, and
the degradation is gated on an independent source rather than on a clock.

**Run 14's designated next question got answered, and the answer is in two
halves that point the same way:**

- **32 of 32 NFL contracts whose listing we actually watched opened OUTSIDE
  the liquidity gate** -- median spread 22.5c, median volume 0, median ask size
  4 -- and took a median of **568 minutes** to produce a quote the gate would
  accept. Across that stub the ask moves a median 7c and the claimed edge moves
  a median **12.0pp**. That is where the project's spectacular early-board
  "edges" come from, and the gate already refuses all of them.
- **Once the book is open, the claimed edge does not decay at all.** NFL
  flagged sides: **34.1% -> 33.2%**, mean change **-0.84pp, CI [-8.4, +5.0]**.
  EPL: **24.3% -> 22.5%**, **-1.81pp, CI [-5.8, +2.2]**. The market does not
  come toward the model over the whole tradeable window.

**The second half is the one that matters, and it kills a comfortable story.**
The winner's curse is not a thin-book artifact. The book is tight, deep and
unmoving, and the model disagrees with it by a third of its own price the whole
way to kickoff.

**A third finding, found by reading a diff:** `bets/ledger.csv` was being read
with pandas' default float parser, so every `recommend` and every `settle`
silently perturbed cells nothing had touched. Run 11 fixed exactly this for the
game tables and the odds snapshots. The file the project is actually about was
still on the broken reader.

**No bets settled.** NFL week 2 opens 09-18T00:15Z, not 09-17 as run 14
recorded. Ledger unchanged from runs 11-14: 25 settled, 6 wins, **24.0%**, ROI
**-20.87%**. Three new shadow rows. `live_enabled` stays `false` everywhere.

Tests **266 -> 286**.

## Finding 1: the only EPL source this project has is down

Every path on the host, tried repeatedly and with a browser user-agent:

```
GET https://www.football-data.co.uk/mmz4281/2627/E0.csv
  -> 302  location: https://football-data.co.uk/mmz4281/2627/E0.csv
GET https://football-data.co.uk/mmz4281/2627/E0.csv
  -> 302  location: http://127.0.0.1/mmz4281/2627/E0.csv
```

`www` redirects to the apex; the apex redirects everything to the loopback.
The site root, `englandm.php` and every season's CSV do the same, so this is
the whole host, not our file. `pd.read_csv` follows the second hop, tries a
plain-HTTP connection and gets `Connection refused`.

### What broke, and what that says about the pipeline rather than the source

Two failures, and neither was really about football-data.co.uk:

1. **`refresh-history` raised inside its EPL step.** The ESPN refresh and the
   SQLite rebuild come after it in the same function, so they never ran. One
   dead source stopped the refresh of three live ones. The ESPN block already
   had a try/except -- written in an earlier run for exactly this reason --
   and the two primary fetches above it did not.
2. **`recommend --sports soccer` raised before pricing anything**, because
   `_load_games_for` fetched the rating seasons live on *every* invocation
   while a committed table of exactly those seasons sat in `data/processed/`.

Both are now fault-tolerant, each upstream independently, and `refresh-history`
still exits non-zero at the end with the list of sources it could not refresh.
A partial refresh that exits 0 is the failure mode being avoided: the tables on
disk look fine and nobody is told one of them is yesterday's.

### The fallback is gated on games, not on a clock

The committed table is the obvious fallback and it is also the dangerous one.
Pricing today's board from a table missing last night's results is how a model
quietly prices a league whose state it no longer knows, and in the output it
looks exactly like a normal run.

So `ingest/sources.py` allows the fallback and never lets it be silent, and the
gate is:

> a committed table is usable **iff** it is missing no game ESPN reports as
> already played.

`espn.audit_against_primary`'s `only_espn` is that count -- already written,
already tested, and from a source that carries no odds, so it can never decide
a price, only say whether the table about to set one has fallen behind reality.

**A staleness check on the table's own timestamp would have passed today and
would still be the wrong instrument.** The EPL table was 15 hours old and
completely current, because no EPL fixture falls between 09-14 and 09-19. Age
is not the question; missing games are. Today: **ESPN gap 0 of 40 played**, so
EPL was priced, from a table nothing independent could fault.

A related trap, caught while reporting it: `ingested_at` in these tables is
**not a fetch time**. `write_processed` holds back rows that came back
unchanged so the git diff stays readable, so a row re-fetched today keeps its
old stamp -- `espn_epl_games` reads `2026-09-15` on a table refreshed at 06:08
today. The provenance dict now calls it `table_last_changed_at`, which is what
it is, and nothing consults it for the usable/not-usable decision.

### What this does NOT license

**No new source was added and none is being asked for.** CLAUDE.md's bar is
free, no human-created account, and verified against something already held.
ESPN already clears that bar and is already here; it just carries no odds, so
it cannot replace football-data.co.uk for the closing-odds columns the
backtests train on. Those columns are historical and already committed, so
nothing is currently blocked.

**The deadline is 2026-09-19.** That is the next EPL fixture. If the source is
still down when those results land, ESPN will report played games the committed
table lacks, the gate above will refuse to price EPL, and `recommend --sports
soccer` will skip the league -- correctly, and loudly. That is a working
failure, not a silent one, but it is a failure. If it happens, the next run's
job is to wire EPL results from ESPN into the rating path (odds columns stay
missing for new fixtures, which the live model does not use) or to find another
free mirror of the football-data files. **Neither needs anybody's permission
and neither is an escalation.**

**Escalations: none.** No charge and no signup form is outstanding. This is an
outage, reported as a finding.

## Finding 2: a contract's first quotes are not a market

This is the first half of run 14's open item -- "the gate rejects early boards;
the model's largest claimed edges appear on early boards; neither has been
expressed as a number against the other".

`betting/edge_decay.py` re-prices **every capture of every contract** in the
committed snapshot history through the production path, with the liquidity gate
switched off so rejected quotes get priced too, and with `now` set to the
capture time so the in-play gate applies as of then. The model at each capture
is built **only from games that had finished before it** -- this project has
shipped three lookahead bugs (runs 2, 3, 6) and an as-of model is the whole
reason this is a module and not a script.

### The tape that explains it

`KXNFLGAME-26SEP27KCMIA-MIA`, from listing:

| capture | bid | ask | spread | ask size | volume |
|---|---|---|---|---|---|
| 09-15 16:36Z | 0.29 | 0.67 | **0.38** | 20 | 106 |
| 09-15 17:02Z | 0.23 | 0.59 | 0.36 | 20 | 106 |
| 09-15 17:33Z | 0.17 | 0.32 | 0.15 | 20 | 300 |
| 09-15 18:02Z | 0.19 | 0.21 | **0.02** | 12 | 300 |
| ... 36 hours ... | | | | | |
| 09-17 06:08Z | 0.17 | 0.18 | 0.01 | 620 | 908 |

The "48-cent price move" in the first 86 minutes is not a market moving. It is
a book opening.

### Measured across every listing we watched

Restricted to contracts that appeared **after** capture began, because a
contract already on the board has an unobserved opening and counting it would
report the cron's start date as a market event:

| | NFL | EPL |
|---|---|---|
| listings observed | **32** | **0** |
| opened outside the liquidity gate | **32 (100%)** | -- |
| median opening spread | 0.225 | -- |
| median opening volume / ask size | 0 / 4 | -- |
| median minutes to first gate-passing quote | **568** | -- |
| mean minutes | 842 | -- |
| median \|ask move\| across the stub | 0.070 | -- |
| median \|claimed-edge move\| across the stub | **12.0pp** | -- |
| never passed the gate at all | 12 of 32 | -- |

**EPL contributes nothing here and the table says so.** All 60 EPL contracts in
the store were already listed on 09-10, so this is an NFL-only measurement on
32 contracts, and it should not be quoted as a fact about Kalshi.

For scale: run 13 measured the mean absolute **net** ask move over the *entire*
rest of the pre-kickoff window at 0.0157 for NFL. The median move across the
opening stub alone is 0.070 -- about four and a half times as much, in a median
of nine and a half hours.

### The number this replaces

**The first draft of this module anchored on each contract's first capture and
reported that claimed edge GROWS by +20.0pp on gate-rejected contracts, cluster
CI [+11.6, +31.6].** That interval excludes zero and the number is arithmetically
correct. It is also entirely the table above: a stub quote is wide on *both*
sides, so both sides price as negative edge, and when the book opens the edge
"grows". Nothing was published from that pass.

The fix is the anchor, not the arithmetic. Everything below starts at a
contract's **first gate-passing quote** -- the first moment the recommender
could actually have bet it.

## Finding 3: once the book opens, the claimed edge does not decay

Anchored at the first tradeable quote, compared with the last pre-kickoff
capture, on contracts with two such quotes at least 24h apart.

NFL: 73 contracts / 41 events, median first quote T-242h, median span 77h.
EPL: 55 contracts / 20 events, median first quote T-100h, median span 68h.

**The flagged cohort** -- the sides the recommender would have bet, which is
what every "biggest edge on the board" claim in this journal has ever been
about:

| | NFL | EPL |
|---|---|---|
| contracts / events | 29 / 29 | 22 / 18 |
| mean claimed edge, first tradeable quote | **34.1%** | **24.3%** |
| mean claimed edge, last pre-kickoff quote | **33.2%** | **22.5%** |
| mean change | **-0.84pp** | **-1.81pp** |
| 95% CI (cluster bootstrap on events) | **[-8.39, +4.96]** | **[-5.83, +2.24]** |
| market leg | -0.09pp | -1.76pp |
| model leg | -0.18pp | +0.16pp |

**Both intervals straddle zero, and both are narrow enough to exclude the
decay that would matter.** A +34% claimed edge at T-242h is a +33% claimed edge
at the last capture before kickoff.

The decomposition is there because net change alone would let two opposite
stories look identical. A claimed edge can shrink because the market came to us
(a real mispricing being corrected) or because the model changed its mind when
last week's results landed (its early number having been noise its own later
evidence overwrote). Each leg is computed by freezing the other. **Neither leg
moves.** The ask is unchanged on 22% of NFL contracts and the model's
probability is unchanged on 55% of them.

### The cohort that actually reached kickoff

45 of 73 NFL contracts and 46 of 55 EPL ones are week-3 and week-4 games that
have not been played, so their "last quote" is just today's price over a
truncated window. Reported separately, because pooling them would let unplayed
games speak about what happens at kickoff:

| cohort | contracts (flagged) | median last capture | edge first | edge last | change |
|---|---|---|---|---|---|
| NFL, window complete | 12 | T-0.42h | 24.2% | 23.8% | **-0.37pp** |
| NFL, truncated | 17 | T-85.9h | 41.0% | 39.9% | -1.18pp |
| EPL, window complete | 4 | T-0.23h | 19.2% | 22.8% | +3.66pp |
| EPL, truncated | 18 | T-45.1h | 25.5% | 22.5% | -3.03pp |

**The NFL complete-window cohort is 12 contracts** and no interval is reported
on it. It says the same thing the full sample does: a 24% claimed edge is still
a 24% claimed edge twenty-five minutes before kickoff. The EPL complete cohort
is **4 contracts from 3 events** and is in the table only so its absence cannot
be mistaken for agreement.

### What this joins up

Run 14 closed with: "the gate rejects early boards; the model's largest claimed
edges appear on early boards; those two facts have not been joined up with a
number." They are now, and the join produces a positive and a negative:

- **Positive.** The gate's single most valuable action is not filtering bad
  quotes in general. It is refusing to price a contract during the hours
  between listing and the book opening, which is where essentially all of the
  price movement in this project's captured history happens. That is a much
  stronger version of run 14's Finding 1 -- measured on the price rather than
  on a tick -- and it is consistent with run 14's NFL/EPL split, since the EPL
  board never listed a new contract in our window.
- **Negative, and it is the important one.** The comfortable reading of the
  winner's curse was that the model's monster edges are artifacts of thin
  books. **They are not.** The gate already removes the thin-book period. What
  is left is a tight, deep, unmoving book that the model disagrees with by a
  third of its own price for ten days, and today's largest claimed edge --
  MIA at +163% against a 1-cent book with 620 of size and 908 of volume -- is
  the clean case.

This does **not** license any change. It is a measurement of disagreement, not
of who is right: the market never coming to the model is only evidence against
the model when combined with the outcomes, and those say 25 settled bets, 6
wins, ROI -20.87%, and a CLV reading of no detectable edge at half-tick
precision. **That combination is what makes the honest null the leading
hypothesis, and this run strengthens it.** `PRICING_VERSION` is untouched;
nothing in the model or the gate was changed on the strength of any of it.

## Finding 4: the ledger was being altered by the act of reading it

Found by reading today's own `git diff`. One row changed that no code had
touched:

```
-...,0.09687997808317032,pending,...
+...,0.0968799780831703,pending,...
```

`ledger._load` used `pd.read_csv` without `float_precision="round_trip"`.
pandas' default float parser is fast but not correctly rounded, so a load/save
cycle perturbs values in the last bit. The ledger is rewritten by `recommend`
and by `settle`, i.e. at least twice per run, forever.

**This is the same defect run 11 diagnosed and fixed for `data/processed/` and
`data/snapshots/`** -- where it was drifting 585 of 2,499 NFL rows on every
refresh -- and `storage/snapshots.py` carries a long note about why it matters
at 1e-16. That note applies with more force to `bets/ledger.csv` than to
anything it was written about:

1. It makes `git diff` lie about the bet record. A row that changed because a
   bet *settled* is supposed to stand out next to rows that did not change.
   Today two cells of noise sat in a four-line diff; at 300 rows it is the
   review problem run 11 described.
2. The ledger is the evidence. Altering it as a side effect of reading it is
   the one thing this project cannot do.

Only 2 of 123 rows drifted today, and the smallness is not the reassuring part
-- which cells drift depends on the exact decimal expansions the file happens
to hold, so a synthetic fixture would have passed while the real file failed.
`test_ledger_round_trip.py` therefore asserts on the **committed file**: it must
be byte-identical after a load/save cycle. It is now. The second test pins the
*diagnosis* -- that the default parser is what breaks it -- so that if a future
pandas fixes its parser, the note in `_load` gets reconsidered rather than
quietly guarding nothing.

**This is the fifteenth instance of this project's recurring failure, a value
that is not what the surrounding code assumed, and the second consecutive one
that is arithmetic rather than semantic.** It is also the second time this
exact defect has been found in this repository, which is the more useful thing
to record: run 11 fixed it where it was noticed instead of where it lived.

## Bets

**Nothing settled.** 28 pending at the start, 0 resolved, 0 CLV filled, 0
backfilled. Run 14 recorded NFL week 2 as opening 09-17T00:15Z; ESPN's schedule
puts the first game at **09-18T00:15Z** (BUF vs DET), so the first pending row
settles tomorrow, not today. Nothing depended on the wrong date -- `settle` asks
Kalshi, not the calendar -- but it is corrected here.

**Three new rows logged**, all `shadow`, out of 23 flagged recommendations:

| matchup | side | model | fair | edge | after fee | kickoff |
|---|---|---|---|---|---|---|
| BAL @ DAL | home | 0.500 | 0.397 | +25.1% | +20.1% | 2026-09-27T20:25Z |
| ATL @ GB | away | 0.376 | 0.270 | +34.2% | +27.8% | 2026-09-25T00:15Z |
| Crystal Palace @ Leeds | away | 0.275 | 0.202 | +31.0% | +24.2% | 2026-09-20T13:00Z |

The rest were duplicates of open rows: NFL 16 flagged of 48 fillable (33.3%),
EPL 7 of 27 (25.9%), `skipped_duplicate` 14 and 6. `illiquid_skipped` 16 NFL
and 3 EPL, `in_play_skipped: 0`, `superseded_voided: 0`.

**The largest claimed edge on the board is MIA @ SF away at +163.3%** (model
0.316, fair 0.114). It was not logged -- it is a duplicate of an open row -- and
it is the exact case Finding 3 is about: a 1-cent book with real size, priced
three times too high by the model, for the ninth consecutive run.

Ledger after this run:

| | run 14 | run 15 |
|---|---|---|
| settled | 25 | 25 |
| wins | 6 | 6 |
| pending | 28 | **31** |
| void | 67 | 67 |
| win rate | 24.00% | 24.00% |
| ROI | -20.87% | -20.87% |
| mean CLV (real close) | -1.14% (n=16), 0.38 ticks | unchanged, n=16 |

Integrity: **56 non-void rows = 56 distinct `bet_id` = 56 distinct
(game, selection, market).** Every row `shadow`.

**The pre-registered cohort was again not re-scored**, for the fourth run
running. Run 11 fixed the honest read at 36 wagers on 09-21; nothing settled
today. **11 wagers still to kick off, the first at 09-18T00:15Z.**

## Regression checks

All four canonical numbers reproduce digit-for-digit, from the committed
tables, on a container that re-resolved every dependency from scratch:

| | run 15 | runs 5-14 | match |
|---|---|---|---|
| NFL log-loss | 0.6517617405253826 | 0.6517617405253826 | digit-for-digit |
| NFL ROI | -8.208908995992267% | -8.208908995992267% | digit-for-digit |
| NFL n_games / n_bets | 1942 / 1625 | 1942 / 1625 | exact |
| EPL 2425 holdout ROI | -5.11513157894739% | -5.11513157894739% | digit-for-digit |

`espn-audit` clean: NFL 16/16 scores and kickoffs agreed, EPL 40/40, zero
disagreements. `only_espn: 1` on soccer, which is **not** a gap: ESPN's `dates`
parameter walks whole months, so the fetch returns Brentford v Chelsea on 09-18,
a fixture nobody has played. Checked rather than assumed, because that counter
is now load-bearing for the fallback gate in Finding 1.

`verify-settlements` clean: NFL 32/32, soccer 120/120, `unmatched_in_coverage: 0`,
94 NFL unmatched all out-of-coverage (preseason).

Tests 266 -> 286: seven for `ingest/sources` (the live path, the usable and
not-usable fallbacks, the unverifiable fallback that must not read as verified,
the season filter on the fallback, and the old-but-complete table), ten for
`edge_decay` (the anchor, the one-tradeable-quote and short-span exclusions,
each leg of the decomposition in isolation and together, the strict as-of
boundary, the truncated-window flag, the listing-vs-already-listed distinction,
and the underpowered guard), two for the ledger round-trip.

## Data sources

| Source | Status |
|---|---|
| nflverse | Live. 2,499 games, 2,243 played. Week 2 lines moving; 18 rows revised. |
| **football-data.co.uk** | **DOWN** since at least 06:03Z. Redirect loop to `http://127.0.0.1/` on every path. Committed table used, ESPN-verified complete. |
| Kalshi REST | Live. 48 NFL + 27 EPL contracts. |
| ESPN scoreboard | Live. NFL 65 rows / 16 played, EPL 50 / 40. |

Capture cron healthy: snapshots every ~30 minutes, most recent commit 04:36Z,
~85 minutes before this run started.

## Open questions / next steps

- **football-data.co.uk, by 2026-09-19.** If it is still down when EPL results
  land, the ESPN gate will correctly refuse to price EPL. Fixing that is the
  next run's first job: wire EPL results from ESPN into the rating path, or
  find another free mirror of the football-data files. Not an escalation.
- **Run 14 asked run 15 for "a model idea with a stated reason to expect a
  different outcome, or say plainly that it has none." This run has none, and
  says so.** Finding 3 is a reason to expect the ideas already tried to keep
  failing: the market is not moving toward this model on a liquid book over ten
  days, at either league, in any cohort. Runs 11 and 12 established that the
  model cannot be recalibrated into a winner and that the free columns do not
  hold the missing information. Nothing this run found narrows where a better
  idea would come from. **Three consecutive runs of apparatus-only work is now
  worth saying plainly rather than noting.**
- **What Finding 3 does suggest, and it is not a model idea:** the flagged
  cohort's mean claimed edge is 34% and its realized ROI is -20.9%. The gap
  between "claimed edge" and "realized return" is the project's actual subject
  and has never been regressed as such. That is measurable with what is already
  committed once the settled book is larger.
- **The opening-book measurement is NFL-only, on 32 contracts.** EPL listed
  nothing new during the capture window. Do not quote it as a fact about the
  venue until an EPL listing has been watched.
- **CLV needs ~14 more real-close rows to resolve a quarter tick** (30 total,
  16 now). Week 2 settles 09-18 to 09-22. Read it against `clv_resolution`,
  never alone; one tick is ~3.55% at this ledger's prices.
- **Score the pre-registered cohort at 36 on 09-21 and treat that as the read.**
  Runs 12-15 did not re-score the partial cohort.
- **After 09-21, `PRICING_VERSION` is free to move**, unchanged since run 10.
- Nothing in `pyproject` is pinned exactly; `test_benchmarks.py` catches the
  consequences rather than preventing them. pandas resolved to 3.0.5 again.
- **Do not re-raise:** `*/30` capture cadence (run 13 closed it), the Odds API
  (run 2), football-data.org (run 3), validating the gate "against realized
  fill quality" (run 14 -- not measurable in a paper-trading project).
- NFL preseason markets are priced and settled by Kalshi but invisible to
  nflverse; labelled, not fixable.
- **Standing reminder:** 0 live bets. 25 settled shadow bets, 6 wins, ROI
  **-20.87%**. The market beats the model on every scoring rule on the bets the
  model itself chose; the model ranks games significantly worse than the closing
  line; the free information meant to close that gap made it wider; CLV reads no
  detectable edge at half-tick precision; and the market now demonstrably does
  not move toward the model over the entire tradeable window. **It is still 25
  wagers, and that is the number that keeps all of this provisional.**

## Process note

The stored scheduled prompt still carries "do not post, send, change, or
delete anything" and the unfilled `[which data sources?]` placeholder.
CLAUDE.md has overridden the first for repository work since 2026-09-11 and
settled the second since 2026-09-13. Noted once, per CLAUDE.md, and not
escalated.
