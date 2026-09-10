# Scheduled run 2 -- a lookahead bug invalidates every NFL ROI number published so far

_2026-09-10_

## Headline

**Every NFL backtest this project has published was computed with the season's
chronology scrambled.** The walk-forward engine sorted on a `week` column that
the NFL ingest stored as a *string*, so `"10"` sorted before `"2"` and each
season was processed in the order 1, 10, 11 … 18, 19, 2, 20, 21, 22, 3, 4 …
The model therefore predicted week 2 using Elo ratings that had already
absorbed weeks 10-18. That is lookahead leakage, in the one module whose
docstring states it has none.

It flattered simulated ROI by about 3.6 points:

| NFL 2018-2024, vanilla Elo | Log-loss | ROI | Bets flagged |
|---|---|---|---|
| As published (scrambled order) | 0.652864 | **-4.65%** | 1665 |
| Corrected (chronological) | 0.651762 | **-8.21%** | 1625 |

The scrambled figures are the ones in both prior journal entries. They are
withdrawn. Fixed in `ingest/nfl_stats.py` (week is now a nullable int) and
defensively in `backtest/engine.py`, which now sorts on a coerced numeric week
regardless of what dtype the ingest hands it. Pinned by
`tests/test_backtest_order.py`.

Found by accident: NFL backtests stopped reproducing after I routed them
through a committed CSV, and the CSV round-trip had silently made `week` an
int64. EPL reproduced to twelve decimal places throughout, because
`backtest_soccer` sorts on `game_date` alone and never touched the bad column.
The asymmetry is what gave it away. Worth noting how quiet this was: the
aggregate metrics all looked plausible, and log-loss barely moved.

### What this does and does not invalidate

- **NFL ROI figures: invalid.** Everywhere they appear, including the
  102-configuration sweep from run 1.
- **NFL log-loss figures: essentially unaffected.** 0.652864 → 0.651762 is a
  0.001 move. The sweep's ranking by log-loss should survive, and its
  conclusion certainly does: the best NFL config was 0.6459 against a market
  baseline of 0.6116, and a gap that size is not closed by a 0.001 correction.
  **No adoption decision changes.** Nothing was live; nothing becomes live.
- **All EPL figures: unaffected**, and verified by exact reproduction.

## Corrected NFL results

Market de-vigged closing baseline: **log-loss 0.6091**.

| Config | n | Log-loss | ROI | t | 95% CI | Significant |
|---|---|---|---|---|---|---|
| 2018-2024 vanilla | 1942 | 0.6518 | -8.21% | -2.25 | [-15.4%, -1.1%] | yes |
| 2018-2024 +MOV | 1942 | 0.6389 | -10.38% | -2.97 | [-17.2%, -3.5%] | yes |
| 2018-2025 vanilla | 2227 | 0.6516 | -8.64% | -2.53 | [-15.3%, -2.0%] | yes |
| 2018-2025 +MOV | 2227 | 0.6387 | -9.51% | -2.87 | [-16.0%, -3.0%] | yes |

MOV scaling still improves log-loss and still makes ROI *worse*, now with the
losses significant at 95%. It remains unadopted, and the case for it is weaker
than the kickoff entry suggested.

## The EPL result that looks like a discovery and is not

Holding out the completed 2025-26 season (380 games, calibrated on
2019/20-2024/25):

- Model log-loss **0.6351** vs market **0.6192** -- the model is still worse.
- Flat-stake ROI **+8.27%**, win rate 35.8%, on 282 bets.

The project's first positive number, and it is noise:

- **t = +0.84**, 95% CI **[-11.1%, +27.6%]**, comfortably spanning zero.
- Resolving an edge this size at 2 sigma needs **~1,600 bets** -- over four
  full EPL seasons of betting every flagged game.
- 282 of 380 games (74%) flagged at a 3% threshold: the usual
  calibration-failure tell.
- Decisive: **a model that is worse-calibrated than the market cannot have a
  real edge against it.** Positive ROI alongside worse log-loss is variance.
  Genuine knowledge the market lacks would show up in log-loss first.

Not adopted, and it will not be unless log-loss beats the market first.
`simulate_flat_stake_roi()` now returns `roi_se_pp`, `roi_t_stat`,
`roi_ci95_pct` and `significant_at_95`, so **ROI can no longer be reported
without its interval.**

## Corrections to my own earlier claims this session

Two things I said in the interim status report were wrong or overstated, and
correcting them matters more than the findings themselves:

