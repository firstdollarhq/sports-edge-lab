# Scheduled run 4 -- the betting rule selects the model's own errors

_2026-09-11_

## Headline

**The model is roughly calibrated. The rule that turns it into bets is not,
and the two facts have been hiding each other.**

Run 3 left a diagnosis on the table: NFL is "under-dispersed and overrates
underdogs". That is a statement about the ratings. It is wrong, or at least it
names the wrong culprit. Within the same predicted-probability buckets, NFL
2021-24:

| sample | n | claimed | actual | gap |
|---|---|---|---|---|
| all priced sides | 2278 | — | — | +0.011 / −0.039 / +0.023 / −0.026 / +0.026 |
| **sides the rule BETS** | 930 | 0.466 | 0.329 | **−0.137** |
| **sides the rule PASSES** | 1348 | 0.523 | 0.616 | **+0.093** |

Unconditionally the ratings are fine: the per-bucket gaps are small and they
alternate sign. Conditional on being **bet**, the model overstates by 13.7
points -- in *every* bucket, from 0.20 to 1.00, not just on longshots.
Conditional on being **passed**, it understates by 9.3. Selection gap
**−0.230**. EPL is the same sign and shape at −0.060.

This is the winner's curse, and the mechanism is not subtle. The market's
log-loss is 0.6111; the model's is 0.6492. The market is the better forecast.
The rule bets precisely where the model most disagrees with it, which is
precisely where the model's own error is most likely to be large and positive.
It is a machine for finding the model's mistakes and staking money on them.

**Why this matters more than the size of the number:** it redirects the work.
A miscalibrated rating engine is an argument for more Elo tuning. A biased
selection rule is not -- no parameter reaches it. Run 3 concluded "Elo
parameter tuning is exhausted, the next direction is adding information". That
conclusion survives, but for a different reason than it gave.

## Does Elo know anything the closing line doesn't?

The sharpest version of the project's central question, and it had not been
asked directly. Score `w*model + (1-w)*market` across w, against the de-vigged
closing line:

| | NFL 2021-24 | EPL |
|---|---|---|
| best w | **0.00** | **0.00 on 5 of 6 holdout seasons** |
| log-loss monotone in w | **yes** | yes on those 5 |
| best improvement | −0.0000 | 2025-26 only: +0.00018, CI **[−0.0021, +0.0017]** |

**Every weight on the model makes the forecast worse.** Not "not enough to
beat the vig" -- monotonically worse, with w=0 optimal and the do-nothing
baseline always available. The one holdout that produces a positive weight
produces an improvement of 0.0002 whose bootstrap interval straddles zero
four times over.

A parameter sweep can luck into a good log-loss; this cannot. The curve is
smooth in w and w=0 is always on it. 150 configs failing to beat the market
was consistent with "the right config has not been found". This is not.

**Nothing adopted. `live_enabled` stays false everywhere** -- now on a sharper
basis than "no config won yet".

## The most tempting number produced today

**+10.19% ROI**, NFL, at blend weight w=0.05.

It is on **32 bets**, its 95% interval is **[−73.9, +94.3]**, and it comes
from a weight that log-loss says is **strictly worse than betting nothing**.
It is the single most quotable figure in the run and it means nothing at all.

`summarize_blend` now reports every positive-ROI weight with its own log-loss
delta and interval attached, and a test pins that, because this number will
be regenerated on every future run and will be tempting on every one of them.

## EPL's +8.27% is one draw from a negative distribution

Run 3 reported EPL 2025-26 at +8.27% ROI (t=0.84, 282 bets) -- the project's
only encouraging figure. Re-run with each season in turn as the holdout, same
model, same protocol:

