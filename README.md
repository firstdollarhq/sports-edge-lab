# sports-edge-lab

A research project testing predictive sports models against real market odds.
**Paper trading only** — no real money moves through this repo. The goal is
to find a real, validated edge, not to confirm a bias. See `journal/` for an
honest, dated log of what was tried and what happened.

## Status (2026-09-14, scheduled run #9)

- **0 live bets. 23 settled shadow bets (6 wins), 23 pending, 67 void.**
  Headline win rate **26.1%**, ROI **-13.98%**. Still 23 wagers; it settles
  nothing on its own.
- **Run 4's pre-registered prediction has resolved on 23 of 36 wagers, and the
  model's own claim is the hypothesis it falsifies.** NFL week 1 settled
  overnight. Actual **6** wins against **9.45** claimed, **7.22**
  selection-corrected and **7.77** market-implied. The NFL leg is the sharp
  one -- corrected **4.09**, market 4.82, claimed 5.87, **actual 4**. Exact
  Poisson-binomial P(X <= 6) is **0.095** under the model's claim, 0.377
  corrected, 0.287 market. **None of those is a rejection at any conventional
  level**; what the result says is that the observation sits in the tail of
  the model's own claim and comfortably inside the other two. `cli scorecard`.
- **The market beats the model on every scoring rule, on the bets the model
  itself chose.** Model log-loss **0.6535** vs market **0.6030**; Brier 0.2318
  vs 0.2057; model overstatement **+15.0pp** vs the market's +7.7pp.
- **CLV reversed once the reference became real.** Mean CLV falls from run 8's
  **+4.04%** to **+0.72%**, and the split by leg is the point: the 13 NFL
  wagers, measured against a genuine **T-0.42h** close, read **-1.03%**, while
  the 10 EPL wagers on a stale **T-7.75h** reference read +3.00%. Run 8
  published +4.04% together with the reasons not to believe it; this is what
  those reasons looked like when the real number arrived. **12 of 23 readings
  are exactly 0.00%**, and CLV does not separate winners (+0.01%) from losers
  (+0.98%) in this sample.
- **The final hour is measured at last, on 26 contracts, and it barely moves.**
  Against a reference 25 minutes before kickoff: T-1h..T-2h mean |move|
  **0.0038**, median **0.000**, max 0.01, and **not one of 26 contracts moved
  as much as two cents**. **`*/15` capture is therefore rejected**; `*/30`
  stays. Moving the reference from T-8h to T-0.42h shifts the measured price
  by only ~0.6c -- which is *about the size of the entire effect being
  measured*, and is why the pre-cron CLV numbers were misleading rather than
  merely imprecise.
- **The 94 unmatched NFL settled markets are explained and the item is
  closed.** All 94 are **August dates -- preseason**, which nflverse does not
  carry at all (the 2026 table starts 2026-09-09). Never a defect, but it was
  reported in a way that could hide one: a real mapping failure on a covered
  date would have had to move a counter already reading 94. `verify_against_stats`
  now splits `unmatched` into out-of-coverage vs **in-coverage**, using
  per-season windows from the stats table. NFL: 30 checked, **30 agreed**, 94
  out of coverage, **0 in coverage**. Soccer: 117 / 117 / 0 / 0.
  **This is a reporting fix, not a bug fix -- the tally stays at 12.**
- **Within the settled cohort, the bigger the claimed edge, the bigger the
  overstatement.** Split at the median claimed edge (19.4%): the low half
  realized 0.55 wins below its claim, the high half **2.89 below**. That is
  run 4's selection-audit signature appearing in realized results rather than
  backtest -- at n = 11 and 12, a direction and not a measurement.
- **The betting rule, not the rating engine, is the main defect.**
  Unconditionally NFL Elo is roughly calibrated. Conditional on a side being
  *bet* it overstates its win probability by **13.7 points**, in every
  probability bucket; on sides it *passes* it understates by 9.3. That is the
  winner's curse. `cli selection-audit`.