1. **"The spread eats the whole 3% edge threshold."** The measurements are
   right (median relative width 1.23% NFL / 1.89% EPL, up to 14.3%), but the
   implication was wrong. `recommend.py` already prices edges at the **ask**,
   with a test pinning it, so the cost of crossing is already paid inside the
   edge number. It is not a further deduction, and describing it as one would
   double-count it. The framing applied to a mid-priced recommender, which had
   already been replaced on the default branch before I looked.
2. **The liquidity gate I first added was too tight.** I set a 2% cap on
   relative book width, which rejected a 0.40/0.42 market -- entirely ordinary,
   2.4% wide -- and broke four existing tests. That was me tuning a threshold
   to a story rather than to the data. Re-scoped to 5%, which catches the
   pathological tail (the worst observed, Sunderland at Man City at bid 0.06 /
   ask 0.08, is 14.3% wide and passes every absolute check) and leaves normal
   markets alone. Its honest justification is that a very wide relative book
   makes the de-vigged fair price unreliable and unlikely to fill near the
   touch -- **not** that it costs edge.

Also withdrawn: the earlier report said this session's ledger had zero bets
and no pipeline could fill it. The parallel run had already built the
pipeline; the live ledger is still empty by design, but 39 shadow bets exist.

## Data sources -- validated, not assumed

Each was tested against its live endpoint rather than trusted from the README:

| Source | Status | Evidence |
|---|---|---|
| nflverse / `nfl_data_py` | Keep | 2024: 285 games, moneyline on 285/285. 2025 complete, 2026 in progress. |
| football-data.co.uk | Keep | E0 2425 and 2526 complete at 380 each; 2627 live with 30 played. `Avg*` columns throughout. |
| Kalshi `/markets` | Keep | 122 open NFL+EPL markets, all two-sided. |
| Kalshi **candlesticks** | **Added** | Real historical bid/ask/volume/OI per market. |
| The Odds API (~$29/mo) | **Rejected** | Kalshi covers live *and* historical for free. |

The candlestick endpoint is the useful find: we would trade on Kalshi but every
backtest measures against sportsbook lines, which is a different venue with
different prices. Two traps documented in `ingest/kalshi.py`:

- A settled market cannot yield its own closing price -- the book empties on
  settlement, so `previous_yes_bid/ask` reads 0.00/1.00 on *every* settled
  market.
- The last candle before settlement is an **in-play** price. NFL markets close
  hours after kickoff, by which point the price has absorbed the result. Using
  it as a closing line would be lookahead leakage in a convincing costume --
  the same class of error as the week bug above, which is not a coincidence.
  `closing_quote_before()` therefore cuts at kickoff, not at settlement.

Historical tables are now committed rather than re-downloaded per run:
`data/processed/nfl_games.csv` (2,499 games, 2018-2026) and
`data/processed/epl_games.csv` (2,690 games, 2019/20-2026/27). A backtest whose
inputs silently re-download is a backtest whose sample can shift under a result
you have already published.

## Merge note

This run's work was developed in parallel with scheduled run 1 and merged into
it. Where the two overlapped, run 1's implementation was kept: its Kalshi
client (ticker-based team resolution, retry/backoff), its snapshot store, its
liquidity module, and its CLI. My additions on top: candlestick history,
committed game tables, the season filter on backtests, ROI significance
reporting, the `edge_pct` → `edge_fraction`/`edge_percent` rename (the old name
collided with the ledger's percent-valued column of the same name), the
relative-width gate, and the chronology fix. My own snapshot directory
(`data/snapshots/kalshi/`) was a redundant duplicate in a layout nothing reads
and was removed in favour of the per-sport layout.

## State

- **0 live bets.** 39 shadow bets pending, from models that failed backtest;
  excluded from headline stats, as they should be.
- No model deployed. `live_enabled` false everywhere.
- Tests 61 → 82, all network-free.
- Odds snapshots: 248 NFL + 240 soccer quotes captured today.

## Open questions / next steps

- **Re-run the 102-config sweep's ROI figures.** Log-loss rankings and the
  no-adoption conclusion stand; the ROI column does not.
- **Build the Kalshi-venue backtest.** Everything measured so far is
  model-vs-sportsbook. `closing_quote_before()` makes the real comparison
  possible and it is the highest-value work left.
- Audit the remaining sort keys and joins for the same class of bug. One
  string-typed ordering column survived this long unnoticed; there is no reason
  to assume it was the only one.
- Elo parameter tuning is exhausted (run 1's conclusion, unaffected). The next
  direction is adding information, not retuning.
- The 5% relative-width gate is a first guess, unvalidated against realized
  fill quality.
- Standing reminder: 0 live bets, 1 day. Everything above is model
  archaeology, not evidence about markets.
