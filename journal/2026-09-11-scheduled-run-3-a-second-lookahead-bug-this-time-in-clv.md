# Scheduled run 3 -- a second lookahead bug, this time in CLV

_2026-09-11_

## Headline

**A second lookahead bug, in the one metric the project trusts most.**

`ingest/kalshi.py` populated a column called `commence_time` from Kalshi's
`expected_expiration_time`. That timestamp is not kickoff. Measured against
nflverse across all 31 NFL events on the 2026-09-10 board, it lands **3 hours
late on 27 of them and 6 hours late on the other 4. Never on time.** Kalshi
has no kickoff field at all -- `occurrence_datetime` is byte-identical to
`expected_expiration_time`.

Two consumers treated it as kickoff:

| Path | Status before the fix |
|---|---|
| `closing_quote_before()` (candlesticks) | **Leaking.** Demonstrated live. |
| `settle._closing_odds()` (snapshots) | Clean, by luck alone. |

The demonstration: `closing_quote_before()` for SF @ LA returned **bid 0.98 /
ask 0.99**, a candle stamped 03:00 UTC. Kickoff was 00:35 UTC. The game was
decided. Against an entry of 0.36 that is a CLV of roughly **+175%**,
manufactured entirely by the clock.

Why this is worse than the `week` bug that preceded it: an in-play price
already knows the result, so contaminated CLV is not merely noisy -- it is a
**restatement of win/loss wearing the costume of a skill measurement**. It
would have read as enormous closing-line skill, and it would have read that
way *precisely when the model won*. CLV is the metric this project nominated
as its better short-run signal specifically because win rate is noisy over
tens of bets. It would have been the most convincing wrong number available.

The settle path was clean only because no snapshot has ever landed inside a
game window (max `fetched_at` 2026-09-10T17:59, before every kickoff). Note
the trap in that: **following the project's own standing advice to snapshot
more often is what would have set it off.** The README and CLAUDE.md both push
for higher cadence; higher cadence plus a 3-6h-late cutoff equals in-play
prices in the CLV column.

Same class as the `week`-as-string bug, and that is not a coincidence worth
shrugging at. Both were a mislabelled field feeding the one function whose
docstring promised no leakage, with plausible-looking aggregates on top. Run 2
wrote `closing_quote_before()` *specifically* to avoid in-play prices and
documented the hazard in its own docstring -- then handed it the wrong clock.
Naming a variable after what you wish it contained is apparently this
project's recurring failure mode.

## The fix

Kickoff now comes from the stats source or it does not come at all.

- `ingest/kickoff.py` (new) resolves true kickoff by joining to the committed
  game tables, with a +/-2 day tolerance to absorb ticker-date skew.
- `ingest/nfl_stats.py` keeps `gameday` + `gametime` as `kickoff_utc`
  (America/New_York -> UTC).
- `ingest/soccer_stats.py` keeps football-data.co.uk's `Time` column, which was
  previously parsed and thrown away (Europe/London -> UTC). **No new data
  source and no API key was needed -- the column was already in a free feed we
  were downloading and discarding.** This retires the standing suggestion that
  football-data.org's key might be needed for fixture metadata.
- The Kalshi field is renamed `expiration_time` everywhere, in the snapshot
  schema, the ledger and the DB. Old snapshot CSVs are normalised on read
  rather than rewritten -- they are the irreplaceable asset.
- `settle._closing_odds()` cuts at the resolved kickoff and **returns None when
  it cannot resolve one.** No CLV is a missing number; fake CLV is a wrong
  conclusion. Settlement records a `clv_missing_reason` so the two causes stay
  distinguishable.

Verification: expiration-minus-kickoff is now measured rather than assumed, and
is positive on all 31 events (min 3.0h, max 6.0h). `tests/test_kickoff.py`
pins it, including a direct regression that feeds the settle path both a
pre-kickoff 0.36 and an in-play 0.99 and asserts it takes the 0.36.

Tests 83 -> 93.

**No published number changes.** No NFL CLV had been computed from
candlesticks, and the snapshot record contains no in-play rows. The bug was
caught before it produced a result, which is the one piece of luck in this
entry.

## Two stale EPL shadow bets, voided

The 12 pending EPL bets reproduce **exactly** under the pre-run-2 liquidity
gate (absolute checks only) and yield 10 under today's gate. The two that
disappear are both Hull @ Chelsea:

