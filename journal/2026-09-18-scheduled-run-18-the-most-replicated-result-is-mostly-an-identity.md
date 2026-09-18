# Scheduled run 18 -- the most-replicated result in the project is mostly an identity

_2026-09-18, 15:02-15:4xZ. Second run today; run 17 ran 06:01-07:1xZ this morning._

## Headline

**Nothing settled, nothing new was logged, and the ledger file was not written
at all.** No NFL or EPL fixture fell between 06:00Z and 15:00Z: `settle`
resolved 0 of 35 pending, `recommend` flagged 21 NFL and 10 EPL contracts and
logged **0** because every one restates an open row, and `git diff` on
`bets/ledger.csv` is **empty**. Ledger unchanged at **26 settled, 6 wins,
23.08%, ROI -23.91%**.

**So this run spent itself on the last untested lever in the bet rule, and it
is now closed.** The project's most-cited replicating result is that the model
overstates more when it claims more -- run 4 in backtest, runs 9, 11 and 17 in
the realized ledger, the high half falling further below its claim every time
it is measured. The obvious move is an upper **cap** on claimed edge. It had
never been tested, and run 11's AUC bound does not reach it: a cap is not a
transform of the forecast, it changes which subset gets bet.

**It fails, and the reason it fails is the interesting part. Most of the
separation that motivated it is algebra.**

    claim_gap - market_gap  ==  market - claimed

and sorting bets by claimed edge *is* sorting them by `claimed - market`. The
high half is **guaranteed** a worse claim gap than the low half whatever the
outcomes do. On the backtest's selection window the identity accounts for
**160%** of the observed separation -- the empirical remainder runs the other
way -- and on the holdout, **79%**. The residual flips sign between the two
windows.

**0 of 11 caps beat the de-vigged closing line, in either phase.** Tests
**301 -> 317**. `cli sweep-edge-cap`.

**Second, smaller finding: the weather tier run 12 tested could never have
been run live.** nflverse populates `temp` and `wind` for **0 of 255** unplayed
games and ~65% of played ones; this morning's settled `DET @ BUF` acquired
67F/4mph some hours *after* it was settled. Run 12 rejected weather on AUC
anyway, so nothing downstream moves -- but "mildly optimistic", which is what
`features.py` has said since run 12, understates it. The column is not worse
at pricing time. It is empty.

## Finding 1: the edge cap, and the identity under the result that motivated it

### What was tested

Bands are cumulative, `[3%, cap)`, on the flagged NFL sides. Eleven caps
including `none` (the incumbent), selected on **2021-2023** and confirmed on a
held-out **2024** -- run 17's protocol, for run 17's reason: the canonical
2021-2024 window has been looked at by every other sweep in this repo.

**The gate, for a rule that changes which sides get bet rather than how they
are priced, is ROI at de-vigged fair odds.** Stake $1 per selected side and
settle it at `1 / fair_market_prob`. Then `fair ROI == 0` means the selection
knows exactly what the closing line knows, and `> 0` means it carries
information the line lacks. Book ROI is reported beside it but cannot be the
gate: it is fair ROI minus the vig, so a rule with no information at all still
prints a negative number, and a rule that merely pays less vig has discovered
nothing.

**A band must hold 100+ selection bets to be eligible.** Pre-specified, not
fitted. The tightest cap puts 29 bets in a band and posts **+4.32%** fair ROI
with an interval **93 points wide** -- the best of any finite cap, and exactly
the number this project would have adopted and then retracted.
`test_the_eligibility_floor_is_what_rejects_the_tightest_cap` asserts both
halves of that so the guard cannot be quietly removed.

### Selection, 2021-2023: 702 flagged bets over 854 games

