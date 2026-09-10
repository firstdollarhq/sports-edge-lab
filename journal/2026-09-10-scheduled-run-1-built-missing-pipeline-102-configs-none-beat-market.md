# Scheduled run #1 -- built the missing pipeline; swept 102 model configs, none beat the market

_2026-09-10_

## What happened

First scheduled review run, ~5 hours after project kickoff. It found zero bets
to review, which turned out to be structural rather than incidental: **there was
no code path that could ever place a bet.** `add_bet()` and `record_result()`
were called only from the test suite. Nothing wired model → live odds → edge →
ledger, and nothing settled a pending bet or filled a closing price. The ledger
could not have filled no matter how long the schedule ran.

So this run was mostly plumbing, plus a real model experiment once the plumbing
made the failure mode visible.

## Bets placed

**39 shadow bets** (27 NFL, 12 EPL), all pending -- the games are Sep 19-21.
Zero live bets. `live_enabled` remains `false` for both leagues.

Shadow bets are recorded as evidence and excluded from headline win rate and
ROI. They exist so that a model which has not earned deployment still generates
an out-of-sample track record we can grade later.

Average flagged "edge" across those 39: **+28.5%**. That number is not good
news. A 28.5% average edge against a liquid regulated exchange is a statement
about the model, not about the market.

## The diagnosis: under-dispersion, and why rescaling can't fix it

The live recommender made the failure legible in a way aggregate log-loss did
not. Every single top NFL recommendation was on an underdog:

```
MIA @ SF    away  model=0.338  market fair=0.141  edge=+125%
Hull @ CHE  away  model=0.245  market fair=0.065  edge=+250%
```

Measured over 2018-24 (1,942 games), NFL model probabilities are badly
under-dispersed against the market:

| | sd | range |
|---|---|---|
| Model | 0.100 | 0.239 – 0.852 |
| Market (de-vigged) | 0.183 | 0.088 – 0.937 |

corr(model, market) = 0.667.

The obvious fix is to stretch the probabilities away from 0.5. **It does not
work.** Stretching the log-odds by a scale factor:

| scale | 1.0 | 1.2 | 1.4 | 1.6 | 2.0 |
|---|---|---|---|---|---|
| log-loss | 0.6529 | 0.6526 | 0.6545 | 0.6586 | 0.6722 |

Best case is a 0.0003 improvement at scale=1.2, then it degrades. That is the
important result: if the model's *ordering* were as good as the market's and it
were merely timid, stretching would recover most of the gap. It doesn't, so the
ordering itself is worse. This is an **information gap, not a calibration bug.**

The decile table shows where the ordering fails -- the model is systematically
too high on weak home teams:

| elo_diff bucket | n | actual | model | market |
|---|---|---|---|---|
| (-201, -26] | 243 | 0.292 | 0.406 | 0.353 |
| (-26, 9] | 243 | 0.403 | 0.489 | 0.420 |
| (9, 35] | 242 | 0.426 | 0.531 | 0.503 |
| (143, 304] | 243 | 0.782 | 0.737 | 0.738 |

At the top end the model matches the market almost exactly. At the bottom it is
10+ points too generous. Combined with under-dispersion, the effect is that the
model overrates whichever side is the underdog -- and a 3% edge threshold then
flags nearly every underdog as +EV. That is precisely the "threshold is catching
miscalibration, not edges" suspicion from kickoff, now with a mechanism.

## Backtest of proposed changes -- 102 configs, zero adopted

Protocol: walk-forward, calibration fit strictly on seasons earlier than the
test season, metrics pooled over held-out seasons. Baseline to beat is the
de-vigged closing line, not the previous model version.

**NFL** (48 configs: k ∈ {12,20,28,36} × home_adv ∈ {25,40,55} × MOV on/off ×
logistic calibration on/off; test seasons 2021-24, n=1,139):

- Market: log-loss **0.6116**, Brier 0.2118
- Baseline (k=20, ha=55): 0.6516
- Best config (k=12, ha=40, MOV, no calib): **0.6459**
- **Configs beating market: 0 of 48**

**EPL** (54 configs: k ∈ {12,20,30} × home_adv ∈ {40,60,80} × goal-diff scaling
on/off × calibration window ∈ {2,3,5} seasons; test season 2024-25, n=380):

- Market: log-loss **0.9706**
- Baseline (k=20, ha=60, gd_scale, 5 seasons): 0.9895
- Best config (k=30, ha=40, no gd_scale, 5 seasons): **0.9834**
- **Configs beating market: 0 of 54**

**Nothing adopted.** Every candidate improves on the baseline and every
candidate still loses to the market, so none clears the deployment gate. Two
secondary findings worth keeping:

