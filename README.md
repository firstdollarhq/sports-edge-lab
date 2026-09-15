# sports-edge-lab

A research project testing predictive sports models against real market odds.
**Paper trading only** — no real money moves through this repo. The goal is
to find a real, validated edge, not to confirm a bias. See `journal/` for an
honest, dated log of what was tried and what happened.

## Status (2026-09-15, scheduled run #12)

- **0 live bets. 25 settled shadow bets (6 wins), 24 pending, 67 void.**
  Headline win rate **24.0%**, ROI **-20.87%**. Still 25 wagers; it settles
  nothing on its own.
- **The free information Elo cannot see makes the ranking worse, not better —
  so run 11's proposed direction is now itself a rejected change.** nflverse
  ships rest, short weeks, divisional games, neutral sites, roof, weather and
  starting-QB ids, and the ingest was discarding all of it. Carried, fit
  walk-forward as a logistic on `[elo_diff + context]`, and scored on AUC over
  1,408 games (2020-2024), every tier ranks **below** an elo-only control:
  schedule **-0.0111** [-0.017, -0.005], weather **-0.0126** [-0.020, -0.006],
  qb -0.0071 [-0.017, +0.003]. None approaches the market (0.7288). Sweeping
  the L2 penalty over 15 (tier, C) settings finds **no setting where context
  beats the control** — the best is qb at C=0.1, -0.0045 with a CI straddling
  zero. **Nothing adopted.** `cli context-report --sweep-regularization`.
  - The coefficients are *sensible* — `neutral_site` lands at **-0.4534**,
    correctly undoing most of the flat +55 Elo hands a team that is not home.
    It applies to 54 of 2,499 games, so being right about 2.2% of the sample
    does not pay for the variance added to 100% of it.
  - Two tiers **improve log-loss while ranking worse**. That is exactly the
    trap run 11's AUC bound exists to catch, and it would have read as an
    improvement under every metric this project used before run 11.
- **A per-season refit is not a monotone transform, and the control caught
  it.** A logistic on `elo_diff` alone must reproduce baseline Elo's AUC
  exactly; pooled it did not (0.68389 vs 0.68532). Cause: the model refits each
  season, so the window is five *different* monotone transforms. Per season the
  control ties at **exactly 0.0, all five**. So the control is asserted per
  season, and the yardstick for the features is the elo-only tier rather than
  raw Elo — otherwise the refit effect (-0.0014) would have been credited to
  the features and made the result look better than it is. Run 11's bound is
  untouched: it concerns a single fixed transform, and this effect is two
  orders of magnitude short of the -0.046 gap to the market.
- **The NFL model's problem is discrimination, not calibration — which rules
  out every recalibration-shaped change at once.** Over all 1,942 priced games
  in the canonical window, model AUC is **0.678** against the market's
  **0.724**; paired bootstrap gap **-0.046**, 95% CI **[-0.064, -0.030]**, and
  the model ranks better in **0 of 5,000** resamples. AUC is invariant under
  any monotone transform, so no threshold move, no shrinkage, no Platt or
  isotonic fit, no fee-inclusive edge can close it — none of them reorder
  anything. The Murphy decomposition agrees: the model's deficit is mostly
  **resolution** (0.0241 vs 0.0372), not reliability (0.0055 vs 0.0005). And
  an *oracle* recalibration — isotonic fit on the very outcomes it is scored
  on — still only reaches log-loss **0.635** against the market's **0.610**.
  This is the answer to run 10's closing question, and it retires a whole
  family of proposals. `cli discrimination-report`.
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
- **CLV is a function of reference staleness, not of skill — and not of the
  league either.** Run 9 split mean CLV by leg (NFL -1.03% on a real close,
  EPL +3.00% on a stale one). Run 10 split it by the thing actually doing the
  work, the **reference lag**, and the effect holds *within* the EPL leg as
  well as between leagues:

  | reference | n | mean CLV | pos / zero / neg |
  |---|---|---|---|
  | real close (≤1h) | 14 | **-1.41%** | 2 / 8 / 4 |
  | stale (>1h) | 9 | **+4.04%** | 5 / 4 / **0** |

  The 2 EPL wagers that *do* have a real close read **-3.19%**; the 8 stale
  ones read +4.55%. Every positive reading this project has published came
  from a reference that was not a close, and the stale cohort's +4.04% is
  *exactly* run 8's old headline — which is what confirms the decomposition.
  The lag is now stored per row (`clv_reference_lag_h`) and `ledger-summary`
  reports the two cohorts apart, so the blended average can no longer be
  quoted as a measurement. **12 of 23 readings are exactly 0.00%**, and CLV
  does not separate winners (+0.01%) from losers (+0.98%) in this sample.
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
- **150 model configurations backtested, plus 15 context-feature fits in run
  12. None beat the market.** Nothing adopted, `live_enabled` is `false`
  everywhere.
