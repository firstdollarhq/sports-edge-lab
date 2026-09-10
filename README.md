# sports-edge-lab

A research project testing predictive sports models against real market odds.
**Paper trading only** — no real money moves through this repo. The goal is
to find a real, validated edge, not to confirm a bias. See `journal/` for an
honest, dated log of what was tried and what happened.

## Status (2026-09-10, project creation)

- **0 bets placed.** This repo did not exist before today.
- Two leagues active: **NFL** (season underway) and **EPL** (English Premier
  League, season underway). NBA/NHL are stubbed in `config/leagues.yaml` but
  disabled — their seasons start in ~a month.
- Baseline Elo models are built and backtested against real historical closing
  odds. **Neither currently beats the market** (see `journal/2026-09-10-project-kickoff-*.md`
  for numbers) — they are not yet deployed for live recommendations. This is
  the expected/correct first result for a naive baseline, not a setback.

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
3. `edge_pct = model_prob * decimal_odds - 1`. A paper bet is only logged if
   edge clears **`edge_threshold_pct`** (default 3%, see `config/leagues.yaml`).
4. Stake sizing uses **fractional Kelly** (`kelly_multiplier = 0.25` by
   default) — never full Kelly, which is too volatile for a model with
   uncertain calibration.
5. Every bet, win or loss, goes in `bets/ledger.csv` with model prob, market
   odds, edge, and (once the game closes) closing odds and CLV — closing
   line value is tracked independently of win/loss because it's a better
   short-run signal of whether the model has real skill than win rate alone.

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
```

## Setup

```bash
pip install -e ".[dev]"
pytest                                  # 17 tests, no network needed
cp .env.example .env                    # only needed for optional sources
python -m sportsedge.cli kalshi-nfl     # live NFL market snapshot, no key needed
python -m sportsedge.cli kalshi-epl     # live EPL market snapshot, no key needed
python -m sportsedge.cli ingest-nfl --seasons 2023 2024
python -m sportsedge.cli ingest-soccer --league E0 --seasons 2324 2425
python -m sportsedge.cli ledger-summary
```

## Journal discipline

Every meaningful session (data refresh, model change, backtest run, bet
settled) gets a dated entry in `journal/` via `src/sportsedge/journal/entry.py`.
Entries record what worked, what didn't, and why — including negative
results. **A few weeks of results is noise; the point is signal, not
confirming a bias.**

## Open questions / next steps

- Baseline Elo underperforms the market on both NFL (log-loss 0.653 vs.
  market 0.610) and EPL (0.607 vs. 0.590) — before this improves, there is
  no real edge to bet, only threshold noise. Next candidate improvements to
  backtest (not yet adopted): incorporate injury/QB-change signals for NFL,
  try a shorter Elo half-life / higher K for soccer, and widen the calibration
  training window.
- Kalshi order-book liquidity varies a lot by market — need to add a min
  liquidity/volume filter before treating a Kalshi quote as a real, fillable
  price rather than a stale one.
- Not yet decided: whether to also pull The Odds API (paid) for a second,
  traditional-sportsbook price to compare against Kalshi's exchange price.
