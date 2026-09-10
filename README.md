# sports-edge-lab

A research project testing predictive sports models against real market odds.
**Paper trading only** — no real money moves through this repo. The goal is
to find a real, validated edge, not to confirm a bias. See `journal/` for an
honest, dated log of what was tried and what happened.

## Status (2026-09-10, first scheduled review)

- **0 bets placed.** Nothing has been recommended live.
- Historical record: **2,499 NFL games** (2018–2026) and **2,690 EPL games**
  (2019/20–2026/27), committed under `data/processed/`.
- Odds snapshots: **started 2026-09-10**, committed under `data/snapshots/`.
- Two leagues active: **NFL** and **EPL**. NBA/NHL stubbed but disabled —
  seasons start ~Oct 2026.
- **Neither model beats the market**, on either sport, on the extended
  history. Not deployed. See the journal for numbers, including an EPL
  backtest that returned +8.27% ROI and is statistically indistinguishable
  from zero (t=+0.84).

## Why these data sources

| Need | Source | Cost | Notes |
|---|---|---|---|
| NFL schedules, scores, closing lines (historical) | [nflverse](https://github.com/nflverse/nfl_data_py) | Free, no key | Ships actual closing moneyline/spread/total per game |
| Soccer results + closing odds (historical) | [football-data.co.uk](https://www.football-data.co.uk/) | Free, no key | CSV per league/season; uses bookmaker-average (`Avg*`) columns when available |
| **Live market odds (both sports, ongoing)** | **[Kalshi](https://kalshi.com)** public REST API | **Free, no key** | CFTC-regulated exchange; read-only market data needs no auth. Each contract's dollar price *is* the market-implied probability. `KXNFLGAME` / `KXEPLGAME` series. |
| Live soccer fixtures/standings (optional) | [football-data.org](https://www.football-data.org/) | Free tier, needs key | Only needed if we want fixture metadata beyond what Kalshi/nflverse give us |
| **Historical exchange bid/ask** | **Kalshi candlesticks** | **Free, no key** | `/series/{s}/markets/{m}/candlesticks` returns the real historical bid/ask/volume/OI series. Enables a backtest on the venue we would actually trade. |
| Alternate sportsbook comparison | [The Odds API](https://theoddsapi.com/) | ~$29/mo for NFL+soccer | **Rejected.** Kalshi covers live *and* historical for free. |

Kalshi was not part of the original plan — it came up mid-build as a
free alternative to a paid odds API, and turned out to cover exactly the two
leagues we're starting with, so it's now the primary live-odds source.

Every source above was validated against its live endpoint on 2026-09-10, not
taken on trust. Two Kalshi gotchas that cost real time:

- `liquidity_dollars` reads **0.0000 on every market sampled** (122/122). The
  liquidity filter uses `volume_fp` / `open_interest_fp` / `yes_bid_size_fp`.
- A settled market's `previous_yes_bid/ask` reads 0.00/1.00 — the book empties
  on settlement. And the last candle before settlement is an **in-play** price,
  since NFL markets close hours after kickoff. `closing_quote_before()` takes
  the last two-sided quote strictly before *kickoff* to avoid leakage.

## Architecture

```
src/sportsedge/
  ingest/       nfl_stats.py, soccer_stats.py (historical), kalshi.py (live odds)
  models/       elo.py (rating engines), calibration.py (soccer 3-way outcome calibration)
  backtest/     engine.py (walk-forward backtest, no lookahead), metrics.py
  betting/      edge.py (de-vig, EV, Kelly), ledger.py (bets/ledger.csv)
  journal/      entry.py (dated markdown journal entries)
  storage/      db.py + schema.sql (SQLite historical database)
```

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
3. `edge_fraction = model_prob * decimal_odds - 1`. A paper bet is only logged
   if edge clears **`edge_threshold_pct`** (default 3%, see
   `config/leagues.yaml`).
   **Price at the ask, never the mid.** On an exchange you lift the ask to buy,
   and pricing off the mid overstates edge by exactly `ask/mid - 1`. On the
   live board that is a median of 1.23% (NFL) and 1.89% (EPL), reaching 14.3%
   on thin longshots — 16 of 60 EPL markets have a spread that eats the entire
   3% threshold. Run `spread-report` to see today's numbers.
   Units: `edge_fraction()` returns a fraction; everything human-facing
   (config, CLI, ledger, journal) is percent. Convert at the boundary.
4. Stake sizing uses **fractional Kelly** (`kelly_multiplier = 0.25` by
   default) — never full Kelly, which is too volatile for a model with
   uncertain calibration.
5. Every bet, win or loss, goes in `bets/ledger.csv` with model prob, market
   odds, edge, and (once the game closes) closing odds and CLV — closing
   line value is tracked independently of win/loss because it's a better
   short-run signal of whether the model has real skill than win rate alone.

## Backtesting discipline

**No model change goes live without being backtested first, and the backtest
result goes in the journal even if it's bad.** ROI is never reported without
its uncertainty: `simulate_flat_stake_roi()` returns `roi_t_stat`,
`roi_ci95_pct` and `significant_at_95` alongside the point estimate, because a
profitable-looking backtest on a few hundred bets usually is not one. The walk-forward backtest
(`src/sportsedge/backtest/engine.py`) only ever uses information available
before each game to make that game's prediction — ratings update strictly
after the prediction is recorded, so there's no lookahead leakage.

Run it yourself:

```bash
pip install -e ".[dev]"
python -m sportsedge.cli backtest-nfl --seasons 2018 2019 2020 2021 2022 2023 2024 2025
python -m sportsedge.cli backtest-soccer --league E0 --seasons 1920 2021 2122 2223 2324 2425 2526
```

Hold out a **completed** season. Passing an in-progress season as the holdout
gives a 30-game test set and a meaningless result.

## Setup

```bash
pip install -e ".[dev]"
pytest                                  # 43 tests, no network needed
cp .env.example .env                    # only needed for optional sources
python -m sportsedge.cli refresh-history   # rebuild the durable game tables
python -m sportsedge.cli snapshot-odds     # record today's Kalshi book — run daily
python -m sportsedge.cli spread-report     # what crossing the spread costs today
python -m sportsedge.cli kalshi-nfl        # live NFL board, with liquidity flags
python -m sportsedge.cli kalshi-epl
python -m sportsedge.cli ledger-summary
```

## Journal discipline

Every meaningful session (data refresh, model change, backtest run, bet
settled) gets a dated entry in `journal/` via `src/sportsedge/journal/entry.py`.
Entries record what worked, what didn't, and why — including negative
results. **A few weeks of results is noise; the point is signal, not
confirming a bias.**

## Where the data lives

`data/processed/` and `data/snapshots/` are **committed to git on purpose.**
Each run gets a fresh, ephemeral container, so a gitignored SQLite file does
not survive between runs. Game tables could be rebuilt from upstream, but
odds cannot: CLV is unreconstructable after the fact, and an unrecorded
pre-kickoff quote is gone permanently. CSV in git is the record; SQLite is a
derived cache.

## Open questions / next steps

- **Build the Kalshi-venue backtest.** Everything measured so far is
  model-vs-sportsbook, but Kalshi is where we would trade.
  `ingest.kalshi.closing_quote_before()` makes this possible; it is the
  highest-value next task.
- Baseline Elo still underperforms the market on both sports over the extended
  history (NFL 0.6516 vs 0.6091; EPL 0.6351 vs 0.6192). Until that flips there
  is no edge to bet, only threshold noise. MOV scaling improves NFL log-loss
  but made simulated ROI *worse* on the larger sample — not adopted.
- The liquidity filter now exists, but **half the board fails it** (61/122
  markets). Its thresholds are a first guess, unvalidated against realized
  fill quality.
- Snapshot timing matters more than snapshot count — a quote near kickoff is
  worth many taken days out.
