# Scheduled run 5 -- the exchange is the expensive venue, not the cheap one

_2026-09-12_

## Headline

**Every ROI this project has published is model-vs-sportsbook. We would trade
on Kalshi. Moving the historical sample to that venue costs 3.3 points of ROI
-- it does not save them.**

Runs 3 and 4 both carried "build the Kalshi-venue backtest" forward as the
highest-value work left, and `engine.py`'s docstring has pointed at a
`backtest.kalshi_engine` that did not exist since before run 2. It exists now.

I expected it to flatter the model. Kalshi's book is about a quarter as wide
as a sportsbook's margin, so the obvious prior was "the exchange is cheaper,
the model's loss shrinks, maybe the gate gets closer". The opposite is true,
and the reason is specific enough to be worth stating precisely.

| NFL 2018-2024 | n | win% | ROI | 95% CI |
|---|---|---|---|---|
| sportsbook (real) | 1625 | 32.86% | **−8.21%** | [−15.4, −1.1] |
| Kalshi (simulated) | 1556 | 32.46% | **−11.48%** | [−18.5, −4.4] |

## What is real here and what is simulated

This distinction is the whole integrity of the section, so it goes first.

**Real, measured this run:**

- Kalshi's de-vigged mid against the sportsbook's de-vigged fair, on the same
  28 games. **corr 0.9955**, mean diff +0.0011, mean |diff| **0.0126**, max
  0.0372. The two venues make the same forecast.
- The venue's cost of entry. Kalshi's overround at the ask is **+1.04%**
  against the sportsbook's **+4.28%** on the identical games.
- The half-spread, from 672 captured NFL quotes and 540 EPL: median **0.5c**,
  and flat at half a cent across *every* price bucket from 10c to 90c.

**Simulated:** the 2018-2024 re-run. Kalshi's public API serves the current
board, not a price history, and this project has been capturing snapshots for
three days. A Kalshi backtest of 2018-2024 does not exist and cannot be
manufactured. What the module does instead is substitute the *measured*
microstructure into the historical sample, and the agreement figure above is
what licenses that substitution rather than assuming it. Every result dict
carries `simulated_at_venue: True` so nothing downstream can quote it as an
observed exchange return.

## Why the cheaper venue is the more expensive one

A sportsbook's vig is proportional, so its toll is flat as a fraction of your
stake. Kalshi charges a fee that is quadratic in *notional* -- which makes it
regressive in *stake*, because fee/stake = rate × (1 − price).

Measured across the 1,625 bets the NFL rule actually places:

| fair price of the side bet | n | sportsbook toll | Kalshi toll | of which fee |
|---|---|---|---|---|
| under 0.15 | 84 | 3.47% | **10.63%** | 6.37% |
| 0.15 – 0.30 | 564 | 3.27% | 7.58% | 5.42% |
| 0.30 – 0.45 | 678 | 3.10% | 5.79% | 4.42% |
| 0.45 – 0.60 | 257 | 3.06% | 4.37% | 3.40% |
| 0.60 – 0.80 | 42 | 3.18% | 3.30% | 2.52% |
| **overall** | **1625** | **3.17%** | **6.37%** | **4.66%** |

The sportsbook column barely moves. The Kalshi column triples.

And the bet rule lives at the expensive end: **88.6% of its bets are on sides
priced below even money**, mean fair price **0.342**. So this compounds run 4's
finding rather than sitting beside it. The rule's longshot bias is not only
where the model's errors concentrate -- it is also the single most expensive
place to trade on the venue we would trade on.

Decomposed: the exchange's tighter book is worth **+2.11pp**, the fee gives
back **−5.38pp**, net **−3.27pp**.

## The number I could not verify, and what I did about it

Kalshi's API confirms the fee's *shape*: `series/KXNFLGAME` and
`series/KXEPLGAME` both report `fee_type="quadratic_with_maker_fees"` and
`fee_multiplier=1`. It does not expose the coefficient. No market, series or
exchange endpoint carries it, the documentation page is a JavaScript shell
that serves no text to a plain fetch, and the PDF returned HTTP 429.

So the rate is a parameter, `FEE_RATE_IS_VERIFIED` is `False`, and the run
reports the whole range rather than one row:

| fee rate | n bets | ROI | 95% CI | significant |
|---|---|---|---|---|
| 0.000 | 1724 | −6.10% | [−13.0, +0.80] | no |
| 0.010 | 1704 | −7.17% | [−14.1, −0.25] | yes |
| 0.035 | 1641 | −9.53% | [−16.5, −2.56] | yes |
| **0.070** | 1556 | **−11.48%** | [−18.5, −4.41] | yes |
| 0.100 | 1487 | −12.96% | [−20.1, −5.83] | yes |

