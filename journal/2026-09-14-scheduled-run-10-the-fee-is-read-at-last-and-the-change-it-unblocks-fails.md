# Scheduled run 10 -- the fee coefficient is read at last, and the change it unblocks fails

_2026-09-14, 15:02-16:20 UTC. Run 9 was the same day, 06:02-07:10Z._

## Headline

**Kalshi's fee coefficient is verified at exactly 0.07**, closing an item open
since run 5. Not from a page that states it -- no endpoint does, and
kalshi.com still answers 429 -- but by inverting a worked example in Kalshi's
own fee-rounding docs. That cleared the stated blocker on moving the edge
threshold onto the fee-inclusive number.

**So the p3 change was backtested, and it is REJECTED.** It makes NFL worse
(-10.09% -> -11.48%), the two legs disagree in sign at every fee rate, and
neither comes near the deployment gate. The mechanism is worth more than the
result: the bets it culls are the *low*-claimed-edge ones, which run 9
measured as the least overstated half of the book.

**CLV's sign is a function of reference staleness, not of league.** Run 9 read
it as an NFL-vs-EPL split. Split instead by reference lag, the effect holds
*within* the EPL leg: 14 rows with a real close average **-1.41%**, 9 with a
stale reference average **+4.04%** with **zero negative readings**. The lag is
now a stored column and the summary reports the cohorts apart.

**Nothing settled this run.** All 23 pending wagers are on games from
2026-09-15 to 09-22. No bets were logged either -- all 21 recommendations were
duplicates of open rows. Ledger untouched except for the backfilled lags.

## Finding 1: the fee coefficient, by inversion

Runs 5-9 all recorded the same dead end: the API exposes `fee_type` and
`fee_multiplier` but no coefficient, kalshi.com/fees and the fee-schedule PDF
answer HTTP 429, and the docs site is a JavaScript shell. All of that is still
true this run. What is new is that the docs site **mirrors every page as
markdown** -- `docs.kalshi.com/<path>.md`, enumerated in `/llms.txt` -- and
that mirror serves plain text to a bare `requests.get`.

`getting_started/fee_rounding.md` is about rounding, not rates, but its worked
example carries both sides of the fee equation:

> a buy has `-$0.055000` of signed revenue and a model fee of `$0.00363825`

Signed revenue for a buy is `-price x contracts`, so that is one contract at
5.5c, and the published quadratic form inverts directly:

```
rate = 0.00363825 / (1 x 0.055 x 0.945) = 0.07     exactly
```

The reading is unique in the way that matters. The example gives revenue, not
the split, so the other whole-contract splits of $0.055 were checked too:

| split | implied rate |
|---|---|
| **1 @ 5.5c** | **0.07 exactly** |
| 5 @ 1.1c | 0.0669 |
| 11 @ 0.5c | 0.0665 |
| 55 @ 0.1c | 0.0662 |

One round published rate, three ragged numbers. `DEFAULT_FEE_RATE` was already
0.07, so **no number in the project moved** -- the NFL backtest reproduces at
log-loss 0.6517617405253826 and ROI -8.208908995992267%, digit-for-digit. What
changed is what the project is entitled to claim.

This is the taker rate, which is the only one that applies: the pricer lifts
the ask on every simulated bet and `recommend.py` prices at the ask for the
same reason. We never rest an order, so the maker side never arises.

`FEE_RATE_FIXTURE` stores the example as data and a test re-derives the rate
from it on every run, rather than leaving the verification as a claim in a
docstring that nothing checks.

## Finding 2: p3 backtested, and rejected

With blocker 1 cleared, the change run 9 nominated as run 10's candidate was
measurable. Both rules settle at the identical price; they differ only in
which edge the 3% threshold tests:

```
p2 (current):  model_prob / ask         - 1 >= 0.03
p3 (proposed): model_prob / (ask + fee) - 1 >= 0.03
```

p3's bet set is a strict subset of p2's, so no change to the walk-forward loop
was needed: run the venue backtest with the threshold wide open, then apply
each rule post-hoc. `fair_market_prob` plus the pricer's own half-spread
reconstruct the ask exactly.

