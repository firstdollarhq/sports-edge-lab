# First scheduled review -- sources validated, history extended, and the one positive result is noise

_2026-09-10_

## What happened

First scheduled review after the kickoff build earlier today. Still **zero bets
placed** -- nothing to grade, no wins or losses to log, no odds-vs-model
comparisons to audit. Neither model has cleared the bar to make a live
recommendation, so the ledger is still header-only.

Three decisions were delegated to me this session: pick the data sources,
decide the persistence question, and decide whether to re-price edges at the
ask. All three are settled below.

## Correction to the earlier status report

Earlier today I reported that "any live recommendation priced off the Kalshi
mid would be overstating edge" and implied the backtests were affected. The
first half is right; the second is not. The two backtests run against
**sportsbook** odds (nflverse moneylines, football-data.co.uk bookmaker
averages), and a sportsbook quote is already the price you get -- vig baked
in, no mid-vs-ask gap. The mid-pricing exposure was specific to the **live
Kalshi path**, which had not placed a bet yet. Nothing historical was
contaminated. Recording this because a wrong diagnosis in the journal is worse
than no diagnosis.

## Decision 1 -- data sources (validated, not assumed)

Every source was tested against the live endpoint rather than trusted from the
README:

| Source | Status | Evidence |
|---|---|---|
| nflverse / `nfl_data_py` | **Keep** | 2024: 285 games, moneyline present on 285/285. 2025 complete, 2026 in progress. |
| football-data.co.uk | **Keep** | E0 2425 and 2526 complete at 380 games each; 2627 live with 30 played. `AvgH/AvgD/AvgA` present throughout. |
| Kalshi `/markets` | **Keep** | 122 open NFL+EPL markets, all two-sided. |
| Kalshi **candlesticks** | **ADD** | New. Returns real historical bid/ask/volume/OI per market. |
| The Odds API (~$29/mo) | **Reject** | Kalshi now covers live *and* historical for free. No reason to pay. |

**The candlestick endpoint is the significant find.** We would trade on Kalshi
but were backtesting against sportsbook closing lines -- different venues,
different prices, different spreads. Beating a bookmaker average tells you
little about beating an exchange. Candlesticks make a same-venue backtest
possible. Two traps found while validating it:

- The settled-market record cannot be used to reconstruct a closing price. Once
  a market settles the book empties, so `previous_yes_bid_dollars` reads
  0.0000 and `previous_yes_ask_dollars` reads 1.0000 on *every* settled market.
- The last candle before settlement is an **in-play** price. NFL markets close
  hours after kickoff, by which point the price has absorbed the result. Using
  it would be lookahead leakage wearing a closing-line costume.
  `closing_quote_before()` therefore takes the last two-sided quote strictly
  before kickoff, not before settlement.

Also fixed: `liquidity_dollars` reads **0.0000 on all 122 markets**, so the
liquidity filter is built on `volume_fp` / `open_interest_fp` /
`yes_bid_size_fp` / `yes_ask_size_fp` instead. None of these were previously
captured by the ingest code. **Only 61 of 122 open markets pass the filter** --
half the board is not realistically bettable.

## Decision 2 -- persistence: commit the record to git

The SQLite DB is gitignored and the container is ephemeral, so every scheduled
run was starting from zero history. Survivable for game tables (rebuildable
from free sources); **not** survivable for odds, because CLV cannot be
reconstructed retroactively. A pre-kickoff quote nobody wrote down is gone.

So the durable record is now plain CSV committed to git, and SQLite is demoted
to a derived cache:

- `data/processed/nfl_games.csv` -- 2,499 games, 2018-2026 (2,228 played)
- `data/processed/epl_games.csv` -- 2,690 games, 2019/20-2026/27
- `data/snapshots/kalshi/YYYY-MM-DD.csv` -- **first snapshot recorded today: 122 quotes**

`snapshot-odds` appends rather than overwrites, so running twice a day captures
intraday movement instead of discarding it. The CLV clock starts now; it should
have started at kickoff, and the day between is simply lost.

## Decision 3 -- price at the ask, and the unit bug that came with it

Adopted. On an exchange you do not trade at the mid, you lift the ask.
`edge = p/price - 1`, so pricing off the mid overstates edge by exactly
`ask/mid - 1`. Measured on today's live board:

| | median | p75 | max | markets where it eats the whole 3% threshold |
|---|---|---|---|---|
| NFL | 1.23% | 1.96% | 7.14% | 8 / 62 |
| EPL | 1.89% | 3.45% | 14.29% | 16 / 60 |