- **Elo carries no information the closing line lacks.** Blending
  `w*model + (1-w)*market` is optimised at **w = 0** for NFL, with log-loss
  monotonically worse in w; EPL lands on w = 0 for 5 of 6 holdout seasons.
- **The model loses at both venues, and the exchange is the dearer one.**
  Moving the NFL sample to Kalshi takes ROI from **-8.21% to -11.48%**. The
  tighter book is worth +2.1pp; the trading fee gives back -5.4pp.
  `cli venue-report`.
- **Why the cheaper venue costs more:** a sportsbook's vig is proportional, so
  its toll is flat at ~3.2% of stake at every price. Kalshi's fee is quadratic
  in notional, so as a fraction of *stake* it is `rate x (1 - price)` -- 3.3%
  on a 70c favourite, **10.6% below 15c**. The bet rule places **88.6% of its
  bets below even money**. NFL ROI is negative at every fee rate **including
  zero** (-6.10%), so the conclusion does not rest on the one coefficient
  Kalshi's API will not expose.
- **The EPL expiration lag is measured, not assumed: exactly 3.00h on 13/13
  contracts.** NFL is 3.00h x 27 and 6.00h x 3 in the same window.
- **Settlements are independently cross-checked and all agree.** 30/30 NFL and
  117/117 soccer, against ESPN's public scoreboard as a third opinion rather
  than Kalshi's own resolution alone. `espn-audit` is read every run, not
  assumed: NFL 15/15 scores and kickoffs, EPL 30/30.
- **150 model configurations backtested. None beat the market.** Nothing
  adopted, `live_enabled` is `false` everywhere.
- **EPL's +8.27% ROI is retired.** Re-run with each season as holdout it is
  1 of 6 positive; pooled **-8.30%**, sd 9.33pp.
- **Twelve bugs of one shape so far**, all a value that was not what the
  surrounding code assumed -- most recently the ledger counting every bet
  twice (run 7) and three caught inside run 8's own new code. See
  "Known-bad numbers" below.
- **Next pre-registration, written before the games:** the 13 still-open
  pre-registered wagers (12 NFL, 1 EPL) settling through 2026-09-21 --
  claimed **5.74**, selection-corrected **4.05**, market-implied **4.72**.

## Why these data sources