| leg | rule | n | win% | ROI | 95% CI | sig |
|---|---|---|---|---|---|---|
| NFL | p2 | 1724 | 34.22 | **-10.09%** | [-16.7, -3.5] | yes |
| NFL | **p3** | 1556 | 32.46 | **-11.48%** | [-18.5, -4.4] | yes |
| EPL | p2 | 373 | 33.51 | **-11.07%** | [-26.6, +4.5] | no |
| EPL | **p3** | 283 | 34.98 | **-8.99%** | [-26.8, +8.9] | no |

Robustness, since a single fee rate should not decide it (at fee=0 the two
rules are identical by construction):

| fee | NFL p3 - p2 | EPL p3 - p2 |
|---|---|---|
| 0.010 | -0.47pp | +0.86pp |
| 0.035 | -1.38pp | +4.05pp |
| **0.070** | **-1.39pp** | **+2.08pp** |
| 0.100 | -1.26pp | +3.54pp |

**Decision: rejected.** Three reasons, in order of weight:

1. **It fails the deployment gate.** The gate is "beats the de-vigged closing
   line", not "improves on p2". Both legs stay deeply negative under both
   rules. Adopting p3 because EPL improved by 2pp would be adopting a change
   on the strength of a number that is still losing badly.
2. **The legs disagree in sign at every fee rate.** NFL worse, EPL better,
   consistently. The NFL sample is 4.6x larger and its result is significant;
   the EPL one is not.
3. **The mechanism cuts the wrong way.** The 168 NFL bets p3 removes have a
   median pre-fee edge of **+4.72%** and a median price of **47c** -- the
   low-edge, near-even-money bets. Run 9 measured the low-edge half of the
   settled book as the half whose claimed edge is *least* overstated
   (realized-minus-claimed -0.55 vs -2.89 for the high-edge half). A
   fee-inclusive threshold is still a *minimum on claimed edge*, so raising it
   in effect selects harder for the model's own overstatement. That is run 4's
   selection gap sharpened, not repaired.

Point 3 generalises past this change and is the thing to carry forward:
**every filter of this shape trusts the model's probability more, and the
model's probability is the broken part.** Even the minimal,
theoretically-unimpeachable version -- "never bet a negative after-fee EV",
i.e. p3 at a 0% threshold -- leaves NFL at -10.81% against p2's -10.48%.

Honesty note on the dropped set: the 168 NFL bets p3 removes returned +2.74%
with a 50.6% win rate, which looks like p3 throwing away winners. Its CI is
[-13.6, +19.0] and t = +0.33, so the correct statement is that the dropped
cohort is **indistinguishable from break-even** while the kept cohort is
significantly negative. That is enough to reject p3 and not enough to claim
those bets are good.

Blocker 2 also still stands until 2026-09-21 regardless: 13 pre-registered
wagers are open, and a `PRICING_VERSION` bump would void them a week before
they resolve. But the rejection does not rest on it.

**The tally of bugs stays at 12.** p3 was a proposal that failed a backtest,
which is the process working, not a defect.

## Finding 3: CLV is measuring staleness, not skill

Run 9 reported mean CLV by leg -- NFL -1.03% on a genuine T-0.42h close, EPL
+3.00% on a stale T-7.75h reference -- and read it as the NFL leg being the
trustworthy one. That framing has a confound: leg and reference quality were
perfectly correlated in that cut.

They are not any more. The capture cron has been running since 2026-09-13
10:00Z, so some EPL contracts now have near-kickoff captures too. Splitting
the same 23 rows by **reference lag** instead:

| reference | n | mean CLV | median | pos / zero / neg |
|---|---|---|---|---|
| **real close (<=1h)** | 14 | **-1.41%** | +0.00% | 2 / 8 / **4** |
| **stale (>1h)** | 9 | **+4.04%** | +2.56% | 5 / 4 / **0** |

And within the EPL leg alone, which is the check that separates the two
explanations:

| EPL rows | n | mean CLV |
|---|---|---|
| real close (<=1h) | 2 | **-3.19%** |
| stale (>1h) | 8 | **+4.55%** |