- `home_advantage=55` is too high for NFL; 25 and 40 both beat it consistently.
- EPL's problem is *not* dispersion (model sd_home 0.207 vs market 0.192 -- the
  soccer model is if anything slightly over-dispersed). Its gap is pure
  information. So the NFL and EPL models are failing for different reasons and
  should not be "fixed" with the same lever.

The models were left at v1 rather than switched to the marginally-better
configs. Changing the shadow model now would reset the evidence clock in
exchange for a model that still loses to the market -- no gain.

**Conclusion: Elo-on-scores parameter tuning is exhausted.** 102 configurations
spanning a wide parameter space all land in 0.645-0.66 (NFL) and 0.983-0.99
(EPL). The remaining gap is information the market has and Elo does not --
injuries, QB changes, lineups, weather, motivation. The only candidate worth
pursuing is *adding information*, not retuning.

## What was built

- `ingest/teams.py` -- resolves Kalshi tickers to stats-source teams.
- `storage/snapshots.py` -- durable, committed odds capture.
- `betting/liquidity.py` -- fillability filter.
- `betting/recommend.py` -- model → live odds → de-vig → edge → ledger.
- `betting/settle.py` -- settlement + CLV.
- `models/live.py` -- current-strength ratings for live pricing.
- CLI: `snapshot-odds`, `recommend`, `settle`, `verify-settlements`.
- Tests: 17 → **57**, all network-free.

Three correctness details that were verified rather than assumed:

1. **Kalshi ticker team order differs by sport.** NFL is `AWAY+HOME`
   (`KXNFLGAME-26SEP21NYGLAR` = NYG at LA); EPL is `HOME+AWAY`
   (`KXEPLGAME-26SEP06ARSCFC` = Arsenal hosting Chelsea). Verified against
   nflverse (15/15 week-2 games) and football-data.co.uk (4/4 fixtures). Getting
   this backwards would invert every prediction while leaving aggregate metrics
   looking plausible. Both orders are now pinned by tests.
2. **Settlement cross-check: 92 markets checked, 92 agreed, 0 mismatches**
   between Kalshi's own resolution and the independent stats sources.
3. **We price at the ask, not the mid.** Pricing at the mid credits the model
   with half the spread on every bet -- ~0.5% of notional on a 1-cent book,
   which is the same order of magnitude as the edges being hunted.

## What did not work

- Every proposed model change. 102 configs, none cleared the gate.
- Probability rescaling as a fix for NFL under-dispersion (see above).
- My first settlement cross-check reported 20 NFL mismatches. That was a bug in
  the *verifier*, not the mapping: it joined markets to games on team pairing
  alone, so August preseason markets matched regular-season fixtures with the
  same two teams. Fixed by keying on date (±1 day for timezone skew) and pinned
  by a regression test.

## Data sources used

- nflverse -- NFL schedules/scores/closing lines (free, no key)
- football-data.co.uk -- EPL results + closing odds (free, no key)
- Kalshi public REST API -- live prices and settlements (free, no key)

New data this run: the 2026 NFL season is one game old (1 of 272 complete, SEA
13-10 NE), and EPL 2026-27 has 30 completed matches. There was essentially
nothing new to backfill.

## Liquidity finding

The liquidity filter is doing real work, and asymmetrically:

- NFL: 61 of 62 contracts fillable.
- EPL: **38 of 60** -- 22 rejected, almost all on thin volume.

So a third of the EPL book is not a tradeable price. Pricing off those quotes
would have manufactured edges out of stale markets. This closes the "need a
Kalshi liquidity filter" open question from kickoff.

## Correction to the kickoff entry

The kickoff journal says live odds were verified against "Week 3 NFL" markets.
NFL 2026 week 1 is Sep 9-14, so the Sep 19-21 slate is **week 2**. No number in
that entry depends on this.

## Open questions / next steps

- **Escalation (money):** The Odds API Professional (~$29/mo) for a second,
  sportsbook-style price to compare against Kalshi's exchange price. Owner
  decision -- not purchased.
- **Escalation (account):** football-data.org free tier needs an API key that a
  human must create. Owner decision -- not created.
- The scheduled prompt still contains a literal `[which data sources?]`
  placeholder; the working answer is recorded in CLAUDE.md, but the stored
  prompt lives at account level and can't be edited from inside a session.
- Next model direction is **new information, not new parameters**: QB
  change/injury signals for NFL are the highest-value candidate. Elo tuning is
  done.
- Snapshot cadence: CLV needs a pre-kickoff price. A once-daily run will miss
  closing prices for games that start between runs. Consider running
  `snapshot-odds` several times daily, or at minimum shortly before each slate.
- 39 shadow bets settle Sep 19-22. **That will be ~39 outcomes, which is
  noise.** Do not read a win/loss streak off them either way. The thing worth
  reading first is CLV, and even that needs far more than one slate.