- **EPL's +8.27% ROI is retired.** Re-run with each season as holdout it is
  1 of 6 positive; pooled **-8.30%**, sd 9.33pp.
- **Twelve bugs of one shape so far**, all a value that was not what the
  surrounding code assumed -- most recently the ledger counting every bet
  twice (run 7) and three caught inside run 8's own new code. See
  "Known-bad numbers" below. **The tally stays at 12 after run 12**: the
  pooled-control discrepancy it found was caught by a control written to catch
  it, before any number rested on it, which is the system working rather than
  a thirteenth failure of it.
- **Next pre-registration, written before the games:** the 13 still-open
  pre-registered wagers (12 NFL, 1 EPL) settling through 2026-09-21 --
  claimed **5.74**, selection-corrected **4.05**, market-implied **4.72**.

## Why these data sources

| Need | Source | Cost | Notes |
|---|---|---|---|
| NFL schedules, scores, closing lines (historical) | [nflverse](https://github.com/nflverse/nfl_data_py) | Free, no key | Ships actual closing moneyline/spread/total per game. Also ships the pre-kickoff context run 12 tested and rejected (rest, divisional, neutral site, roof, surface, temp, wind, starting QB) — carried since run 12, **never read by Elo** |
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
                features.py (pre-kickoff context: rest/venue/weather/QB — TESTED
                             AND REJECTED, run 12; kept as the evidence)
  backtest/     engine.py (walk-forward backtest, no lookahead), metrics.py
                sweep.py (parameter grid vs the closing line)
                selection.py (winner's-curse audit + model-vs-market blend)
                discrimination.py (calibration or ranking? bounds recalibration)
                context.py (does non-Elo information rank better? + L2 sweep)
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
python -m sportsedge.cli backtest-nfl       # canonical window, 2018-2024
python -m sportsedge.cli backtest-soccer    # canonical window, 1920-2425
python -m sportsedge.cli selection-audit    # is the model wrong, or the bet rule?
python -m sportsedge.cli discrimination-report   # is it calibration, or ranking?
```

Both backtests now **default** to the canonical window rather than requiring
`--seasons`. The windows used to live only in journal prose, and the example in
`cli.py`'s docstring was a different one: 2020-2024 returns -9.84% and
2223-2425 returns -8.46%, both plausible-looking numbers that are not the
pinned ones. `tests/test_benchmarks.py` pins all four exactly, so a real drift
fails CI instead of being spotted by eye. Pass `--seasons` only to ask a
different question, and state the window whenever you quote the answer — the
EPL holdout ROI moves about nine points on that choice alone.

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

The threshold still tests `edge_pct`. That began as two blockers; run 10
cleared the first, and then found the change is not worth making anyway.

1. ~~**The rate is unverified.**~~ **Verified 2026-09-14 at exactly 0.07.** No
   endpoint states the coefficient, but the docs site mirrors every page as
   markdown (`docs.kalshi.com/<path>.md`, indexed in `/llms.txt`), and
   `getting_started/fee_rounding.md` works an example carrying both sides of
   the equation: a buy with `-$0.055000` signed revenue and a model fee of
   `$0.00363825`. One contract at 5.5c inverts to
   `0.00363825 / (0.055 × 0.945) = 0.07` exactly, and the other whole-contract
   splits of that revenue give ragged rates (0.0669, 0.0665, 0.0662), so the
   reading is unambiguous. Pinned by `kalshi_engine.FEE_RATE_FIXTURE` and
   re-derived on every test run.
2. **It would break a pre-registered prediction**, still, until 2026-09-21.
   13 wagers from run 4's cohort (12 NFL, 1 EPL) are open, and run 9
   pre-registered the same 13 again. A `PRICING_VERSION` bump re-prices open
   bets, so `void_superseded_rows` would void them a week before they resolve.
3. **And the change is rejected on the evidence.** Backtested at the simulated
   venue, selecting on the after-fee edge and settling at the same price:

   | leg | p2 (threshold pre-fee) | p3 (threshold post-fee) | |
   |---|---|---|---|
   | NFL | **-10.09%** (n=1724) | **-11.48%** (n=1556) | worse by 1.39pp |
   | EPL | **-11.07%** (n=373) | **-8.99%** (n=283) | better by 2.08pp |

   The legs disagree in sign at every fee rate from 0.01 to 0.10, and neither
   comes near beating the closing line — which is what the deployment gate
   asks for, not an improvement on p2. The mechanism is the reason to care:
   the NFL bets p3 removes are the **low**-claimed-edge ones (median +4.72%
   pre-fee, median price 47c), and run 9 measured the low-edge half of the
   settled book as the half whose claimed edge is *least* overstated. A
   fee-inclusive minimum is still a minimum on claimed edge, so it selects
   harder for the model's own overstatement: run 4's selection gap sharpened,
   not repaired.

The backfill is therefore strictly derived (`market_odds_decimal` is 1/ask by
construction); no price, stake, status, selection or `pricing_version` moves.
`test_backfill_after_fee_is_derived_not_a_repricing` asserts that.
`test_fee_does_not_change_which_bets_are_flagged` and
`test_threshold_still_tests_the_pre_fee_edge` pin the decision above: a side
whose edge clears the threshold before the fee but not after it must still be
flagged. They pin the behaviour, not the opinion — a future run with a better
reason may still move it, as a `p3` bump, after clearing the deployment gate
in backtest.

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

- **The honest null is now the leading hypothesis, and it is stated as one.**
  Twelve runs, 150+ configurations, a hard AUC bound retiring every
  recalibration-shaped change (run 11), and a negative result on the obvious
  non-Elo information (run 12). Nothing found so far suggests a public-data
  team-strength model beats this closing line. That is a finding, not a
  failure — but adding further features without a reason to expect a different
  outcome would be.
- **What would actually be a different bet:** information the closing line
  prices *late* or prices *badly*, not information it prices perfectly. Every
  feature run 12 tested is on the market's screen too, and the line-movement
  work says the final hour barely moves (26 contracts, none moved 2c), which
  is itself evidence the market is not leaving anything on the table here.
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
- **CLV may not be a usable signal at this venue at all, and every positive
  reading so far came from a stale reference.** Run 10 split the 23 settled
  rows by reference lag rather than by league: **≤1h reference, n=14, mean
  -1.41%; >1h reference, n=9, mean +4.04% with not one negative reading.** The
  split holds *within* the EPL leg (2 real closes read -3.19%, 8 stale read
  +4.55%), so it is a property of the measurement, not the sport. **12 of 23
  readings are exactly 0.00%** and CLV does not separate winners (+0.01%) from
  losers (+0.98%). The lag is now stored per row and reported apart, so the
  blended average cannot be quoted as a measurement. Given a market whose
  entire observed movement inside two hours is one cent, the open question is
  no longer "is the CLV number believable" but "can CLV measure anything
  here". **Decide it once the real-close cohort is large enough to have a
  usable standard error — not before.**
- ~~Kalshi's fee coefficient is unread~~ -- **read and verified in run 10 at
  exactly 0.07**, by inverting Kalshi's own worked example rather than finding
  a page that states it. See "The fee is reported, not enforced" above.
  Moving the threshold onto the fee-inclusive number (`p3`) was then
  backtested and **rejected**: it makes NFL worse, the legs disagree in sign,
  and neither clears the deployment gate.
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