**Every positive CLV reading this project has published came from a reference
that was not a close.** Not one of the 9 stale rows is negative; 4 of the 14
real-close rows are. And the stale cohort's mean is **+4.044%** -- which is
run 8's headline +4.04% to three decimals, because run 8's nine rows *are*
these nine rows. That identity is what confirms the decomposition rather than
merely suggesting it.

n=2 on the EPL real-close cell. That is a direction, not a measurement, and it
is quoted here only because it points the same way as the 14-row aggregate and
against the flattering reading.

### What changed in the code

The lag was reconstructible by hand from the snapshot store, which is exactly
why it kept having to be reconstructed by hand. It is now a stored column,
`clv_reference_lag_h`, written at settlement alongside the CLV it qualifies,
and `ledger-summary` reports:

```
"avg_clv_pct":                  0.7249547593527358   <- kept, not to be quoted
"avg_clv_pct_real_close":      -1.4089092546539324   <- n=14
"avg_clv_pct_stale_reference":  4.044298781140886    <- n=9
"clv_unknown_reference_n":      0
```

The blended `avg_clv_pct` is kept for continuity with every earlier run and
labelled in the code as not the number to quote: it averages two cohorts whose
signs are opposite.

Three details chosen deliberately:

- **1.0h is the cutoff**, and it is not arbitrary: `line-movement` measures
  mean |move| inside the final two hours at 0.004 with a maximum of one cent,
  so a quote from inside that window differs from the true close by less than
  the tick size.
- **Rows settled before the column existed report as `unknown`, never as
  good.** Assuming a missing lag is fine is precisely the error the split
  exists to prevent.
- **The backfill runs unconditionally**, like `backfill_clv` and
  `void_superseded_rows` before it, for the reason this repo has written down
  twice already: a repair someone has to remember to invoke is how the defect
  returns. It filled all 23 rows this run and it only ever *adds* a lag -- no
  settled row's CLV or closing price can be restated by a later snapshot, and
  a test pins that.

Tests **209 -> 216**, all network-free.

## Bets

`recommend` flagged 17 of 34 NFL contracts (50.0%) and 4 of 24 EPL (16.7%),
and logged **0** -- all 21 were duplicates of open rows. `in_play_skipped: 0`,
`illiquid_skipped: 9` on the EPL side, the standing thin-book pattern.
`superseded_voided: 0`, correctly, since no pricing version changed.

A live example of what Finding 2 is about appeared on the board: Chelsea @
Brentford, draw, **+3.8% edge before the fee and -1.3% after**. Under p3 that
row would not be bet. It is also the kind of row the backtest says is among
the model's *better* ones.

| | run 9 | run 10 |
|---|---|---|
| settled | 23 | 23 |
| wins | 6 | 6 |
| pending | 23 | 23 |
| win rate | 26.09% | 26.09% |
| ROI | -13.98% | -13.98% |
| mean CLV (blended) | +0.72% | +0.72% |
| mean CLV (real close) | -- | **-1.41%** (n=14) |

Ledger integrity: 46 non-void rows = 46 distinct wagers. Every row `shadow`.

## Regression checks

No model changed, so nothing required backtesting for adoption. All four run
as regression checks on this run's edits:

| | run 10 | runs 5-9 | match |
|---|---|---|---|
| NFL log-loss | 0.6517617405253826 | 0.6517617405253826 | digit-for-digit |
| NFL ROI | -8.208908995992267% | -8.208908995992267% | digit-for-digit |
| EPL 2425 holdout ROI | -5.11513157894739% | -5.11513157894739% | digit-for-digit |
| NFL flagged gap / soccer | -0.137 / -0.045 | -0.137 / -0.045 | exact |

Blend weights also reproduce: w* = 0 for NFL (the model adds nothing), w* =
0.10 for soccer with `improvement_significant: false`.

One self-inflicted false alarm worth recording, because it nearly became a
finding: the CLI prints **two** different selection numbers, a per-cohort
`OVERALL` gap and a `selection gap (flagged minus passed)`. Run 9 quoted the
first (-0.137); a grep here caught the second (-0.230) and it looked for
several minutes like an unexplained regression in a number that should have
been frozen. It was not -- both reproduce exactly. The lesson is the repo's
own recurring one in a new costume: a number is not identified by the word
"gap" any more than a join key is unique because it looks unique.