Worst case: Sunderland at Man City, bid $0.06 / ask $0.08 -- crossing costs
14.3%, roughly five times the entire edge threshold. On the 37 EPL contracts
priced under $0.30 the median cost is 3.45%, i.e. more than the threshold.
A 3% threshold measured against mid prices is not a 3% threshold.

While fixing this I found a latent unit bug and killed it. `edge.edge_pct()`
returned a *fraction* (0.03), while the ledger's `edge_pct` column,
`summarize()["avg_edge_pct"]` and `tests/test_ledger.py` all use *percent*.
Same name, two units, and the fraction was headed for the permanent bet
record. Renamed to `edge_fraction()` / `edge_percent()`. Nothing was corrupted
because no bet has been logged -- fixing it now was free, and it would not
have been free later.

## Backtest results on the extended history

Re-ran everything on the larger dataset. **Rule 3 holds: nothing here is
adopted.**

NFL 2018-2025 (2,227 games), market de-vigged closing baseline **log-loss
0.6091 / Brier 0.2108**:

| Model | Log-loss | ROI | t | 95% CI | Verdict |
|---|---|---|---|---|---|
| Vanilla Elo | 0.6516 | -8.64% | -2.53 | [-15.2%, -1.8%] | Loses, significantly |
| + MOV scaling | 0.6387 | -9.51% | -2.87 | [-15.9%, -2.9%] | Loses, significantly |

Both remain clearly worse-calibrated than the market. Note that MOV scaling
**improved log-loss but made ROI worse** on this larger sample -- at kickoff it
improved both. The "validated small improvement" from this morning is weaker
than it looked; it is a calibration improvement only, and it is still a
significant money-loser. Not adopted.

### The EPL result, and why it is not a discovery

EPL 2025-26 held out (380 games, calibrated on 2019/20-2024/25):

- Model log-loss **0.6351** vs market **0.6192** -- the model is still WORSE.
- Flat-stake ROI **+8.27%**, win rate 35.8%, on 282 bets.

This is the first positive number the project has produced, and it is noise:

- **t = +0.84.** 95% CI **[-11.1%, +27.6%]** -- spans zero comfortably.
- Resolving an edge this size at 2 sigma would take **~1,600 bets**, more than
  four full EPL seasons of betting every flagged game.
- 282 of 380 games (74%) flagged at a 3% threshold -- the same
  calibration-failure tell as everywhere else.
- Decisive: **a model that is worse-calibrated than the market cannot have a
  real edge against it.** Positive ROI alongside worse log-loss is the
  signature of variance, not skill. If the model genuinely knew something the
  market did not, it would show up in log-loss first.

Taking this live would be precisely the bias-confirmation trap in the project
brief. It is not adopted, and it will not be, unless log-loss beats the market
first.

To stop this arising again, `simulate_flat_stake_roi()` now returns
`roi_se_pp`, `roi_t_stat`, `roi_ci95_pct` and `significant_at_95` alongside the
point estimate. **ROI can no longer be reported without its interval.**

## What worked

Validating sources against live endpoints rather than trusting the README --
it turned up the candlestick endpoint, the settled-market trap, and the dead
`liquidity_dollars` field. Reporting uncertainty by default immediately paid
for itself on the EPL number.

## What did not work

Both models still lose to the market on both sports; that has not changed and
the extra data did not help. MOV scaling is a weaker candidate than it looked
this morning. And a bug I introduced myself this session: `_load_games()`
initially ignored `--seasons` when reading the committed table, which silently
held out the 30-game in-progress 2026-27 season instead of a completed one.
Caught because a 30-game holdout is obviously too small; a subtler version
would have sailed through. Now filtered explicitly, with a warning on missing
seasons.

## Open questions / next steps

- **Build the Kalshi-venue backtest.** All results so far measure the model
  against sportsbooks; the venue we would actually trade is Kalshi.
  `closing_quote_before()` makes this possible and it is the highest-value
  next piece of work.
- Still no live recommendations, correctly. The bar is unchanged: beat the
  market on log-loss out-of-sample first.
- Candidate improvements still unbacktested: injury/QB-change signals for NFL,
  shorter Elo half-life for soccer, wider calibration window.
- Half the Kalshi board fails the liquidity filter. The thresholds
  (OI >= 500, volume >= 500, resting size >= 50, spread cost <= 2%) are a first
  guess and have not been validated against realized fill quality.
- Snapshot cadence is currently whatever the schedule fires at. Capturing a
  quote close to kickoff matters more than capturing many far from it.
- Standing reminder: 0 bets, 1 day. Everything above is model archaeology, not
  evidence about markets.