| cap | n | claim gap | mkt gap | book ROI | fair ROI | fair 95% CI |
|---|---|---|---|---|---|---|
| 5% | 29 | -6.39 | -2.84 | +1.40% | **+4.32%** | [-42.4, +51.1] |
| 10% | 132 | -11.17 | -6.65 | -15.69% | -13.16% | [-33.4, +7.1] |
| 15% | 206 | -9.35 | -3.97 | -11.33% | -8.49% | [-24.8, +7.8] |
| 20% | 267 | -10.01 | -3.87 | -10.39% | -7.51% | [-22.3, +7.3] |
| 25% | 337 | -11.00 | -4.07 | -11.54% | -8.72% | [-22.0, +4.6] |
| **30%** (pick) | 396 | -10.80 | -3.22 | -10.01% | -7.11% | [-19.6, +5.4] |
| 40% | 467 | -11.63 | -3.19 | -10.46% | -7.54% | [-19.3, +4.2] |
| 50% | 516 | -12.95 | -3.99 | -14.08% | -11.29% | [-22.4, **-0.2**] |
| 75% | 610 | -12.84 | -2.57 | -10.07% | -7.13% | [-18.0, +3.8] |
| 100% | 647 | -13.92 | -3.15 | -13.33% | -10.50% | [-21.1, +0.1] |
| **none** (incumbent) | 702 | -14.07 | -2.36 | -9.85% | **-6.88%** | [-18.0, +4.3] |

**The incumbent is the best row in the table.** Not "survives" -- best. The
best *eligible* cap (30%) is -7.11% against the uncapped -6.88%, so the pick
never led where it was chosen, which is a cleaner rejection than losing on the
holdout would have been. One band's interval excludes zero on the **negative**
side (50%, upper bound -0.2); at eleven looks that is what eleven looks buys
you, and it is reported rather than picked out.

### Confirmation, held-out 2024: 228 bets

| cap | n | claim gap | mkt gap | book ROI | fair ROI | fair 95% CI |
|---|---|---|---|---|---|---|
| 5% | 15 | +7.47 | +11.46 | +13.24% | +18.12% | [-34.1, +70.4] |
| 10% | 43 | -0.77 | +4.05 | -4.58% | -0.42% | [-31.2, +30.3] |
| 15% | 75 | -0.80 | +4.78 | -2.33% | +1.91% | [-23.5, +27.4] |
| 20% | 103 | -4.91 | +1.73 | -5.44% | -1.34% | [-24.3, +21.6] |
| 25% | 120 | -5.83 | +1.12 | -6.87% | -2.83% | [-24.8, +19.1] |
| **30%** (pick) | 139 | -8.09 | -0.46 | -11.26% | -7.42% | [-27.6, +12.7] |
| 40% | 161 | -8.22 | +0.35 | -8.94% | -5.01% | [-24.1, +14.1] |
| 50% | 186 | -10.81 | -1.43 | -13.28% | -9.54% | [-27.9, +8.8] |
| 75% | 209 | -11.50 | -1.24 | -13.11% | -9.37% | [-27.2, +8.4] |
| 100% | 217 | -11.44 | -0.74 | -10.80% | -6.98% | [-25.0, +11.0] |
| **none** (incumbent) | 228 | -12.71 | -1.17 | -12.67% | -8.93% | [-26.7, +8.9] |

**Beat the de-vigged closing line: 0 of 11 in selection, 0 of 11 here.**

The pick does come out ahead of the incumbent out-of-sample (-7.42% vs
-8.93%), which is worth naming precisely because it is the shape of a result
and is not one: it was already behind in selection, the two intervals overlap
across forty points, and four *other* caps beat it on the same holdout. The
tempting row here is the 15% cap at **+1.91%**, which was never the pick and
sits in an interval fifty points wide.

The uncapped 2024 book ROI is **-12.67292964478684%, CI [-29.75, +4.40]** --
digit-for-digit run 17's incumbent `season_regression` holdout, reached
through a different module. That is a cross-check on the band machinery
betting the same universe the rest of the repo backtests, and it is pinned as
a test rather than noticed here.

### The identity, which is the actual finding

Every band reports two gaps, because conflating them is the trap:

    claim_gap_pp  = realized - claimed       the model vs its own claim
    market_gap_pp = realized - fair market   the model vs the closing line

Read the `claim gap` column down either table and it orders almost perfectly:
selection **-6.39 -> -14.07**, holdout **+7.47 -> -12.71**. Run 4's signature,
reproducing beautifully at n=702.

Read the `mkt gap` column and it does **not** order. Selection: -2.84, -6.65,
-3.97, -3.87, -4.07, -3.22, -3.19, -3.99, -2.57, -3.15, -2.36. Flat at about
-3pp, and the widest band is the *least* negative. Holdout: mostly positive
and unordered.