## Data sources

| Source | Status |
|---|---|
| nflverse | Live. 2,499 games, 2,242 played (unchanged; week 2 starts 09-17). |
| football-data.co.uk | Live, **still not publishing matchweek 4**. E0 2026-27 stuck at 30 played, latest 2026-09-06. |
| Kalshi REST | Live. 34 NFL + 24 EPL contracts; fee coefficient now read (Finding 1). |
| ESPN scoreboard | Live. NFL 15/15 scores and kickoffs agree; EPL 30/30 and 30/30. 10 fixtures only in ESPN. |

`verify-settlements` clean: NFL 30/30 agreed, soccer 117/117, and
`unmatched_in_coverage: 0` on both -- the counter run 9 split out is doing its
job.

**A correction to run 9 on football-data.co.uk.** Run 9 called it "unchanged
for a **fourth** run", which is true but misleading. The gap between its last
published date (2026-09-06) and the next matchweek (09-12) is the September
**international break** -- there were no fixtures to publish for most of that
window. The real lag is 09-12/13 fixtures unpublished as of 09-14 15:00Z,
which is ~2 days, not ~8. The upstream CSV was fetched directly this run to
confirm the staleness is theirs and not an ingest bug: 30 rows, latest
2026-09-06.

The 10 "only in ESPN" EPL rows reconcile exactly: 9 results football-data.co.uk
has not published (09-12 and 09-13) plus one unplayed fixture in the audit
window (Leeds v Newcastle, today). Nothing unexplained.

**Escalations: none.** No charge and no signup form is outstanding.

## Process note

The stored scheduled prompt still carries "do not post, send, change, or
delete anything" and the unfilled `[which data sources?]` placeholder.
CLAUDE.md has overridden the first for repository work since 2026-09-11 and
settled the second since 2026-09-13. Noted once, per CLAUDE.md, and not
carried into the summary.

## Open questions / next steps

- **The 13 open pre-registered wagers settle 2026-09-15 to 09-21.** Run 9's
  pre-registration stands unchanged and is restated here for the record:
  claimed **5.74**, selection-corrected **4.05**, market-implied **4.72**.
  Nothing about it was touched this run -- which is the point of not bumping
  `PRICING_VERSION` yet.
- **After 09-21, `PRICING_VERSION` is free to move** -- but p3 specifically is
  now rejected on evidence and should not be re-proposed without a new reason.
  Any successor has to clear the deployment gate in backtest, not merely beat
  p2.
- **The real target is the model's probabilities, not the bet filter.** Three
  runs have now tried to fix the selection problem by changing *which* bets
  clear a threshold on claimed edge. Finding 2 says that family of changes
  cannot work, because the threshold's input is the thing that is wrong. The
  blend sweep (w* = 0 for NFL) says the same from the other direction.
- **CLV: decide whether to keep collecting it.** Now measurable properly, but
  the real-close cohort is 14 rows with 8 of them exactly zero. Do not decide
  on this sample; revisit when the real-close cohort has a usable standard
  error.
- **`edge_threshold_pct: 3.0` has still never been derived from anything**
  (run 5). The threshold grid computed this run shows NFL ROI essentially flat
  from 0% to 12% and falling beyond, which is weak evidence that the exact
  value does not matter much -- for a rule that is losing either way.
- Kalshi's fee coefficient: **closed**, run 10.
- The 5% relative-width liquidity gate remains unvalidated against realized
  fill quality.
- NFL preseason markets are priced and settled by Kalshi but invisible to
  nflverse; labelled, not fixable.
- ESPN is an **undocumented** endpoint; `espn-audit` is read every run.
- **Standing reminder:** 0 live bets. 23 settled shadow bets, 6 wins, ROI
  **-13.98%**, the model loses to the closing line on every scoring rule on
  the bets it chose, and the one CLV cohort measured against a real closing
  price is **negative**. That is the deployment gate doing its job, and it is
  still 23 wagers.