| Need | Source | Cost | Notes |
|---|---|---|---|
| NFL schedules, scores, closing lines (historical) | [nflverse](https://github.com/nflverse/nfl_data_py) | Free, no key | Ships actual closing moneyline/spread/total per game |
| Soccer results + closing odds (historical) | [football-data.co.uk](https://www.football-data.co.uk/) | Free, no key | CSV per league/season; uses bookmaker-average (`Avg*`) columns when available |
| **Live market odds (both sports, ongoing)** | **[Kalshi](https://kalshi.com)** public REST API | **Free, no key** | CFTC-regulated exchange; read-only market data needs no auth. Each contract's dollar price *is* the market-implied probability. `KXNFLGAME` / `KXEPLGAME` series. |
| **Settlement cross-check + kickoff times (both sports)** | **[ESPN public scoreboard](https://site.api.espn.com/apis/site/v2/sports/)** | **Free, no key** | Undocumented endpoint behind espn.com's scoreboard. Schedules and results only — **no odds, never feeds the model**. Publishes within minutes of full time, where football-data.co.uk publishes in batches days later. Verified against the primary source: 30/30 scores and 30/30 kickoffs agree (`cli espn-audit`). |

**Rejected, on the merits, and closed** — these are not open asks and should
not be re-raised:

| Source | Status | Why |
|---|---|---|
| [The Odds API](https://theoddsapi.com/) (~$29/mo for NFL+soccer) | **Rejected, run 2** | Kalshi covers live odds for both leagues free, and run 5's venue work showed the two price the same games the same way (corr 0.9955 over 28 games). Paying for a second view of a number we already hold is not worth $29/mo to a project with no validated edge. |
| [football-data.org](https://www.football-data.org/) (free tier, needs a human-created key) | **Rejected, run 3 — as unnecessary, not blocked** | It was wanted only for kickoff times. football-data.co.uk already ships them in a column the ingest was discarding, and ESPN now covers the gap for unpublished fixtures. |

Kalshi was not part of the original plan — it came up mid-build as a
free alternative to a paid odds API, and turned out to cover exactly the two
leagues we're starting with, so it's now the primary live-odds source.

## Architecture

```
src/sportsedge/
  ingest/       nfl_stats.py, soccer_stats.py (historical), kalshi.py (live odds)
                teams.py (Kalshi ticker -> stats-source team resolution)
  models/       elo.py (rating engines), calibration.py (soccer 3-way outcome calibration)
                live.py (current-strength ratings for pricing today's games)
  backtest/     engine.py (walk-forward backtest, no lookahead), metrics.py
                sweep.py (parameter grid vs the closing line)
                selection.py (winner's-curse audit + model-vs-market blend)
  betting/      edge.py (de-vig, EV, Kelly), ledger.py (bets/ledger.csv)
                scorecard.py (settled bets vs model AND market, effective n)
                liquidity.py (is this quote fillable?), recommend.py (model vs market)
                settle.py (resolve bets, compute CLV)
  journal/      entry.py (dated markdown journal entries)
  storage/      db.py + schema.sql (SQLite historical database)
                snapshots.py (committed odds capture — see below)
```

### Odds snapshots are the one irreplaceable asset

`data/snapshots/<sport>/<date>.csv` is deliberately **not** gitignored. Live
odds cannot be reconstructed after the fact, and each session runs in a fresh
container, so these committed CSVs are the only durable record. Closing-line
value depends entirely on having captured a price before kickoff — a missed
snapshot window is permanently missing data.

### Team resolution: the ticker order differs by sport

Kalshi encodes both teams in the event ticker, but **not in the same order**:

- NFL is `AWAY+HOME` — `KXNFLGAME-26SEP21NYGLAR` is NYG *at* the Rams.
- EPL is `HOME+AWAY` — `KXEPLGAME-26SEP06ARSCFC` is Arsenal *hosting* Chelsea.

Both were verified against the stats sources (nflverse, football-data.co.uk)
rather than assumed, and both are pinned by tests. Getting either backwards
inverts every prediction for that sport while leaving aggregate metrics looking
entirely plausible.

### Model approach

- **NFL**: standard Elo (`k=20`, home advantage `+55` rating points), with an
  optional margin-of-victory K-scaling (the well-known 538-style multiplier),
  gated behind a flag so it can be A/B'd in backtest before ever being turned
  on for real recommendations.
- **Soccer**: Elo strength ratings + a **multinomial logistic regression**
  fit on prior-season (elo_diff → H/D/A outcome) pairs to produce calibrated
  3-way probabilities. This was a deliberate choice: rather than hard-code an
  assumed draw-probability formula, the draw/win/loss split is learned from
  real historical outcomes and evaluated out-of-sample (fit on seasons 1–5,
  tested on season 6, walk-forward within each).

### Betting methodology

1. Compute model win probability for each side of a market.
2. De-vig the market's own implied probabilities (two-way for NFL moneyline,
   three-way for soccer 1X2) to get a fair-odds baseline for comparison.
3. Drop any quote that isn't actually fillable (`betting/liquidity.py`: spread,
   resting size, traded volume, extreme prices). On EPL this currently removes
   ~⅓ of contracts — pricing off a stale book manufactures fake edges.
4. `edge_pct = model_prob * decimal_odds - 1`, **priced at the ask**, not the
   mid. The ask is what you'd actually pay; using the mid silently credits the
   model with half the spread on every bet. A paper bet is only logged if edge
   clears **`edge_threshold_pct`** (default 3%, see `config/leagues.yaml`).
5. Stake sizing uses **fractional Kelly** (`kelly_multiplier = 0.25` by
   default) — never full Kelly, which is too volatile for a model with
   uncertain calibration.
6. Every bet, win or loss, goes in `bets/ledger.csv` with model prob, market
   odds, edge, and (once the game closes) closing odds and CLV — closing
   line value is tracked independently of win/loss because it's a better
   short-run signal of whether the model has real skill than win rate alone.

## The deployment gate: shadow vs. live

`live_enabled` in `config/leagues.yaml` is `false` for every league, and stays
false until that league's model **beats the de-vigged closing line
out-of-sample** — not merely improves on an earlier version of itself.

While it's false the recommender still runs, but every row it writes is a
`shadow` bet: recorded as evidence, reported separately, never folded into
headline win rate or ROI. A model that loses to the market and gets deployed
anyway just launders a bias into a bet history.

Flipping that flag is the single decision that turns this from a research log
into a betting record. It should never happen as a side effect of another
change.

## Backtesting discipline

**No model change goes live without being backtested first, and the backtest
result goes in the journal even if it's bad.** The walk-forward backtest
(`src/sportsedge/backtest/engine.py`) only ever uses information available
before each game to make that game's prediction — ratings update strictly
after the prediction is recorded, so there's no lookahead leakage.

Run it yourself:

```bash
pip install -e ".[dev]"
python -m sportsedge.cli backtest-nfl --seasons 2018 2019 2020 2021 2022 2023 2024
python -m sportsedge.cli backtest-soccer --league E0 --seasons 1920 2021 2122 2223 2324 2425
python -m sportsedge.cli selection-audit    # is the model wrong, or the bet rule?
```

`selection-audit` answers the two questions a parameter sweep cannot: whether
the model's errors are concentrated in the sides it chooses to bet (the
winner's curse), and whether any blend weight on the model beats the closing
line it is betting into.

## Setup

```bash
pip install -e ".[dev]"
pytest                                  # 209 tests, no network needed
cp .env.example .env                    # only needed for optional sources
python -m sportsedge.cli kalshi-nfl     # live NFL market snapshot, no key needed
python -m sportsedge.cli kalshi-epl     # live EPL market snapshot, no key needed
python -m sportsedge.cli ingest-nfl --seasons 2023 2024
python -m sportsedge.cli ingest-soccer --league E0 --seasons 2324 2425
python -m sportsedge.cli ledger-summary
```

### The recurring loop

```bash
python -m sportsedge.cli snapshot-odds        # capture live odds (run often!)
python -m sportsedge.cli recommend --dry-run  # see picks without writing
python -m sportsedge.cli recommend            # write to bets/ledger.csv
python -m sportsedge.cli settle               # resolve finished games, fill CLV,
                                              # and recover CLV on rows that
                                              # settled before the stats source
                                              # published their kickoff
python -m sportsedge.cli verify-settlements   # cross-check Kalshi vs stats source
python -m sportsedge.cli scorecard            # model vs market vs reality on
                                              # settled bets, with effective_n
```

`scorecard` is the one that answers the project's actual question. A low win
rate is not evidence against the model -- the rule bets longshots, so a low win
rate is what a *correct* model looks like. The test is whether the model's
probabilities beat the closing line's **on the bets the model chose**, which is
the narrowest place the two disagree and the only place money moves. It reports
both, plus an exact Poisson-binomial P(X <= k) so the reader sees the
expectation next to the tail probability, and counts `effective_n` on distinct
`(contract, selection)` wagers rather than ledger rows.

`recommend` is idempotent per (contract, model version), so re-running on a
schedule won't inflate the bet count.

## Journal discipline

Every meaningful session (data refresh, model change, backtest run, bet
settled) gets a dated entry in `journal/` via `src/sportsedge/journal/entry.py`.
Entries record what worked, what didn't, and why — including negative
results. **A few weeks of results is noise; the point is signal, not
confirming a bias.**

## The venue: we backtest against a sportsbook, we would trade on an exchange

`cli venue-report`. Kalshi's public API serves the current board, not a price
history, so **a Kalshi backtest of 2018-2024 does not exist** and this module
does not claim one. What it does is measure the venue and substitute it into
the historical sample. The measurements are real:

| measured 2026-09-12 | value |
|---|---|
| Kalshi de-vigged mid vs sportsbook de-vigged fair, same 28 games | **corr 0.9955**, mean abs diff 1.26pp |
| Kalshi overround at the ask | +1.04% |
| Sportsbook overround, same games | +4.28% |
| Kalshi half-spread (672 NFL + 540 EPL quotes) | median **0.5c**, flat across every price bucket |

The forecast agreement is what licenses the substitution: if the two venues
price the same games the same way, "the model loses to the de-vigged closing
line" is a statement about both. Every simulated result carries
`simulated_at_venue: True` so it can never be quoted as an observed return.

Both venues run through the **same** walk-forward loop via a `pricer`, not a
second copy of it — the week-ordering bug lived in two copies and had to be
fixed twice. The default path reproduces -8.208908995992267% and log-loss
0.6517617405253826 exactly, pinned bet-for-bet.

## The fee is reported, not enforced

Kalshi's trading fee is the larger of the two execution costs (~4.7% of stake
against the spread's ~1.7%), and `recommend.py` prices at the ask only. So
`edge_pct` overstates every logged edge by roughly the fee — 5.39pp on the
open book. `edge_after_fee_pct` and `fee_assumption` now record it per row.

The threshold still tests `edge_pct`, deliberately, for two reasons:

1. **The rate is unverified.** The API confirms
   `fee_type="quadratic_with_maker_fees"` and `fee_multiplier=1` but exposes
   no coefficient. Enforcing a threshold against a number nobody could read
   writes it into the permanent bet record.
2. **It would break a pre-registered prediction that settles 2026-09-13.**
   Run 4 wrote down, before any game: ~30 wins if the claimed edges are real,
   ~22 if the selection audit is right. The 70 open bets *are* that test.
   Re-pricing them into a different population the day before they resolve
   would dispose of the project's one falsifiable commitment — and in the
   flattering direction, since the bets the fee cuts are the longshots the
   audit predicts will lose.

The backfill is therefore strictly derived (`market_odds_decimal` is 1/ask by
construction); no price, stake, status, selection or `pricing_version` moves.
`test_backfill_after_fee_is_derived_not_a_repricing` asserts that, and
`test_fee_does_not_change_which_bets_are_flagged` is the tripwire for when a
future run moves the threshold as a `p3` bump.

## Known-bad numbers (withdrawn)

**Every bet count published before 2026-09-13 run 7 -- inflated.** Not a wrong
price but a wrong *population*: `ledger.existing_keys` includes
`pricing_version` so that a pricing bump makes an open contract eligible to be
priced again, which is correct, but re-pricing is a replacement and the code
only ever performed the insert. The 2026-09-11 p1 -> p2 bump therefore
duplicated 35 wagers rather than replacing them, and both copies always carried
the same outcome. 75 non-void rows were **40 distinct wagers**; "74 pending"
was 32, and run 4's "70 pre-registered bets" were **36**. Point estimates
survive (each pair scales claimed and realized identically) but every n was
doubled and every CI was narrow by ~sqrt(2). NFL looked handled only because
its model version happened to move at the same time and *that* path did void
its predecessors. Repaired by voiding the superseded half -- newest
`pricing_version` wins, settled duplicates included, since that is where the
double-count reaches win rate and ROI. Audited cell by cell: only `status`,
`result_logged_at` and `notes` moved. Fixed by `ledger.void_superseded_rows`,
run unconditionally inside `recommend`; `tests/test_superseded_void.py`.

**Headline ROI of -13.06% -- superseded, and not by an improvement.** The
de-duplication above takes it to +0.51%. Nothing got better: no bet changed
outcome and no price moved, but the single NFL win went from 1/15 of the book
to 1/8, taking its own ROI contribution from +11.85pp to +22.22pp. EPL alone is
-24.81% on 7 bets. Neither figure is a result at these sample sizes; the point
of recording both is that a correction moved the headline in the flattering
direction and that is exactly when to distrust it.

**Two EPL bets from 2026-09-12 run 6 -- voided.** Liverpool v Fulham and
Chelsea v Hull were priced at 15:11Z against fixtures that kicked off at 14:00Z,
by a pre-game Elo reading in-play quotes. Both sides bet had been marked *down*
by the market (Liverpool 0.66 -> 0.52, Chelsea 0.80 -> 0.41), so the "edge" was
the model's ignorance of the score. Not tradeable prices and not evidence about
the model. An audit of all 76 open rows against the new gate found exactly these
2 failing, so `PRICING_VERSION` deliberately did not move: there were no rows
priced under a superseded rule to invalidate, and bumping it would have re-logged
74 correct rows and disposed of run 4's pre-registered prediction. Gated by
`recommend.partition_in_play`; `tests/test_in_play_gate.py`.

**EPL closing-line value before run 6 -- a number that never existed.** Not a
wrong figure but an empty column: `settle_pending` fills CLV only for rows that
are still `pending`, and football-data.co.uk publishes only completed matches,
days late, so an EPL bet always settled before its kickoff could be resolved and
was never revisited. Recovered by `settle.backfill_clv`, which re-resolves the
kickoff and fills from the committed snapshots — still cutting at true kickoff,
never at Kalshi's expiry. `tests/test_clv_backfill.py`.

**NFL ROI before 2026-09-10 run 2 -- withdrawn.** The ingest stored `week` as a
string, so `"10"` sorted before `"2"` and each season ran 1, 10, 11 ... 18, 19,
2, 20 ... The model predicted week 2 from ratings that had absorbed weeks
10-18. Corrected 2018-2024 vanilla Elo is **-8.21% ROI, not -4.65%**. Log-loss
moved by ~0.001 and is effectively unaffected; all EPL figures are unaffected
and reproduce exactly. No adoption decision changes. Pinned by
`tests/test_backtest_order.py`.

**NFL CLV -- caught before it produced a number.** `commence_time` was
populated from Kalshi's `expected_expiration_time`, which lands **3-6 hours
after kickoff** on every NFL event measured (27 at +3h, 4 at +6h, 0 on time;
Kalshi has no kickoff field). Both closing-price paths treated it as kickoff,
so they could return an **in-play** quote. Demonstrated: `closing_quote_before()`
for SF @ LA returned bid 0.98 / ask 0.99 against an entry of 0.36 -- a CLV of
~+175% produced entirely by the clock, and one that would only ever look good
when the bet won. Nothing published depended on it: no candlestick CLV had been
computed and no snapshot contains an in-play row. Fixed by
`ingest/kickoff.py`; pinned by `tests/test_kickoff.py`.

**EPL's +8.27% ROI -- retired 2026-09-11 run 4.** It was reported on the
2025-26 holdout. Re-run with each season in turn as the holdout, the same
model and protocol give -11.76 / -6.57 / -12.19 / -19.35 / -5.12 / **+8.27**:
1 of 6 positive, pooled **-8.30%**, sd 9.33pp. The figure is the best of six
draws from a distribution centred near -8%, and its season has the
second-worst log-loss in the set. Never presented as validated; now treated as
withdrawn rather than merely uncelebrated.

**The committed tables were rewriting themselves on every read -- fixed, no
number affected.** pandas' default CSV float parser is not correctly rounded:
it read a stored `1.3690036900369003` back as `...005`. 585 of 2,499 NFL rows
drifted in the last bit on every refresh with no upstream change behind them.
Irrelevant at 1e-16, but it made `git diff` useless on the data (six genuine
line moves were invisible among 2,499 "changed" rows) and it meant reading the
irreplaceable snapshot store altered it. All reads now use
`float_precision="round_trip"`; pinned by `tests/test_snapshots.py`.

**Run 1's 102-config sweep is not reproducible.** Its script was never
committed and a faithful reconstruction does not match it (best 0.6396 here vs
0.6459 reported). The no-adoption conclusion is unaffected -- the gap to the
market is far larger than the discrepancy -- but the individual figures should
not be quoted. The sweep now lives in `backtest/sweep.py` with its protocol
documented.

### Where kickoff comes from, and why it matters

Kalshi timestamps are **never** a pre-game cutoff. Kickoff is resolved from the
stats sources only -- nflverse `gameday`+`gametime`, football-data.co.uk
`Date`+`Time` -- via `ingest/kickoff.py`. If a kickoff cannot be resolved, the
bet settles with **no CLV** rather than a guessed one: a missing number is
recoverable, a fabricated one is not.

An in-play price already knows the result. CLV computed against one is not a
noisy skill measurement, it is a restatement of win/loss -- which is why this
mattered more than the ROI bug that preceded it.

"Recoverable" became true rather than aspirational in run 6. Because
football-data.co.uk publishes only completed matches, and days late, an EPL
kickoff is *never* resolvable while the bet is open -- so "no CLV at
settlement" was permanent, not deferred, until `settle.backfill_clv` began
revisiting settled rows once the source catches up.

The same clock cuts the other way at the front of the pipeline:
`recommend.partition_in_play` refuses to *price* a game that has already
started. Where kickoff is unresolvable it infers one from the expiration minus
the sport's largest measured lag (NFL 6h, EPL 3h) -- deliberately the earliest
plausible kickoff, because inferring early costs a bet and inferring late
corrupts the record.

## Open questions / next steps

- **The selection gap is the thing to attack, not the ratings.** A model need
  not beat the market on every game to be bettable -- it needs to be right
  about *which* games it disagrees on. Nothing measured so far suggests Elo
  is. Elo parameter tuning is exhausted (150 configs, none beat the market)
  and retuning cannot reach a selection bias in any case.
- **Do not "fix" the selection gap with a price or edge filter without a real
  test.** Every price bucket in the NFL backtest is ROI-negative (best
  -3.90% at market >=0.50, CI [-18.9, +11.1]). A filter that improves
  backtest ROI here is selecting on noise.
- **Beware the blend sweep's own bait.** It reports +10.19% ROI at w=0.05 --
  on 32 bets, CI [-73.9, +94.3], from a weight log-loss says is worse than
  betting nothing. It regenerates on every run. `summarize_blend` prints such
  rows with their log-loss delta attached for this reason.
- ~~Build the Kalshi-venue backtest~~ -- **done in run 5**
  (`backtest/kalshi_engine.py`). The exchange is the *dearer* venue: NFL ROI
  -8.21% at the sportsbook, -11.48% simulated at Kalshi.
- **Run 4's pre-registered prediction has resolved on 23 of 36 wagers, and it
  resolves against the model.** Actual **6** wins vs 9.45 claimed / 7.22
  selection-corrected / 7.77 market-implied; NFL leg actual **4** vs corrected
  **4.09**. P(X <= 6) = 0.095 under the model's own claim -- in the tail, but
  **not a rejection at any conventional level**, and 23 wagers settles nothing
  by itself. **Next pre-registration, written before the games:** the 13
  still-open wagers (12 NFL, 1 EPL) settling through 2026-09-21 -- claimed
  **5.74**, corrected **4.05**, market **4.72**.
- ~~The settled results are single-sourced~~ -- **cross-checked in run 8** and
  clean since: 30/30 NFL and 117/117 soccer agree against ESPN's public
  scoreboard. ~~NFL shows 94 unmatched settled Kalshi markets~~ -- **explained
  and closed in run 9: all 94 are August dates, i.e. preseason**, which
  nflverse does not carry (the 2026 table starts 2026-09-09). Not a defect,
  but it was reported in a way that could have hidden one, so `unmatched` is
  now split into out-of-coverage vs **in-coverage**; the in-coverage count is
  the one to watch and it is **0** on both sports.
- ~~Snapshot cadence is the binding constraint on CLV~~ -- **fixed 2026-09-13**
  by `.github/workflows/snapshot-odds.yml`, every 30 min, 10:00-04:00 UTC.
  It had looked like an account-level schedule no session could change; it was
  never a schedule problem. **Every CLV computed before that workflow's first
  run is still a T-8h to T-11h number and should be read with that attached.**
- ~~The final hour is unmeasured~~ -- **measured in run 9 on 26 NFL contracts**
  against a reference 25 minutes before kickoff. It barely moves: T-1h..T-2h
  mean |move| **0.0038**, median 0.000, and **not one of 26 contracts moved as
  much as two cents**. **`*/15` is rejected on that evidence; capture stays at
  `*/30`.** The useful number is the gap between buckets: moving the reference
  from T-8h to T-0.42h shifts the measured price only ~0.6c, which is about
  the size of the whole effect being measured -- so the pre-cron CLV readings
  were misleading rather than merely imprecise. Still one high-liquidity NFL
  slate, so "quiet" is the best case, not the typical one.
- **CLV reversed once the reference became real, and may not be a usable
  signal at this venue at all.** Mean CLV fell from run 8's +4.04% to
  **+0.72%** as 23 rows replaced 9. The leg with a genuine T-0.42h close (13
  NFL wagers) reads **-1.03%**; the leg on a stale T-7.75h reference (10 EPL)
  reads +3.00%. **12 of 23 readings are exactly 0.00%** and CLV does not
  separate winners (+0.01%) from losers (+0.98%). Given a market whose entire
  observed movement inside two hours is one cent, the open question is no
  longer "is the CLV number believable" but "can CLV measure anything here".
- ~~Measure the EPL expiry lag rather than assuming 3h~~ -- **measured in run
  8: exactly 3.00h on 13/13 contracts**, via ESPN kickoffs rather than waiting
  for football-data.co.uk. The assumed constant was right. NFL in the same
  window is 3.00h x 27 and 6.00h x 3.
- **Audit the remaining joins and sort keys.** Twelve bugs of the same shape
  now. Every column whose name asserts a semantic (`*_time`, `*_date`,
  `week`, `season`) deserves an explicit check that it holds what the name
  claims -- as does every "last season" that might be in progress, every value
  that might have a *type* other than the one the code assumes, and every
  price that might not be pre-game.
- The two sports fail for *different* reasons: NFL is under-dispersed
  (model sd 0.132 vs market 0.187); EPL's dispersion is already fine.
- ~~Kalshi liquidity filter~~ -- **done** (`betting/liquidity.py`). The 5%
  relative-width gate remains unvalidated against realized fill quality, and
  it has now voided real bets.
- **Needs the owner: nothing.** No charge and no signup form is outstanding.
  Both previously-listed items are closed on the merits (see the rejected-
  sources table above) and should not be re-raised. When a source is needed,
  the run finds one: ESPN was added in run 8 to unblock three items that had
  been waiting on someone else's publication schedule for three runs.

**The venue-agreement join fanned out across seasons -- caught in the run that
introduced it.** The first version matched the Kalshi board to the stats table
on `(home_team, away_team)`. That pair is not unique: the same fixture recurs
every season, so **30 events became 131 rows**, comparing today's contracts
against games from 2020, 2021 and 2024. It reported corr **0.4572** with a
53-point maximum disagreement, and was nearly written up as "the two venues
disagree substantially". Disambiguated by kickoff it is 28 rows at corr
**0.9955**. Fifth bug of this shape; the only reason it was caught is that the
wrong answer happened to look surprising. Pinned by
`test_agreement_join_is_kickoff_disambiguated`.