They are the same 702 bets. The difference between them is
`market - claimed`, which at de-vigged odds is the claimed edge itself. So the
claim gap was never going to do anything else.

Run on the median split -- the exact form runs 9, 11 and 17 report -- with the
ledger's own 26 rows put through the same function (`cli sweep-edge-cap`):

| phase | half | n | mean edge | claim gap | mkt gap | identity | fair ROI |
|---|---|---|---|---|---|---|---|
| selection | low | 351 | 13.7% | -11.20 | -4.07 | -7.13 | -8.96% |
| selection | high | 351 | 63.3% | **-16.93** | **-0.65** | -16.28 | **-4.80%** |
| holdout | low | 114 | 12.0% | -6.79 | +0.08 | -6.87 | -6.97% |
| holdout | high | 114 | 54.9% | **-18.64** | -2.42 | -16.22 | -10.89% |
| ledger | low | 13 | 11.3% | -10.26 | -5.78 | -4.48 | -5.54% |
| ledger | high | 13 | 29.6% | **-25.89** | **-16.39** | -9.50 | **-39.36%** |

| phase | separation | = identity | + empirical | mechanical share |
|---|---|---|---|---|
| selection | +5.73pp | +9.15pp | **-3.42pp** | **160%** |
| holdout | +11.85pp | +9.35pp | +2.50pp | 79% |
| ledger | +15.63pp | +5.01pp | +10.61pp | 32% |

**In the selection window the high half is the better half.** Its market gap
is -0.65pp against the low half's -4.07pp and its fair ROI is -4.80% against
-8.96%. The claim gap still separates by +5.73pp, all of it and more from the
identity. On the holdout the empirical remainder reverses to +2.50pp. One
league, two adjacent windows, opposite signs.

And the trend test, regressing `won - fair_market_prob` on claimed edge with
the bootstrap resampled over games:

| phase | slope, pp per +10pp of claimed edge | 95% CI |
|---|---|---|
| selection | **+0.463** | [-0.299, +1.270] |
| holdout | **-0.375** | [-1.748, +1.242] |

A cap can only pay if this slope is negative. One window has it positive, the
other negative, and both intervals contain zero.

### What this does and does not say about the ledger

**It does not retract the ledger observation.** The high half of the 26
settled rows really did win 2 where the market implied 4.13, its fair ROI
really is **-39.36%**, and 32% mechanical means two thirds of that separation
is not arithmetic. The backtest cannot un-observe it.

**What it says is that the number has been read against the wrong baseline.**
Scored against the model's own claim the high half looks close to damning --
Poisson-binomial **P(X <= 2) = 0.0428**. Scored against the market, which is
the only baseline that pays, the same 13 rows give **P(X <= 2) = 0.159**:
ordinary. That gap between 0.043 and 0.159 is the identity, in p-value form.

**And the empirical part does not replicate at 27x the sample.** Two backtest
windows disagree about its sign. So the honest status of the project's
most-replicated result is: the headline version is largely arithmetic, and the
part that is not is 13 bets against 1,606 that say otherwise.

**Nothing adopted. `config/leagues.yaml` and `PRICING_VERSION` untouched.**
`edge_threshold_pct` stays 3.0 with no upper bound. Model configurations
tested stays at **160** -- these were eleven *bet-rule* bands in two phases,
not model configs, and folding them into that tally would inflate it with a
different kind of object.

## Finding 2: the weather tier was never available at pricing time

`refresh-history` rewrote 7 rows of `nfl_games.csv` this run. Six are upstream
line revisions on unplayed week-2 games (`MIA @ SF` moved 13.5 -> 12.5). The
seventh is the one worth looking at: **`2026_02_DET_BUF`, settled this
morning, gained `roof=outdoors, surface=grass, temp=67.0, wind=4.0`** -- hours
after it had been resolved, verified and written into the ledger.

Measured across the committed table:

| column | unplayed games (n=255) | played games |
|---|---|---|
| `temp` | **0** populated | ~65% |
| `wind` | **0** populated | ~65% |
| `roof` | 214 (84%) | 100% |
| `surface` | 255 (100%) | ~99% |