| Bet | Selection | Model | Market fair | "Edge" |
|---|---|---|---|---|
| `2f10be15` | away (Hull) | 0.245 | 0.074 | **+206.3%** |
| `4b82dfa6` | draw | 0.246 | 0.143 | **+63.7%** |

The Hull contract is 6.7-7.7% wide (bid 0.06-0.07 / ask 0.07-0.08) and the
relative-width gate rejects it at >5%. With that side unfillable the three-way
de-vig has no complete book, so the draw is unpriceable too -- it fails as
collateral damage rather than on its own numbers.

These were the two largest EPL "edges" in the ledger. They drag the pending
EPL mean from **16.7% to 36.5%**. A +206% edge against a regulated exchange is
a statement about the book being 7.7% wide, not about the market being wrong.
Both voided.

**The structural gap that let them survive.** The 2026-09-10 fix voided and
re-priced the NFL rows of the same vintage -- but it keyed on `model_version`,
and NFL's happened to move (v1 -> v2) for unrelated reasons. The soccer model
version never moved, so its stale rows were silently treated as current. The
void was correct by accident on one sport and absent on the other.

Fixed properly: `PRICING_VERSION` now versions everything between a model
probability and a logged bet -- the liquidity gate, the de-vig, ask-vs-mid, the
edge formula -- independently of the model, and it is part of the ledger dedupe
key. A pricing change now invalidates open rows on its own authority.

Audit of all 38 pending rows against today's gate: exactly 1 fails outright
(the Hull away contract), 1 more is unpriceable as a consequence, and the
remaining 36 are defensible as priced. So the p1 rows that pass are kept rather
than re-priced -- re-pricing them would reset the evidence clock in exchange
for nothing, which is the same reasoning run 1 used for not adopting its
marginally-better configs.

## First settled bet -- and why its CLV is worthless

**SF @ LA, away (SF), shadow, `nfl-elo-v2`. WON.** SF 27 - LA 7.

| | |
|---|---|
| Model prob / fair odds | 0.3998 -> 2.501 |
| Market de-vigged fair | 0.355 -> 2.817 |
| Paid (ask) | 0.36 -> **2.778** |
| Edge | +11.06%, clears the 3% threshold |
| P&L | +1.778 on 1.0 staked |
| CLV | **0.0%, and the number is vacuous** |

The CLV is not a neutral reading. The last snapshot before kickoff was
2026-09-10T17:59, **7.5 hours pre-kickoff**, so entry price and "closing" price
are literally the same captured row. First bet ever settled, and its closing
line value is unmeasurable. That is the cost of the snapshot gap, landing
immediately and on the only bet available to land on.

Worth saying plainly: **this is the most misleading possible first result.**
The model's documented failure mode is under-dispersion that makes it overrate
underdogs. Underdogs win roughly a third of the time, and when they do the
payoff is large. A single underdog win at 2.78 is exactly the shape of a false
positive. One bet. It says nothing. It will still be tempting to remember it.

Also of note: the corrected cutoff did **not** change this bet's closing price
-- both the old (06:35Z) and new (00:35Z) cutoffs select the same 17:59
capture, because no snapshot exists in between. The fix made the number correct
by construction rather than correct by accident. Those look identical in a CSV
and are not the same thing.

## Backtests -- run 2's open ROI item, closed

**Reproducibility first.** All four corrected NFL rows reproduce to the digit
(-8.21% / -10.38% / -8.64% / -9.51%; log-loss 0.6518 / 0.6389 / 0.6516 /
0.6387), as does the EPL 2025-26 holdout (log-loss 0.6351, ROI +8.27%,
t = 0.84, 282 bets, 35.8%).

**48-config NFL sweep, ROI recomputed under corrected chronology.**
Test seasons 2021-24, n = 1139. Market de-vigged closing log-loss **0.6116**.

| Question | Answer |
|---|---|
| Configs beating market on log-loss | **0 / 48** |
| Configs with ROI > 0 | **0 / 48** |
| Configs with ROI significantly > 0 | **0 / 48** |
| ROI range | **-12.21% to -7.38%** (median -9.57%) |
| Best log-loss | 0.6396 (k=20, ha=40, MOV), ROI -11.99%, CI [-20.8, -3.2] |

**Nothing adopted.** The correction changes no conclusion; it makes every cell
worse, which is what was expected and is why it was worth doing anyway.

Three things fall out:

1. **corr(log-loss, ROI) = +0.59.** Lower log-loss goes with *lower* ROI: the
   better-calibrated configs lose more money. This is direct evidence that ROI
   is not a proxy for skill at this sample size, and it is the standing
   argument for writing the deployment gate on log-loss.