| holdout | log-loss | bets | win% | ROI | 95% CI |
|---|---|---|---|---|---|
| 2020-21 | 0.6146 | 357 | 30.8% | −11.76% | [−28.5, +5.0] |
| 2021-22 | 0.5960 | 366 | 28.7% | −6.57% | [−26.0, +12.8] |
| 2022-23 | 0.6372 | 311 | 32.5% | −12.19% | [−28.3, +4.0] |
| 2023-24 | 0.5943 | 346 | 24.6% | −19.35% | [−37.0, −1.7] |
| 2024-25 | 0.6071 | 304 | 33.6% | −5.12% | [−23.8, +13.6] |
| **2025-26** | 0.6351 | 282 | 35.8% | **+8.27%** | [−11.1, +27.6] |

**1 of 6 positive. Pooled −8.30%**, essentially identical to NFL's −8.21%. sd
across holdouts 9.33pp. The +8.27% is the best of six draws from a
distribution centred near −8%, and the season that produced it has the
*second-worst* log-loss in the table -- the better-calibrated seasons lost
more money, which is run 3's `corr(log-loss, ROI) = +0.59` again.

The figure was never presented as validated. It should now be treated as
retired rather than merely uncelebrated.

## Two traps, caught in the code written to catch traps

Both are documented failure modes of this project, and both reappeared inside
the module diagnosing them, in the same session.

**1. The holdout was an in-progress season.** `epl_sides` first took "the last
season" as the holdout. The last season is 2026-27, of which 30 games have
been played. On those 30 games it reported `model_adds_information: true` with
**w\* = 0.75** -- a clean reversal of the real finding. `cli._load_games`
carries a docstring warning about this exact mistake, written by an earlier
run that made it. Now holds out the last *complete* season (200+ games) and
refuses if none exists.

**2. I called 0.0002 "information".** `summarize_blend`'s
`model_adds_information` was a bare sign test on log-loss, so EPL's 2025-26
improvement of +0.00018 tripped it. This project's own standing rule is that a
bare ROI is not a result. A bare log-loss difference is not one either. The
best weight now carries a bootstrap interval resampled over games; that
improvement's is [−0.0021, +0.0017].

The pattern across runs 2, 3 and 4 is now four for four: a value that was not
what the surrounding code assumed it was. String-sorted `week`. A
`commence_time` that was an expiry. A 30-game "season". A significance claim
with no significance in it.

## The committed data was rewriting itself on every read

Not a modelling bug, and it changes no published number, but it is the same
shape as the others.

**pandas' default CSV float parser is not correctly rounded.** It reads a
stored `1.3690036900369003` back as `...005`. So the committed tables did not
survive a read/write cycle: **585 of 2,499 NFL rows drifted in the last bit on
every refresh**, with no upstream change behind them, while `ingested_at`
restamped the other 1,914.

At 1e-16 the numbers are irrelevant. Two consequences are not:

1. **It made `git diff` useless on the data.** Today's refresh carried six
   genuine week-1 line moves (BUF/HOU, CHI/CAR, CLE/JAX, DAL/NYG, MIA/LV,
   WAS/PHI). They were found only by scripting a column-by-column comparison,
   because the diff reported all 2,499 rows as changed. Review in this repo
   *is* reading diffs, so noise at that volume is indistinguishable from no
   review at all.
2. **`data/snapshots/` is the project's one irreplaceable asset, and reading
   it was altering it.**

Every read of a committed CSV now uses `float_precision="round_trip"`, and
`write_processed` keeps the stored row verbatim when the refreshed row says
the same thing. That refresh diff is now six rows. Pinned by a test that
writes, reads and rewrites a table and asserts the file is byte-identical.

NFL 2018-2024 still reproduces at −8.21% ROI / 0.6518 log-loss, so nothing
published moves.

## Bets

**Nothing settled this run.** The only two completed 2026 NFL games are
NE@SEA (no bet) and SF@LA (settled run 3). 35 pending bets, 35 unresolved --
the week-1 slate starts 2026-09-13.

**35 new shadow bets logged** (24 NFL, 11 EPL) from today's board. The ledger
holds **1 settled, 70 pending, 30 void**. Headline win rate and ROI remain
undefined, correctly, at 0 live bets.