Run 12 built the `weather` tier on `is_outdoor`, `wind_mph` and `temp_dev` and
labelled it "mildly optimistic -- nflverse records the conditions the game was
PLAYED in; a model pricing at T-8h has a forecast instead". That framing is
too generous. A model pricing at T-8h does not have a forecast, because
nothing in this repo fetches one; it has `NaN`, and `features.py` defaults it.
The tier as tested is **not deployable at all**, independently of how it
scored.

**Nothing downstream changes**, and that is the point of recording it rather
than a reason not to: run 12 rejected weather on AUC (**-0.0126, CI [-0.020,
-0.006]**), so the conclusion was already correct for a different reason.
What changes is what a future run learns when it proposes revisiting weather
with a better fit -- it now finds out the feature is absent before it spends a
session on it, from `test_weather_columns_do_not_exist_before_kickoff` rather
than from this paragraph.

`roof` and `surface` are the counter-example and are asserted alongside:
schedule-known, available in advance, legitimately usable. The `schedule` tier
remains the only one whose result could have been deployed as-is -- and run 12
rejected that too (-0.0111).

## Bets

**0 settled, 0 CLV filled, 0 backfilled, 35 unresolved.** No fixture fell in
the window; the next are EPL on 09-19 and the NFL slate on 09-20/09-21.

**0 new rows.** NFL flagged **21 of 53** fillable (39.6%), all 21 duplicates
of open positions; EPL flagged **10 of 29** (34.5%), all 10 duplicates.
`illiquid_skipped` 9 NFL and 1 EPL, `in_play_skipped` 0, `superseded_voided`
0.

| | run 17 | run 18 |
|---|---|---|
| settled | 26 | 26 |
| wins | 6 | 6 |
| pending | 35 | 35 |
| void | 67 | 67 |
| win rate | 23.08% | 23.08% |
| ROI | -23.91% | -23.91% |
| mean CLV (real close) | -1.888% (n=17) | -1.888% (n=17) |
| mean CLV (stale) | +4.04% (n=9) | +4.04% (n=9) |

`clv_resolution`, as CLAUDE.md requires: one tick is **3.5253%** of `clv_pct`
at this ledger's mean price paid (0.3462); median reading **0.000%**; mean
|move| **1.00 ticks**; **46.2%** of settled rows never moved a tick. The
-1.888% mean is **0.54 of a tick**.

**Ledger integrity: `git diff --numstat bets/ledger.csv` is empty.** A
`recommend` that logs nothing still rewrites the file, and run 15's
round-trip fix means that rewrite is now byte-identical. This is the first run
where that can be observed cleanly, because it is the first with no settlement
and no new row to account for the diff.

**The pre-registered cohorts were not scored, deliberately.** 25 of 36 settled,
unchanged; 11 open, all NFL, kicking off 09-20T17:00Z to 09-21T00:20Z,
carrying **4.87 claimed / 3.96 market-implied**. P(X <= 6) is still **0.0509**.
`scorecard`'s `p_at_most_model` reads **0.03850644442717604** and is **not**
that number -- it scores every settled row. Score both cohorts on **09-21**.

## Regression checks

All four canonical numbers reproduce digit-for-digit, on a container that
re-resolved every dependency from scratch:

| | run 18 | runs 5-17 | match |
|---|---|---|---|
| NFL log-loss | 0.6517617405253826 | 0.6517617405253826 | digit-for-digit |
| NFL ROI | -8.208908995992267% | -8.208908995992267% | digit-for-digit |
| NFL n_games / n_bets | 1942 / 1625 | 1942 / 1625 | exact |
| EPL 2425 holdout ROI | -5.11513157894739% | -5.11513157894739% | digit-for-digit |

pandas resolved to **3.0.6** again, numpy 2.4.6, scikit-learn 1.9.1.

Tests **301 -> 317**. Fifteen for the edge-cap study (the gate in both phases,
the pick losing in selection, the eligibility floor and what it rejects, the
identity asserted as exact algebra in every band, the mechanical share, the
empirical remainder flipping sign, the trend interval straddling zero, the
half-open band boundaries, fair ROI on frames whose answers are known by hand,
the cross-module ROI check, the ledger adapter's unit conversion, and a
no-leakage assertion that the holdout seasons are absent from the selection
frame); one for the weather-column measurement.

## Data sources

