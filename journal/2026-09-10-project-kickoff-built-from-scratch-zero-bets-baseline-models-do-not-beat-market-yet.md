# Project kickoff -- built from scratch, zero bets, baseline models do not beat market yet

_2026-09-10_

## What happened

Project created from scratch today -- there was no prior repo, model, or bet history. Built the initial scaffold: ingestion for NFL (nflverse, free) and EPL (football-data.co.uk historical, Kalshi live, both free), an Elo rating engine for each sport, a walk-forward backtester, edge/Kelly staking math, a paper-trade CSV ledger, and this journal tooling. Repo: private, GitHub.

Also evaluated Kalshi (a CFTC-regulated event-contract exchange) as an odds source per a mid-build question -- its public market-data API is free and requires no key for reads, and it covers both NFL (KXNFLGAME) and EPL (KXEPLGAME) with real order-book prices. This replaces the originally-planned paid Odds API subscription as the live-odds source for now.

## Bets placed

None. Zero bets exist in bets/ledger.csv. Nothing has been recommended live yet -- the baseline models have not cleared the bar to go live (see below).

## Backtest results (baseline Elo, before any live use)

NFL, 2018-2024 seasons (1942 games), vanilla Elo (k=20, home_adv=+55, no MOV scaling):
- Model log-loss: 0.6529 / Brier: 0.2305
- Market (de-vigged closing lines) log-loss: 0.6097 / Brier: 0.2109 -- the model is WORSE than just trusting the closing line.
- At a 3% edge threshold: 1665 of 1942 games (86%) got flagged as a bet -- that ratio alone says the threshold is catching model miscalibration, not real edges.
- Simulated flat-stake ROI on those flagged bets: -4.65%, win rate 34.7%.

Tried one proposed change -- margin-of-victory K-scaling (the standard 538-style multiplier) -- and backtested it before considering adoption:
- Log-loss improves to 0.6447 / Brier 0.2263, ROI improves to -2.80%, win rate 40.6%.
- Verdict: a real, measurable improvement, but still worse than market and still losing money. NOT adopted for live use -- it's a step in the right direction, not a finished model.

EPL, 2024-25 season (380 games) held out as test set, Elo calibrated via multinomial logistic regression fit on 2019/20-2023/24:
- Model log-loss: 0.6071 / Brier: 0.2108 vs. market 0.5905 / 0.2037 -- same pattern as NFL, model is behind the market.
- 304 of 380 games (80%) flagged at 3% edge threshold. ROI -5.12%, win rate 33.6%.

Honest read: both baseline models are currently WORSE calibrated than the closing line. The high bet-flagging rate at a 3% threshold is the tell -- a well-calibrated model should agree with an efficient market on the vast majority of games and only flag a genuine minority as mispriced. Neither model is deployed for real recommendations. This is the correct and expected outcome for an untuned first-pass Elo model, not a failure of the project.

## What worked

The data pipeline end-to-end: real historical closing lines from nflverse, real historical odds from football-data.co.uk, and real live order-book prices from Kalshi (verified against actual live Week 3 NFL and EPL markets while building). Walk-forward backtest harness has no lookahead leakage. MOV-scaling for NFL Elo is a validated small improvement.

## What did not work

Both baseline Elo models, as-is, lose to the market. Flagging 80-86% of games as +EV at a 3% threshold is a calibration failure, not a discovery of an inefficient market -- treating it as one would be exactly the bias-confirmation trap this project is explicitly trying to avoid.

## Data sources used

- nflverse / nfl_data_py -- NFL schedules, scores, closing moneyline/spread/total (free, no key)
- football-data.co.uk -- soccer historical results + closing odds, EPL used so far (free, no key)
- Kalshi public REST API -- live market prices for NFL and EPL (free, no key for reads)
Not yet used: football-data.org (live soccer fixtures, free tier needs key), The Odds API (paid, would add a second sportsbook-style price to compare against Kalshi).

## Open questions / next steps

- Do NOT go live with either model as-is. Candidate improvements to backtest next: injury/QB-change adjustments for NFL, shorter Elo half-life for soccer, wider soccer calibration window.
- Need a Kalshi liquidity/volume filter before treating any quote as fillable rather than stale.
- Undecided: add The Odds API (9/mo Professional tier) for a second live-odds source to compare against Kalshi, or rely on Kalshi alone for now.
- NBA and NHL intentionally deferred -- seasons start in ~a month.
- Standing reminder: a few weeks of results will be noise regardless of what the model does next. Do not treat any near-term win/loss streak as validation either way.