Today's board is the live version of the audit: the NFL model flagged **24 of
56 fillable contracts (42.9%)** as +EV, with claimed edges up to **+52.8%**,
and **58 of the 70 open bets** sit on sides the market prices below even
money. A model finding a 3% edge on two contracts in five of a regulated
exchange is not finding edge. It is describing itself.

### A pre-registered prediction

These are logged as evidence, not as picks, and they make the audit
falsifiable:

| | claimed by model | selection-corrected |
|---|---|---|
| NFL (49 bets, mean claim 0.448) | 21.9 wins | **15.2** |
| EPL (21 bets, mean claim 0.363) | 7.6 wins | **6.7** |
| **total (70)** | **~29.6 wins** | **~21.9 wins** |

If these settle near 30, the audit is wrong. Near 22 and the market is pricing
them correctly while the model books the difference as edge. Writing it down
before the games are played is the only version of this that counts.

## Data sources

| Source | Status |
|---|---|
| nflverse | Live. 2,499 games, 2,229 played. 2026: 2 of 272 complete, unchanged. |
| football-data.co.uk | Live. 2,690 games. E0 2026-27 still at 30 played. |
| Kalshi REST | Live. 120 contracts captured (60 NFL, 60 EPL). |

Liquidity gate: 57/60 NFL fillable, 37/60 EPL -- the standing EPL thin-book
pattern. No new completed games in either league since run 3, so there was
nothing to backfill; the six changed NFL rows are line moves on unplayed
week-1 games, not revisions to history.

**Escalations: none.** The Odds API stays rejected on run 2's reasoning,
football-data.org's key stays unnecessary per run 3. Neither is an open
question and neither will be carried forward again.

## State

| | |
|---|---|
| Live bets | **0.** Headline win rate and ROI: undefined, correctly |
| Shadow bets | 1 settled (1 win), 70 pending, 30 void |
| Usable CLV readings | **0** |
| Models deployed | None. `live_enabled` false everywhere |
| Tests | 113 pass, network-free |
| Configs beating the market, cumulative | **0 of 150** |
| Blend weights beating the market | **0** (NFL), **0 of 6 holdouts** at significance (EPL) |

Elapsed since the first bet: about 26 hours. Still pipeline archaeology, not
evidence about markets. The one settled bet is still a single underdog win at
2.78, still the most misleading possible first result, and still worth
re-reading run 3's paragraph about it before quoting the 100% win rate.

## Process note

The stored scheduled prompt still contains "do not post, send, change, or
delete anything". CLAUDE.md overrides it for repository work as of
2026-09-11, so this run captured odds, logged bets and committed. Flagging it
here as that note requires: the stored prompt lives at account level and
cannot be edited from inside a session. It also still contains the unfilled
`[which data sources?]` placeholder, answered by the table in CLAUDE.md.

## Open questions / next steps

- **The selection gap is the thing to attack, not the ratings.** A model does
  not need to beat the market on every game to be bettable -- it needs to be
  right about *which* games it disagrees on. Nothing measured so far suggests
  Elo is.
- **Do not "fix" this with a price or edge filter without a real test.** Every
  price bucket in the NFL backtest is ROI-negative (best: −3.90% at market
  ≥0.50, CI [−18.9, +11.1]). A filter that improves backtest ROI here is
  selecting on noise -- the same trap as the +10.19%.
- **Build the Kalshi-venue backtest.** Carried from run 3, still the
  highest-value work left, still not done. `backtest/engine.py`'s docstring
  still points at `backtest.kalshi_engine`, which still does not exist.
  Everything measured is model-vs-sportsbook; we would trade on an exchange.
- **Audit the remaining joins and sort keys.** Now four bugs of this shape,
  not two.
- The 5% relative-width liquidity gate remains unvalidated against realized
  fill quality.
- EPL kickoff times for pending fixtures remain unavailable until played.
- **Standing reminder:** 0 live bets, 1 settled shadow bet, 1 win. A 100% win
  rate on n=1 is not a signal. 70 pending bets will not be one either.