2. **MOV confirmed across the whole grid**, not just the four headline rows:
   mean log-loss -0.005, mean ROI -1.25pp. Improves calibration, worsens
   returns. Stays unadopted.
3. **Run 1's `home_advantage=55` claim should be softened.** Under corrected
   chronology the means are 0.6460 (ha=55) vs 0.6451 (ha=25 and ha=40) -- a
   0.001 gap, the same magnitude as the chronology correction itself. Run 1
   called it consistent; it is not robust enough to describe that way.

**A reproducibility failure worth recording.** Run 1's sweep script was never
committed, and my reconstruction does not match it: I get a best of 0.6396
where run 1 reported 0.6459, and run 1's stated best config scores 0.6412 here.
Neither number is provably wrong, which is the problem. A project whose central
discipline is "backtest before adopting, and publish the backtest even when it
is bad" had its headline backtest living in a scratch file. Now committed as
`backtest/sweep.py` + `cli sweep-nfl`, with the protocol spelled out in the
module docstring.

## Data sources

| Source | Status |
|---|---|
| nflverse | Live. 2026: 2 of 272 complete. Now also supplying `gametime`. |
| football-data.co.uk | Live. E0 2026-27 at 30 played. Now also supplying `Time`. |
| Kalshi REST | Live. 30 NFL + 20 EPL events, all two-sided. |

One new completed game since the last run (SF 27 - LA 7), so there was nothing
meaningful to backfill. Both processed tables were rebuilt anyway to carry
`kickoff_utc`: nfl_games 2,499 rows and epl_games 2,690 rows, kickoff present
on **100% of both**.

EPL kickoffs resolve to `None` for the 10 pending fixtures, which is correct
and not a bug: football-data.co.uk publishes only completed matches, and CLV is
computed at settlement, by which point the match is in the feed. Verified that
the gap is unplayed fixtures rather than a team-name mismatch -- 0 of the
pending EPL team names are unknown to the stats table, and a completed fixture
resolves correctly.

Escalations: **none.** The football-data.org key is now definitively
unnecessary (see "The fix"). The Odds API remains rejected on run 2's
reasoning.

## State

| | |
|---|---|
| Live bets | **0.** Headline win rate and ROI: undefined, correctly |
| Shadow bets | 1 settled (1 win), 35 pending, 30 void |
| Usable CLV readings | **0** |
| Models deployed | None. `live_enabled` false everywhere |
| Tests | 93 pass, network-free |
| Configs beating the market, cumulative | **0 of 150** |

Elapsed since the first bet: about 12 hours. Everything here remains pipeline
archaeology, not evidence about markets.

## Process change

The owner moved scheduled runs off read-only: runs now capture, commit and
settle rather than only reporting, and snapshot cadence can rise as needed.
Recorded in CLAUDE.md.

Sequencing mattered here and is worth noting for its own sake. Raising snapshot
cadence was the requested change; doing it first would have converted the
latent `settle._closing_odds()` leak into a live one, because more frequent
capture is exactly what puts an in-play row in the snapshot store. The
timestamp fix had to land first. A correct change in the wrong order is still
a bug.

## Open questions / next steps

- **Build the Kalshi-venue backtest.** Still the highest-value work left, and
  still not done. Note `backtest/engine.py`'s docstring already points at
  `backtest.kalshi_engine`, which does not exist -- the docstring reads as
  though it were finished. Everything measured so far is
  model-vs-sportsbook; we would trade on an exchange.
- **Audit the remaining joins and sort keys.** This is now **two** bugs of the
  same shape. Two is a pattern, not a coincidence. Every column whose name
  asserts a semantic (`*_time`, `*_date`, `week`, `season`) deserves an
  explicit check that it holds what the name claims.
- **The 5% relative-width gate remains unvalidated** against realized fill
  quality. It has now voided real bets, which raises rather than lowers the
  bar for justifying it.
- EPL kickoff times for *pending* fixtures are unavailable until the match is
  played. Harmless for CLV (computed at settlement) but it means a pre-game
  kickoff check is impossible for soccer. If that ever matters, it needs a
  fixtures source.
- Elo parameter tuning is exhausted: 150 configs, none beat the market. The
  next direction is adding information (QB/injury signals for NFL), not
  retuning.
- **Standing reminder:** 0 live bets, 1 settled shadow bet, 1 win. A 100% win
  rate on n=1 is not a signal, and the next few weeks of results will not be
  one either.
