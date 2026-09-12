# Scheduled run 6 -- the recommender was betting games already in progress

_2026-09-12, 15:02-15:30 UTC (run 5 was 06:02-06:17 the same morning)_

## Headline

**Six EPL fixtures were about an hour into play when this run started. The
recommender priced a pre-game Elo against their live quotes, called the result
an edge of up to +278%, and wrote two of them into the ledger.** Nothing in
the pipeline looked at the clock.

Two of this run's three findings are about time, and they point in opposite
directions: the recommender did not know a game had *started*, and the settler
could not find out when a game had *kicked off*. Both were silent.

## Finding 1: a pre-game model priced against in-play markets

The first pass of `recommend` this run produced these, among others:

| fixture | pre-game ask | ask at 15:11 | model | claimed edge |
|---|---|---|---|---|
| Aston Villa (v Nott'm Forest) | 0.44 | **0.13** | 0.492 | **+278.3%** |
| Chelsea (v Hull) | 0.80 | **0.41** | 0.509 | +24.2% |
| Liverpool (v Fulham) | 0.66 | **0.52** | 0.615 | +18.2% |

That is not a mispricing, it is the model not knowing the score. And the error
has a **sign**, which is what makes it worse than noise: the market marks down
whichever side is currently losing, the pre-game model does not follow, so the
apparent edge lands on the losing side essentially every time. A rule that
bets it is a rule that systematically buys teams that are behind. It would
have produced a stream of losses later attributed to the model rather than to
the pipeline.

Two of them — Liverpool and Chelsea — were logged before I caught it.

**Why nothing flagged it.** `_kickoff_iso` resolved kickoff only to *record*
it; its docstring says "None is acceptable". Kalshi's own `status` field reads
`active` for all 360 captured quotes, in-play ones included, so it cannot be
used to detect this. The liquidity gate passed the quotes because a live
market is liquid — the Chelsea contract had over $1m of volume precisely
*because* it was in play.

**The proof is in our own tape,** not in an assumption about kickoff times.
Across today's captures, the 17:00Z-expiry contracts moved violently while
every other contract on the board sat still:

| expiry | max abs move, 06:02 -> 15:11 |
|---|---|
| **2026-09-12 17:00Z** | **0.57** (Ipswich 0.24 -> 0.81, Crystal Palace 0.52 -> 0.05) |
| 2026-09-12 19:30Z | 0.01 |
| 2026-09-12 22:00Z | 0.02 |
| 2026-09-13 16:00Z | 0.01 |

Nott'm Forest went 0.27 -> 0.61 *between 15:02 and 15:11* — a goal went in
during the run. That is the tape confirming both that those games were live
and that EPL expiry sits 3h after kickoff, which is what the gate now relies
on.

`recommend.partition_in_play` drops these. It is on by default inside both
recommenders rather than an opt-in a caller can forget, and reports
`in_play_skipped` so a gated board is visible instead of silent. Kickoff comes
from the stats source where available; where it is not — which for EPL is
always, see finding 2 — it falls back to expiration minus the sport's largest
measured lag (NFL 6h, EPL 3h), placing the inferred kickoff as early as
possible. Inferring too early costs a betting opportunity; inferring too late
writes an in-play price into a permanent record.

**NFL has been harmless only because the season had not started.** Week 1 is
tomorrow, Sunday games run 17:00-23:30Z, and a scheduled run inside that
window would have done all of this at scale — to the exact slate carrying run
4's pre-registered prediction. This was about 24 hours from becoming the
project's biggest data-integrity problem instead of a two-row one.

### What I did not do: bump `PRICING_VERSION`

The module's own rule is to bump it whenever pricing behaviour changes, and
this changes what gets bet. I did not, and the reason is a measurement rather
than a preference: I audited all 76 open rows against the new gate, and
**exactly 2 fail it — the 2 this run wrote.** Every earlier bet was priced
pre-kickoff.

`PRICING_VERSION` exists to invalidate rows priced under a superseded rule.
There are none. Bumping to `p3` would re-log 74 correctly-priced rows and
dispose of the pre-registered prediction that starts resolving tomorrow, to
fix nothing. The two bad rows are **voided** instead, which is this project's
existing mechanism for withdrawn evidence, with the reason written into the
`notes` column.

## Finding 2: EPL closing-line value was structurally zero, and silent

`settle_pending` computes CLV once, at settlement, and only ever iterates rows
that are still `pending`.

For NFL that is enough. nflverse publishes the whole season's schedule in
advance — 2,499 rows against 2,229 played — so a kickoff is known weeks before
the game.

football-data.co.uk publishes **only completed matches**, and publishes them
late. Its 2026-27 file today holds 30 rows, the most recent dated 2026-09-06.
So an EPL contract finalizes on Kalshi within minutes of the final whistle, at
a moment when no source we hold can say when that match kicked off.
`_closing_odds` then correctly refuses to guess, and the bet settles with
`clv_pct` empty.

**And nothing ever went back for it.** The row is no longer pending, so every
later run skips it. The CLV — which this project's README calls a better
short-run skill signal than win rate — was lost permanently, while every price
needed to compute it sat in the committed snapshots the whole time.

Verified rather than argued: `resolve_kickoff` returns `None` for all six of
today's fixtures right now, and resolves correctly for Arsenal v Chelsea on
2026-09-06, which the table already has.

This one is not a wrong number. It is a number that would silently never have
existed — the failure mode is an empty column, and the per-bet reason string
never surfaced in any aggregate. It is a different defect from the five in
"Known-bad numbers", and it is recorded as its own kind rather than folded
into that tally.

**The concrete cost, had I not caught it today:** 14 EPL bets settle this
evening (expiries 17:00Z, 19:30Z, 22:00Z). They are the first EPL settlements
in the project's history. All 14 have a captured pre-kickoff price, so all 14
now recover their CLV once football-data.co.uk publishes the fixtures. Under
the old code the project's entire first EPL CLV cohort would have gone
missing, and the state table would have kept reporting "usable CLV readings:
0" without anyone learning why.

`backfill_clv` revisits settled rows with no CLV, re-resolves the kickoff, and
fills from the snapshot history. It runs unconditionally after every `settle`:
a recovery pass someone has to remember to invoke is how the number goes
missing in the first place. It fills `kickoff_utc`, `closing_odds_decimal` and
`clv_pct` and touches nothing else — pinned by a test over every other column.

The cutoff is still the true kickoff, never the expiration. A backfill that
reached for expiry would rebuild run 3's lookahead bug one sport over and a
week later; I reintroduced that fallback deliberately and confirmed
`test_backfill_never_falls_back_to_the_expiration` fails, booking a fabricated
CLV off a 95c in-play quote, before restoring the fix.

## Finding 3: a sort key that was two types at once (cosmetic)

`fetch_nfl_games` returns `season` as a **string**; reading the stored CSV back
gives **int64**. `write_processed` concatenates them, so on every refresh its
sort key held both at once and `'2026'` was compared against `2026`. Rows the
refresh changed kept the fetch's string while rows `_keep_unchanged_rows` held
back carried storage's int, so the two groups sorted against each other
instead of interleaving: **267 row positions moved, and 5 real line moves cost
48 changed lines.**

This is the same diff-legibility problem `_keep_unchanged_rows` was built to
solve, reappearing one layer down, in a repo whose review mechanism is reading
diffs.

**It changed no published number, and I checked rather than assuming.** Every
backtest, sweep and live model re-sorts for itself before iterating, and
`read_processed` hands them a column of a single dtype. End-to-end, after the
reordering, the NFL backtest reproduces log-loss **0.6517617405253826** and ROI
**-8.208908995992267%** — digit-for-digit identical to run 5 — and EPL
reproduces **+8.27%**, n=282, CI [-11.1, +27.6]. EPL's table had *no* diff at
all, which is itself confirmation of the diagnosis: EPL seasons are strings on
both sides, so only NFL round-trips str -> int.

Fixed by sorting on `.astype(str)`. Season labels are fixed-width, so a string
sort agrees with the numeric one. Subsequent refreshes are byte-identical.

I am counting this in the bug tally but flagging it as the one member with no
consequence for any result. Padding the count with a cosmetic defect would be
its own small dishonesty.

## Bets

**Nothing settled this run, again.** At 15:02 the EPL 17:00Z slate was mid-match
and NFL week 1 had not started. 74 pending, 0 resolved.

**No new bets logged.** All 30 recommendations after the gate were duplicates
of open rows — the dedupe key working as intended.

Ledger: **1 settled (1 win), 74 pending, 32 void.** Headline win rate and ROI
remain undefined at 0 live bets, which is correct.

**Run 4's pre-registered prediction is intact and starts resolving tomorrow.**
I verified the population rather than trusting it: the bets placed 2026-09-10
and 2026-09-11 are 25+24 = **49 NFL** and 10+11 = **21 EPL**, exactly the 70 the
prediction was written over. The two rows I voided were both written today and
were never part of it.

| | claimed by model | selection-corrected |
|---|---|---|
| NFL (49 bets) | 21.9 wins | **15.2** |
| EPL (21 bets) | 7.6 wins | **6.7** |
| **total (70)** | **~29.6** | **~21.9** |

The first 14 EPL bets resolve tonight, the NFL 49 from tomorrow.

Today's board after the gate: NFL flagged **25 of 57 fillable (43.9%)**, EPL
**5 of 21 (23.8%)**, with 11 EPL contracts gated as in-play and 28 rejected as
illiquid. A model finding a 3% edge on 44% of a regulated exchange's board is
still describing itself, not the market.

## Odds capture

One capture this run, plus the automatic captures `recommend` makes: 6 distinct
NFL and 6 EPL capture timestamps for 2026-09-12, 300 rows per sport. The 15:02
pass is the only record of what today's EPL fixtures looked like in play, and
the 06:0x passes are the last pre-kickoff prices for them.

| Source | Status |
|---|---|
| nflverse | Live. 2,499 games, 2,229 played. 2026: 2 of 272 complete, unchanged. |
| football-data.co.uk | Live. 2,690 games. E0 2026-27 still 30 played, latest 2026-09-06. |
| Kalshi REST | Live. 120 contracts per pass, both series. |

Refresh moved **5 rows, all line moves on unplayed 2026 games**: ATL@PIT
3.15 -> 3.2, DEN@KC 2.24 -> 2.2, MIA@SF 6.6 -> 7.1 (spread 11.5 -> 12.5), and
week-9 CLE@NO and DAL@IND churning a line out and in — the same two fixtures
that churned in run 5. No new completed games in either league.

**Escalations: none.** The Odds API stays rejected on run 2's reasoning;
football-data.org's key stays unnecessary per run 3. Neither is an open
question and neither is being carried forward.

## State

| | |
|---|---|
| Live bets | **0.** Headline win rate and ROI: undefined, correctly |
| Shadow bets | 1 settled (1 win), 74 pending, 32 void |
| Usable CLV readings | **0** (the one reading is a mechanical 0.0%) |
| CLV readings recoverable tonight | **14**, all EPL, which the old code would have lost |
| Models deployed | None. `live_enabled` false everywhere |
| Tests | **157** pass, network-free |
| Configs beating the market, cumulative | **0 of 150** |
| Venues at which the model beats the market | **0 of 2** |

No model change was proposed or made this run, so there was nothing to
backtest for adoption; the two backtests above were run as regression checks
on the table reordering, not as evidence about the model. `live_enabled` stays
false everywhere — not deferred, decided: nothing this run touched the
model, and both baselines still lose to the closing line.

## Process note

The stored scheduled prompt still contains "do not post, send, change, or
delete anything", and CLAUDE.md has overridden it for repository work since
2026-09-11, so this run captured odds, logged voids and committed. Flagging it
as that note requires: the stored prompt lives at account level and cannot be
edited from inside a session. It also still contains the unfilled
`[which data sources?]` placeholder, answered by the table in CLAUDE.md.

## Open questions / next steps

- **The pre-registered prediction resolves from tonight.** The 14 EPL bets
  settle this evening and the 49 NFL bets from tomorrow. The next run's first
  job is to settle them and report the count against ~22 and ~30 honestly,
  whichever way it falls. Nothing about the pricing pipeline should move until
  it has.
- **Verify the first backfilled CLV by hand.** The mechanism is tested but has
  never run against real settled rows. When the 14 EPL bets settle, check one
  end-to-end against the raw snapshot before trusting the aggregate — a CLV
  column that fills with plausible-looking numbers is exactly the failure this
  project keeps having.
- **Measure the EPL expiry lag instead of relying on 3h.** Today's fixtures
  will be in the stats table within days, at which point `expiration_lag` can
  measure it directly for EPL as run 3 did for NFL. The gate's fallback is
  currently the one place a constant stands in for a measurement.
- **Then move the edge threshold onto the fee-inclusive number** as a `p3`
  bump with explicit re-pricing (run 5).
- **`edge_threshold_pct: 3.0` has never been derived from anything** (run 5).
- **The selection gap remains the thing to attack** (run 4). Nothing this run
  found touches it.
- Kalshi's fee coefficient is still unread; worth one more attempt. Not an
  escalation — no account or payment involved.
- The 5% relative-width liquidity gate remains unvalidated against realized
  fill quality.
- **Standing reminder:** 0 live bets, 1 settled shadow bet, 1 win. A 100% win
  rate on n=1 is not a signal, and 74 pending bets will not be one either.