| Source | Status |
|---|---|
| nflverse | Live. 2,499 games, 2,244 played (unchanged). 7 rows revised, incl. post-hoc weather on `2026_02_DET_BUF` (Finding 2). |
| football-data.co.uk | Live. `epl_games.csv` unchanged at 2,700 / 2,700 played. |
| Kalshi REST | Live. 62 NFL + 30 EPL contracts. |
| ESPN scoreboard | Live. NFL 17/17 scores and kickoffs, EPL 40/40. `only_espn` 6 on soccer -- upcoming 09-19/09-20 fixtures, `STATUS_SCHEDULED`, no scores. |

`espn-audit` clean, `verify-settlements` 34/34 NFL and 120/120 soccer. Capture
cron healthy: snapshots every ~30 min, latest 15:02Z immediately before this
run; this session's own two captures wrote 124 NFL and 60 EPL rows.

## Open questions / next steps

- **Score the pre-registered cohorts on 09-21 and not before** -- 36-wager
  (claimed 15.19 / market 12.48) and the 13-wager subset (5.74 / 4.72). This
  is the fifth opportunity to look early and the fifth time it is declined.
  **Do not quote `scorecard`'s `p_at_most_model` as the pre-registered result.**
- **The CLV cohort is at 17 real-close rows and needs ~13 more to resolve a
  quarter tick.** The 11 open pre-registered wagers all settle 09-20/09-21
  with full final-hour coverage, so the run after 09-21 is the first with a
  cohort worth a real interval.
- **The edge cap is closed.** No upper bound on claimed edge; 0 of 11 bands
  beat the closing line in either phase and the best eligible one lost to
  doing nothing where it was chosen. Do not re-raise on the strength of the
  claim-gap split -- that split is 79-160% identity in backtest, and
  `test_claim_gap_separation_is_mostly_an_identity` is the answer.
- **Read the two gaps apart from here on.** Any future statement of the form
  "the bigger the claim, the bigger the overstatement" needs to say which
  baseline. Against the model's claim it is nearly guaranteed; against the
  market it is unmeasured or absent.
- **Weather is closed twice over** -- rejected on AUC by run 12, and
  unavailable at pricing time as of this run. Revisiting it needs a weather
  API this repo does not have, and that would be a new data source subject to
  the usual bar (free, no human-created account, verified against something
  already held).
- **Run 16's ESPN supplement is still untested against a real gap.** The
  09-19 EPL fixtures will be served by a live primary source. Deferred, not
  validated.
- **`PRICING_VERSION` is free to move after 09-21**, unchanged since run 10.
- **Do not re-raise:** `*/30` capture cadence (run 13), the Odds API (run 2),
  football-data.org (run 3), recalibration in any form (run 11), context
  features (run 12), `season_regression` (run 17), an upper edge cap (run 18).
- **Five reasons deep on why the model loses**, now six: AUC deficit -0.046 CI
  [-0.064, -0.030] (run 11); context features rank worse (run 12); the whole
  pre-kickoff window is quiet (run 13); season regression does not move the
  gap (run 17); and now, the selection pathology that looked like the last
  available lever is mostly an artifact of how it was measured. **There is no
  remaining bet-rule change with a reason to expect a different outcome.** The
  honest next step is still the 09-21 cohort.
- **16 stale `claude/elegant-archimedes-*` branches** sit on the remote.
  Harmless, not cleaned up, noted so it is not rediscovered.
- NFL preseason markets are priced and settled by Kalshi but invisible to
  nflverse; labelled, not fixable.
- **Standing reminder:** 0 live bets. **26 settled shadow bets, 6 wins, ROI
  -23.91%.** The market beats the model on every scoring rule on the bets the
  model itself chose. **It is 26 wagers.** That keeps all of it provisional --
  and this run is a reminder that it cuts both ways: the result the project
  was most confident about is the one that did not survive being measured at
  scale.

## Process note

The stored scheduled prompt still carries "do not post, send, change, or
delete anything" and the unfilled `[which data sources?]` placeholder.
CLAUDE.md has overridden the first for repository work since 2026-09-11 and
settled the second since 2026-09-13. Noted once, per CLAUDE.md, and not
escalated.

**Escalations: none.** No charge and no signup form is outstanding.
