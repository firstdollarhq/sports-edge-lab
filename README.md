# sports-edge-lab

A research project testing predictive sports models against real market odds.
**Paper trading only** — no real money moves through this repo. The goal is
to find a real, validated edge, not to confirm a bias. See `journal/` for an
honest, dated log of what was tried and what happened.

## Status (2026-09-12, scheduled run #6)

- **0 live bets. 1 settled shadow bet (a win), 74 pending, 32 void.** The one
  settled bet is SF @ LA at +11.06% edge; its CLV is 0.0% and that number is
  **vacuous** (last snapshot was 7.5h pre-kickoff). One bet is not a win rate.
- **The recommender was pricing a pre-game model against in-play markets.**
  Six EPL fixtures were ~1h into play when run 6 started; it offered Aston
  Villa at **+278%** "edge" (0.44 pre-game, 0.13 live) and logged two such
  rows before the check caught it. The error is signed, not noisy: the market
  marks down whichever side is *currently losing* and the model does not
  follow, so the apparent edge lands on the losing side nearly every time.
  Gated off by `recommend.partition_in_play`; the two rows are voided. NFL was
  spared only because the season had not started — week 1 is 2026-09-13.
- **EPL closing-line value was structurally zero, and silent.** `settle` fills
  CLV once and only looks at *pending* rows, but football-data.co.uk publishes
  only completed matches and publishes them days late, so an EPL bet settles
  from Kalshi before any source can say when it kicked off — and nothing ever
  went back for it. `backfill_clv` now recovers it. 14 EPL bets settling
  tonight would otherwise have lost their CLV permanently, with every price
  needed to compute it already in the snapshots.
- **The model loses at both venues, and the exchange is the dearer one.**
  Every ROI here was model-vs-sportsbook; we would trade on Kalshi. Moving the
  NFL sample to the exchange takes ROI from **-8.21% to -11.48%**. The tighter
  book is worth +2.1pp; the trading fee gives back -5.4pp. See
  `cli venue-report`.
- **Why the cheaper venue costs more:** a sportsbook's vig is proportional, so
  its toll is flat at ~3.2% of stake at every price. Kalshi's fee is quadratic
  in notional, so as a fraction of *stake* it is `rate x (1 - price)` -- 3.3%
  on a 70c favourite, **10.6% below 15c**. The bet rule places **88.6% of its
  bets below even money**. It sits at the expensive end of that curve.
- **The result does not depend on the one number that could not be verified.**
  Kalshi's API gives the fee's shape but not its coefficient, so the rate is a
  parameter and the run reports the range: NFL ROI is negative at every rate
  **including zero** (-6.10%).
- **The betting rule, not the rating engine, is the main defect.**
  Unconditionally NFL Elo is roughly calibrated. Conditional on a side being
  *bet* it overstates its win probability by **13.7 points**, in every
  probability bucket; on sides it *passes* it understates by 9.3. That is the
  winner's curse: the rule stakes money precisely where the model disagrees
  with a more accurate forecast. See `cli selection-audit`.
- **Elo carries no information the closing line lacks.** Blending
  `w*model + (1-w)*market` is optimised at **w = 0** for NFL, with log-loss
  monotonically worse in w; EPL lands on w = 0 for 5 of 6 holdout seasons and
  the 6th improves by 0.0002, CI [-0.0021, +0.0017]. A parameter sweep can
  luck into a good score; this cannot.
- **150 model configurations backtested. None beat the market.** Nothing
  adopted, `live_enabled` is `false` everywhere.
- **EPL's +8.27% ROI is retired.** Re-run with each season as holdout it is
  1 of 6 positive; pooled **-8.30%**, sd 9.33pp. At the exchange the same
  holdout is **-2.85%**.
- **Every logged edge was overstated by roughly the fee** -- 5.39pp on the open
  book. `edge_after_fee_pct` now records it per row. It is reported, not
  enforced: see "The fee is reported, not enforced" below.
- Seven bugs of one shape found so far, all a value that was not what the
  surrounding code assumed -- most recently a quote that was not a pre-game
  price, and a sort key that was `str` and `int64` at once. The seventh changed
  no published number and is flagged as such rather than padding the count.
  See "Known-bad numbers" below.

## Why these data sources

| Need | Source | Cost | Notes |
|---|---|---|---|
| NFL schedules, scores, closing lines (historical) | [nflverse](https://github.com/nflverse/nfl_data_py) | Free, no key | Ships actual closing moneyline/spread/total per game |
| Soccer results + closing odds (historical) | [football-data.co.uk](https://www.football-data.co.uk/) | Free, no key | CSV per league/season; uses bookmaker-average (`Avg*`) columns when available |
| **Live market odds (both sports, ongoing)** | **[Kalshi](https://kalshi.com)** public REST API | **Free, no key** | CFTC-regulated exchange; read-only market data needs no auth. Each contract's dollar price *is* the market-implied probability. `KXNFLGAME` / `KXEPLGAME` series. |
| Live soccer fixtures/standings (optional) | [football-data.org](https://www.football-data.org/) | Free tier, needs key | Only needed if we want fixture metadata beyond what Kalshi/nflverse give us |
| Alternate sportsbook comparison (optional, not yet used) | [The Odds API](https://theoddsapi.com/) | Free tier is NBA/MLB only; NFL+soccer need **Professional, ~$29/mo** | Not required to get started — Kalshi covers live odds for free. Worth adding later to compare exchange vs. sportsbook pricing. |

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
pytest                                  # 57 tests, no network needed
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
```

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
- **Run 4's pre-registered prediction starts resolving 2026-09-12 evening**
  (14 EPL) and 2026-09-13 (49 NFL): ~30 wins if the claimed edges are real,
  ~22 if the selection audit is right. This is the first real evidence the
  project will produce. Settle it and report the count honestly whichever way
  it falls, and move nothing in the pricing pipeline until it has.
- **Verify the first backfilled CLV by hand** before trusting the aggregate.
  `backfill_clv` is tested but has never run against real settled rows, and a
  column that fills with plausible-looking numbers is precisely this project's
  recurring failure.
- **Measure the EPL expiry lag rather than assuming 3h.** The in-play gate's
  fallback is the one place a constant stands in for a measurement. Today's
  fixtures reach the stats table within days, at which point
  `kickoff.expiration_lag` can measure it for EPL as run 3 did for NFL.
- **Audit the remaining joins and sort keys.** Seven bugs of the same shape
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
- **Needs the owner (money):** The Odds API Professional (~$29/mo) for a
  sportsbook-style price to compare against Kalshi's exchange price. Rejected
  on the merits in run 2; listed here as a standing option, not an open ask.
- ~~Needs the owner (account): football-data.org key~~ -- **not needed.**
  football-data.co.uk already ships kickoff times.
- Snapshot cadence: CLV requires a captured pre-kickoff price, so run
  `snapshot-odds` several times a day, or at minimum shortly before each
  slate. A missed window is permanently missing data.

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