**The conclusion does not depend on the constant.** NFL ROI is negative at
every rate including zero. The deployment gate stays shut on evidence that
survives the thing I could not read.

What *is* fee-dependent is the direction of the venue comparison: below about
2% the exchange beats the sportsbook, above it the sportsbook wins. That is
worth knowing and it is not worth acting on until someone can read the number.

## EPL's retired +8.27% is −2.85% at the exchange

Run 4 retired that figure on holdout rotation -- 1 of 6 seasons positive,
pooled −8.30%. The venue is an independent second strike on it:

| EPL 2025-26 holdout | n | win% | ROI | 95% CI |
|---|---|---|---|---|
| sportsbook | 282 | 35.82% | +8.27% | [−11.1, +27.6] |
| Kalshi (simulated) | 283 | 36.40% | **−2.85%** | [−20.1, +14.5] |

Neither is significant, and EPL *is* fee-dependent across the range (+11.5% at
zero to −5.7% at 0.10), so this is a weaker result than NFL's and is recorded
as one. It is corroboration, not a new finding: the figure was already retired.

## The live recommender has been ignoring the larger of the two costs

`recommend.py` opens with a careful paragraph about pricing at the ask rather
than the mid, because half a spread is "the same order of magnitude as the
edges we're hunting for". That paragraph is right and it understates its own
subject. The spread takes ~1.7% of stake. The fee takes ~4.7%. The module
prices the first and has never priced the second.

So every edge in the ledger is overstated by roughly the fee. On the 72 open
bets, by **5.39pp** on average.

`edge_after_fee_pct` and `fee_assumption` are now columns on every row, and
the existing rows are backfilled.

**It is reported, not enforced**, and the second reason matters more than the
first:

1. The rate is unverified, and enforcing a threshold against a number I could
   not read writes that number into the permanent bet record.
2. **It would break a pre-registered prediction that settles tomorrow.** Run 4
   wrote down, before any game was played: ~30 wins if the model's claimed
   edges are real, ~22 if the selection audit is right. The 70 open bets *are*
   that test. The week-1 slate starts 2026-09-13. Re-pricing them into a
   different population the day before they resolve would quietly dispose of
   the one falsifiable commitment this project has made -- and it would do it
   in the direction of making the model look better, since the bets the fee
   cuts are the longshots the audit predicts will lose.

The backfill is therefore strictly *derived*, not a re-pricing:
`market_odds_decimal` is 1/ask by construction, so the fee and the fee-
inclusive edge follow from what each row already recorded. No price, stake,
status, selection or `pricing_version` moves.
`test_backfill_after_fee_is_derived_not_a_repricing` asserts each of those
columns is untouched, and `test_fee_does_not_change_which_bets_are_flagged`
is what should fail first when a future run does move the threshold.

What it changes about the open book: **6 of 72** bets would no longer clear 3%
after the fee, and **2** go outright negative. The other 66 carry claimed edges
large enough that a 5-point haircut barely registers -- which is less
reassuring than it sounds, given run 4 measured those claims as overstated by
13.7 points.

## The fifth bug of the same shape

The first version of the venue-agreement join matched the Kalshi board to the
stats table on `(home_team, away_team)`. That pair is not unique -- the same
fixture recurs every season -- so **30 Kalshi events fanned out to 131 rows**,
matching today's contracts against games from 2020, 2021 and 2024. It reported
a correlation of **0.4572** and a maximum disagreement of **53 percentage
points**, and I nearly wrote it down as "the two venues disagree substantially".

The correct join disambiguates by kickoff. `ingest.kickoff.resolve_kickoff`
exists for exactly this and was written by run 3 after the same class of
mistake. Corrected: 28 rows, corr 0.9955.

The tally is now five for five: a string-sorted `week`; a `commence_time` that
was an expiry; a 30-game "season"; a significance claim with no significance
in it; and now a join key that was not a key. Every one of them produced a
plausible-looking aggregate. The only reason this one was caught is that 0.46
was *surprising* -- and a wrong number that had happened to look reasonable
would have gone straight into the journal.

Pinned by `test_agreement_join_is_kickoff_disambiguated`, which builds a table
where one fixture recurs in three seasons at deliberately absurd prices.

## One loop, two venues

Both venues run through the *same* walk-forward loop in `engine.py`, via a
`pricer` argument, rather than a second copy of it. This file's own history is
the argument: the week-ordering bug lived in the backtest and the live model
separately and had to be found and fixed twice.

The default path reproduces **−8.208908995992267%** and log-loss
**0.6517617405253826** exactly, and `test_pricer_default_matches_book` pins it
bet-for-bet rather than to a rounded figure.

## Bets

**Nothing settled this run.** The first NFL week-1 games kick off 2026-09-13;
today's EPL fixtures expire at 17:00 UTC, hours after this run. 72 pending, 72
unresolved.

**3 new shadow bets logged.** The recommender ran twice against today's board
and skipped 35 duplicates, which is the dedupe key working: same contracts,
same model version, same pricing version as yesterday. The ledger holds **1
settled, 72 pending, 30 void**. Headline win rate and ROI remain undefined,
correctly, at 0 live bets.

Today's board: NFL flagged **25 of 56 fillable contracts (44.6%)** with claimed
edges to +49%; EPL **11 of 37 (29.7%)**. Unchanged in character from run 4, and
unchanged in what it says -- a model finding a 3% edge on nearly half a
regulated exchange's board is describing itself, not the market.

**Run 4's pre-registered prediction is untouched and resolves from tomorrow:**

| | claimed by model | selection-corrected |
|---|---|---|
| NFL (49 bets) | 21.9 wins | **15.2** |
| EPL (21 bets) | 7.6 wins | **6.7** |
| **total (70)** | **~29.6** | **~21.9** |

## Odds capture

Two captures this run, 120 contracts each. The second matters: today's EPL
slate kicks off around 14:00 UTC and this run began at 06:00, so those are
pre-kickoff prices on games that settle within hours. A missed window there is
permanently missing data and would cost the CLV reading on six fixtures.

| Source | Status |
|---|---|
| nflverse | Live. 2,499 games, 2,229 played. 2026: 2 of 272 complete, unchanged. |
| football-data.co.uk | Live. 2,690 games. E0 2026-27 still at 30 played. |
| Kalshi REST | Live. 240 contracts captured across two passes. |

The refresh moved **22 rows, all line moves on unplayed 2026 games** -- and the
whole diff was 27 lines, which is what run 4's round-trip fix bought. Four
week-9 games churned their lines in and out (CLE@NO and NYJ@KC gained a line,
DAL@IND and NYG@PHI lost theirs); that is upstream volatility on distant
fixtures, not a revision to history. No new completed games in either league,
so there was nothing to backfill.

Liquidity gate: 54-56 of 60 NFL fillable, 35-37 of 60 EPL -- the standing EPL
thin-book pattern.

**Escalations: none.** The Odds API stays rejected on run 2's reasoning;
football-data.org's key stays unnecessary per run 3. Neither is an open
question and neither is being carried forward.

## State

| | |
|---|---|
| Live bets | **0.** Headline win rate and ROI: undefined, correctly |
| Shadow bets | 1 settled (1 win), 72 pending, 30 void |
| Usable CLV readings | **0** |
| Models deployed | None. `live_enabled` false everywhere |
| Tests | **139** pass, network-free |
| Configs beating the market, cumulative | **0 of 150** |
| Venues at which the model beats the market | **0 of 2** |

Elapsed since the first bet: about 44 hours. The one settled bet is still a
single underdog win at 2.78 and still the most misleading possible first
result.

## Process note

The stored scheduled prompt still contains "do not post, send, change, or
delete anything". CLAUDE.md overrides it for repository work as of 2026-09-11,
so this run captured odds, logged bets and committed. Flagging it as that note
requires: the stored prompt lives at account level and cannot be edited from
inside a session. It also still contains the unfilled `[which data sources?]`
placeholder, answered by the table in CLAUDE.md.

## Open questions / next steps

- **The pre-registered prediction resolves from 2026-09-13.** This is the
  first real evidence the project will have produced. Nothing about the
  pricing pipeline should move until it has, and the next run's first job is
  to settle it and report the count against ~22 and ~30 honestly, whichever
  way it falls.
- **Then move the edge threshold onto the fee-inclusive number** -- as a `p3`
  pricing bump with an explicit re-pricing of open bets, not a quiet change of
  formula. `test_fee_does_not_change_which_bets_are_flagged` is the tripwire.
- **`edge_threshold_pct: 3.0` has never been derived from anything.** It
  predates any measurement of what either venue costs. At the rule's typical
  price of 0.34 the venue takes 6.4% of stake, so a 3% threshold is asking the
  model to beat the market's fair price by roughly 9.4% relative before the
  bet is worth making. Whether that threshold is right is now answerable and
  has never been asked.
- **The selection gap remains the thing to attack** (run 4). Nothing this run
  found touches it; the venue result makes it more expensive, not less real.
- Kalshi's fee coefficient is worth one more attempt from a future run -- the
  docs page needs JS, but an authenticated endpoint or the contract-terms PDF
  may carry it. Not an escalation: no account or payment is involved.
- The 5% relative-width liquidity gate remains unvalidated against realized
  fill quality.
- **Standing reminder:** 0 live bets, 1 settled shadow bet, 1 win. A 100% win
  rate on n=1 is not a signal, and 72 pending bets will not be one either.
