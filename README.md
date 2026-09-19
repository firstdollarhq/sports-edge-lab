# sports-edge-lab

A research project testing predictive sports models against real market odds.
**Paper trading only** — no real money moves through this repo. The goal is
to find a real, validated edge, not to confirm a bias. See `journal/` for an
honest, dated log of what was tried and what happened.

## Status (2026-09-19, scheduled run #20)

- **0 live bets. 29 settled shadow bets (8 wins), 35 pending, 67 void.**
  Headline win rate **27.59%**, ROI **-8.23%**. Aston Villa won at Tottenham —
  the `away` side, claimed 0.483 against a de-vigged market 0.266, paid 3.7037,
  **closed at 4.1667 for -3 ticks of CLV**. **The ROI improved ten points on
  one wager**, which is the noise this project exists to not be fooled by; it
  is reported as arithmetic, not as progress. It is 29 settled wagers and
  settles nothing on its own.
- **Elo enters a newly-promoted team at 1500, and the bet rule buys the
  difference.** Over the 8 teams making their first EPL appearance in the table
  (2020-21..2025-26), the model's probability for the debutant side runs
  **+0.0447 above the de-vigged market** against a realized **0.2434** — the
  market's **0.2451** is almost exactly right, so the gap is the model's, and
  **all 8 teams are biased the same way** (cluster-bootstrap 95% CI over teams
  **[+0.0253, +0.0634]**). It is the initialisation and not the draw of teams:
  the bias decays monotonically as evidence arrives — **+0.1016** over a
  debutant's first 5 games, +0.0738 (5–9), +0.0413 (10–18), **+0.0237**
  (19–37) — and every debutant finishes its first season below where it
  started.
  - **The bet rule amplifies it**: **62.5%** of debutant sides get flagged
    against **36.4%** of established ones, at a mean claimed edge of **+35.8%**
    against +19.2%. The ROI gap (-11.77% vs -7.12%) is **not** the solid part —
    per team it swings from -81.67% to +44.09% across 8 clusters.
  - **It is live.** Coventry and Hull are 2026-27 debutants with **four games**
    of history each; Hull sits **14th in the Elo book at 1534**, above Fulham,
    Crystal Palace and Tottenham. The largest claimed edge on the entire EPL
    board is `Hull @ Newcastle` away at **+57.7%**.
  - **A second-order effect makes 1500 wrong in a way that is easy to miss.**
    `backtest_soccer` never regresses to the mean and relegated teams carry
    their low ratings out of the division, so the surviving book drifts up: the
    current 20-team mean is about **1572**. A debutant enters ~72 points below
    today's league mean, which is why the bias is +0.045 rather than +0.10 —
    the prior is wrong and partially self-correcting, which is the worst way
    for it to be wrong.
- **The correction was swept out-of-sample and REJECTED.** Seeding a promoted
  side at `1500 - penalty` (the naive version — lowering `default_rating` — is
  a **no-op**, since Elo differences are translation-invariant and the first
  season's teams are all unseen; the sweep returned an identical row for every
  value from 1500 to 1300). Selected at **penalty = 100** on 2020-21..2023-24
  from a smooth single-minimum log-loss curve; confirmed on an untouched
  2024-25..2025-26 holdout.
  - **The bias correction generalises and nothing else does.** Holdout
    debutant bias +0.0606 → **+0.0154** and flag rate 81.6% → **36.8%**, but
    holdout log-loss improves by **0.000056**, debutant-game log-loss gets
    *worse*, and ROI moves the wrong way (+1.32% → -0.27%).
  - Pooled over six seasons with season as the cluster: per-game log-loss
    **-0.000987, CI [-0.00255, +0.00058]**; ROI **-0.622pp, CI [-3.55, +2.17]**,
    P(better) 0.349. Better on overall log-loss in **3 of 6** seasons; better on
    the debutant bias in **6 of 6**. The surgical version — keep the ratings,
    just decline to bet debutant sides — is also nothing (**+0.371pp**, CI
    straddling zero), which is the verdict run 18 reached about the edge cap.
  - **What the rejection teaches.** Runs 11, 12 and 17 tested effects that
    turned out not to be real. **This one is real** — and correcting it still
    buys nothing. That is evidence the deficit is **not concentrated in a
    patchable subgroup**. The model is not losing because of promoted teams; it
    is losing everywhere, and promoted teams are where it is easiest to see.
  - What survived is a counter: `betting/history.py`, reported by `recommend`
    as `thin_history`. A fixture is thin when **either** side is under 20 games
    (`elo_diff` is a difference). **It gates nothing**, and a test asserts the
    rec list comes back unmodified so a future run cannot quietly turn it into
    the filter this run rejected. NFL reports 0 and always will.
- **The tick that every CLV mean is read against was computed with the wrong
  formula, and the error ran in the dangerous direction.** `_clv_resolution`
  priced one tick as `p / (p - tick) - 1` — the cost of buying a cent *cheaper*,
  which is not the quantity CLV moves in. The exact conversion is
  `ticks = clv_pct / placed_decimal`, and the evidence it is right rather than
  merely tidier is that under it **every settled CLV in the ledger is an exact
  integer** (max deviation 8.4e-15), as it must be on a venue that quotes whole
  cents. The old formula ran **1.9%–9.1% high per row, +4.3% on the mean**,
  which biased `mean_abs_ticks` **down** — a genuine one-tick move read as
  0.96–0.98 ticks. One tick is **3.3915%** at this ledger's prices, not 3.5375%;
  `mean_abs_ticks` is **1.2500** (35 ticks / 28 rows), not 1.2083. **No price,
  selection or settlement moves** — this changes how a number is reported.
  - The old formula divided by zero at a 1c contract, so those rows were
    dropped and a test pinned the exclusion. The exact one has no singularity:
    a tick at 1c takes it to 2c, halving the decimal odds, worth **100% CLV**.
    That row now belongs in the mean and the test asserts it is **kept**.
- **The CLV cohort got *less* precise by getting bigger, and run 18's
  projection is optimistic by a factor of three.** Two rows raised the SD
  **39%** (5.037 → 6.995 in `clv_pct`; the n=17 SE reproduces run 17's 1.222%
  digit-for-digit, so only the data moved). Required rows for a quarter-tick SE
  went from **~30 to ~90**; the cohort is at **19**.
  - In exact ticks: mean **-0.105**, median **0.000**, sd 2.378, SE 0.546,
    **95% CI [-1.175, +0.964]**. The reading is unchanged — **no detectable
    edge** — and the uncertainty is ±1.07 ticks, wider than run 18's framing
    implied.
  - **Why it will keep moving: CLV magnitude scales with placement lag.** The
    two new rows were struck at **T-123.6h**; every prior row sat at T-48h to
    T-90h. By lag: T-48..50h **0.900** mean abs ticks (n=10), T-53..57h 0.750
    (n=4), T-75..124h **3.200** (n=5). `corr(lag, |ticks|) = 0.629`,
    cluster-bootstrapped over 17 games to **[0.024, 0.831]**, stable under
    leave-one-game-out (0.528–0.722). Suggestive, not established — but enough
    to disqualify a projection that assumes a fixed SD. Required n by mix:
    **43** (short-lag only), **90** (current), **129** (long-lag only). The
    recommender logs a side the first time it sees an edge, so lag is set by
    when a contract opens, not by any decision — hence `n_for_target_se` is now
    reported beside the mean rather than written into a journal and inherited.
  - **Placement lag is not a variance knob.** Betting later would tighten the
    estimate and shrink the estimand by the same mechanism: a bet struck at
    T-1h has almost no variance *and* almost nothing to measure.
  - **This does not contradict run 13.** Its 0.0107 mean EPL move was measured
    from a median first capture of T-74h; these bets were struck at T-124h.
    `*/30` is untouched and stays untouched.
- **Run 16's ESPN supplement fired against a real gap for the first time, and
  it worked — but the gap was not the outage it was built for.**
  football-data.co.uk is **up and simply publishes on a lag**: its latest row
  is **2026-09-14**, ESPN carried the 09-18 fixture by 06:04Z, and the two
  wagers settled this run sit on it. `verify-settlements` on the primary alone
  checks **120 and leaves 3 unmatched**; with the supplement, **123 checked,
  123 agreed, 0 unmatched**. **This is the common case, not the failure case** —
  any midweek or Friday fixture settles on Kalshi before the primary's CSV
  catches up — so the supplement is load-bearing on the normal path.
  - One existing test had to be rewritten rather than patched:
    `test_espn_results_reproduce_the_primary_ratings_exactly` asserted ESPN
    supplies *exactly* the primary's post-cutoff rows, true only while the two
    were level. ESPN is now a fixture **ahead**, so the comparison is scoped to
    where both have published and the lead is asserted separately as `>=`.
- **The project's most-replicated result is mostly an algebraic identity, and
  the bet-rule change it motivated is rejected.** Runs 4, 9, 11 and 17 all
  found that the model overstates more when it claims more, so run 18 tested
  the obvious response: an upper **cap** on claimed edge, which run 11's AUC
  bound does not reach (a cap is not a transform of the forecast, it changes
  which subset gets bet). Eleven cumulative bands `[3%, cap)`, selected on
  2021-2023 and confirmed on a held-out 2024. **0 of 11 beat the de-vigged
  closing line in either phase**, and the best eligible cap (30%) **loses to
  doing nothing where it was chosen** (-7.11% vs -6.88% fair ROI).
  `cli sweep-edge-cap`, fifteen tests.
  - **The reason is the finding.** `claim_gap - market_gap` **is**
    `market - claimed`, and sorting bets by claimed edge is sorting them by
    `claimed - market`. The high half is *guaranteed* a worse claim gap
    whatever the outcomes do. The identity accounts for **160%** of the
    observed separation on the selection window — the empirical remainder runs
    the *other* way, and the high half is the better half there (fair ROI
    -4.80% vs -8.96%) — and **79%** on the holdout, where the remainder
    reverses sign. On the ledger's own 26 rows it is **32%**.
  - **Read against the right baseline, the ledger's high half is ordinary.**
    Scored against the model's claim, its 2 wins give Poisson-binomial
    **P(X ≤ 2) = 0.0428**. Scored against the market — the only baseline that
    pays — the same 13 rows give **0.159**. That gap is the identity in
    p-value form.
  - **Error against the market does not order with claimed edge**, which is
    the only thing that could have made a cap pay: slope **+0.463**pp per
    +10pp of claimed edge in selection (CI [-0.30, +1.27]) and **-0.375** on
    the holdout (CI [-1.75, +1.24]). Opposite signs, both straddling zero.
  - **Nothing is retracted.** The ledger observation stands; it has been read
    against the wrong baseline, and the part of it that carries information
    does not replicate at 27x the sample. **Any future claim of the form "the
    bigger the claim, the bigger the overstatement" must say which baseline.**
- **The `weather` context tier could never have run live.** nflverse populates
  `temp` and `wind` for **0 of 255 unplayed games** and ~65% of played ones —
  `2026_02_DET_BUF` acquired 67°F/4mph *hours after it was settled*. At pricing
  time the column is not worse than the truth, it is empty. Run 12 rejected
  the tier on AUC anyway (-0.0126, CI [-0.020, -0.006]) so nothing downstream
  moves, but `features.py`'s "mildly optimistic" was too generous and now says
  the measured thing. `roof` (84% of unplayed) and `surface` (100%) are the
  counter-example: schedule-known and legitimately usable.
- **The one settled row is the sharpest single observation in the book.** Model
  0.380 on Detroit against a de-vigged market 0.355, bought at 0.36, **closed
  at 0.31** — a monotone five-tick walk away from the model's side over four
  days with zero reversal, priced against a reference **12.4 minutes** before
  kickoff. CLV **-13.89% = -3.94 ticks**, the book's largest negative (next is
  -12.50%). Verified 34/34 by `verify-settlements` and by both stats sources
  independently.
- **`season_regression` swept for the first time, and rejected** — the one
  `NflConfig` field `sweep_nfl` never varied, so runs 1-16's "150
  configurations" all ran it at 0.33. Worth testing because run 11's
  AUC-invariance argument (which retires every recalibration-shaped change)
  does **not** reach it: season regression changes the ratings, so it reorders
  games. Ten values selected on 2021-2023, confirmed on a held-out 2024:
  **0 of 10 beat the de-vigged closing line on log-loss or AUC in either
  phase**; the value log-loss prefers (0.25) **ranks worse** than the incumbent
  out-of-sample, 0.73315 vs 0.73797 — run 12's trap again; and **0.33 is
  already the AUC optimum of the grid**. The AUC gap to market is flat at
  -0.052 to -0.065 across everything from 0.0 to 0.75, so this parameter is not
  a lever on what is actually wrong. **Nothing adopted.** `cli
  sweep-season-regression`. Configurations tested: **160**.
- **`scorecard`'s `p_at_most_model` is not the pre-registered prediction, and
  the two have now visibly diverged.** It reads **0.0385** against run 11's
  0.0509, but run 4's pre-registered cohort is **36 specific wagers** of which
  **exactly 25 have settled — unchanged** — and its P(X ≤ 6) is **still
  0.0509**. The scorecard's p-value fell because a 26th, non-pre-registered row
  arrived. The cohort completes **09-21** (11 open NFL wagers carrying 4.87
  claimed / 3.96 market-implied); it is deliberately **not** being scored
  before then, because it has already been looked at three times with no
  correction for looking.
- **football-data.co.uk is BACK** after 34-48h down (the recovery falls in an
  unobserved 14h gap). The `www`→apex redirect remains; the
  apex→`http://127.0.0.1/` loop is gone. **The committed table it was replaced
  with came back byte-identical to what the live source now returns** — which
  retroactively audits runs 15-16: their claim that the cached table was
  missing no played game rested on ESPN, and the primary source has now
  confirmed it directly. (Run 16's ESPN supplement had **never fired** as of
  run 18; **run 19 fired it against a real gap** — see the top of this
  section.)
- **The EPL rating path no longer depends on that host (run 16).** When the
  committed table falls behind, `ingest/sources` now fills the gap with ESPN's
  played games, in memory, at load time. `build_soccer_model` reads season,
  date, teams, scores and result — **not one odds column** — and ESPN carries
  all of them. Verified on the real tables, not a fixture: truncate the
  committed table to before 09-11, refill from ESPN, and the rating book comes
  back **identical — 30 clubs, max difference 0.0**, with all 10 recovered
  scores matching what football-data.co.uk itself said.
  - **The cost is stated, not hidden.** The gate was worth something because
    ESPN was an *independent* check on someone else's table; for a supplemented
    row it is both filler and checker. The pre-fill gap is kept beside the
    post-fill gap and printed in the run log, so a supplemented run cannot read
    like one that needed no supplement.
  - **Three refusals** keep it safe: the gap counter and the gap filler share
    one matcher (a date-vs-kickoff mismatch would have appended a second copy
    of a game and double-counted it in every downstream rating); a club the
    rating book has never seen is refused rather than opened as a second Elo
    entity at default rating, which is what an upstream rename would otherwise
    do silently; and the supplement never reaches a backtest, since
    `cli._load_games` reads the committed table directly and odds-free rows are
    holes, not games.
  - **It fired on 2026-09-19 (run 19), and not because of an outage.** Runs 16
    and 17 exercised none of it and run 18 recorded it as deferred. What
    actually exercised it was the primary source's ordinary **publishing lag**:
    up and healthy, latest row 09-14, with a played 09-18 fixture carrying two
    settled wagers. Primary alone: 120 checked, **3 unmatched**. With the
    supplement: **123 checked, 123 agreed, 0 unmatched**. **Validated** — and
    on a path that recurs weekly rather than only during an outage.
- **The outage destroyed no irreplaceable record**, and in the end no
  bookmaker-average closing line was lost at all: no EPL fixture was played
  inside it, and `epl_games.csv` came back from the recovered source
  byte-identical. Had any been played, the Kalshi quotes would still have been
  captured — run 5 measured the two venues pricing the same games the same way
  (corr 0.9955) — so reconstructing an EPL closing line from `data/snapshots/`
  remains possible from committed data at any later date.
- **The model's spectacular early-board edges are a book that has not opened
  yet — and the ones that survive that never decay at all.** Run 14 left "the
  gate rejects early boards, the model's biggest edges appear on early boards,
  and nobody has put a number on the two together" as the next work. Both
  halves, from `cli edge-decay`:
  - **32 of 32 NFL contracts whose listing was actually watched opened OUTSIDE
    the liquidity gate** — median spread **22.5c**, median volume **0**, median
    ask size **4** — and took a median **568 minutes** to produce a tradeable
    quote. Across that stub the ask moves a median **0.070** and the claimed
    edge a median **12.0pp**. For scale, run 13 put the mean |net move| over
    the *entire rest* of the pre-kickoff window at **0.0157**. NFL-only: the
    EPL board listed nothing new during the capture window.
  - **Anchored at the first gate-passing quote, claimed edge does not decay.**
    NFL flagged sides **34.1% → 33.2%**, mean change **-0.84pp, CI
    [-8.39, +4.96]**; EPL **24.3% → 22.5%, -1.81pp, CI [-5.83, +2.24]**.
    Decomposed, neither the market leg nor the model leg moves. On the 12 NFL
    contracts whose window actually finished, **24.2% → 23.8%** at a median
    T-0.42h.
  - **So the winner's curse is not a thin-book artifact.** The gate already
    removes the thin-book period; what is left is a tight, deep, unmoving book
    that the model disagrees with by a third of its own price for ten days.
  - **The first draft of that module reported the opposite and was wrong.**
    Anchored on each contract's *first* capture it found claimed edge GROWING
    by **+20.0pp, CI [+11.6, +31.6]** on gate-rejected contracts. Arithmetically
    correct, and entirely the opening stub: a wide book prices both sides as
    negative edge, so the edge "grows" when it tightens. Nothing was published
    from that pass; the fix was the anchor, not the arithmetic.
- **`bets/ledger.csv` was being altered by the act of reading it.**
  `ledger._load` used pandas' default CSV float parser, which is not correctly
  rounded, so every `recommend` and every `settle` perturbed cells nothing had
  touched (two of them on 09-17). **Run 11 diagnosed and fixed this exact
  defect for `data/processed/` and `data/snapshots/` and left it in the one
  file the project is about.** Now read with `float_precision="round_trip"`,
  pinned by a test that asserts the **committed file** is byte-identical after
  a load/save cycle — a synthetic fixture would have passed while the real file
  failed, because which cells drift depends on the decimals the file holds.
- **The liquidity gate is validated on NFL, and on EPL its interval has now
  moved off zero.** It had gated every price this project ever recommended
  without once being checked. Measured as quote persistence: a gate-rejected
  NFL quote raises its ask by at least a tick before the next capture
  **13.92%** of the time against **5.25%** for an accepted one — **+8.67pp, CI
  [+5.6, +13.0]** on 9,264 pairs, resampling *contracts* rather than quotes
  (run 14: +10.7pp, CI [+6.4, +16.4] on 5,122). The 5% relative-width rule
  **in isolation** — the one run 13 named as unvalidated — was **+18.1pp, CI
  [+7.6, +32.3]**.
  - **EPL moved from nothing to a weak positive**: **+1.6pp, CI [-0.4, +5.6]**
    on 3,540 pairs at run 14, **+2.57pp, CI [+0.72, +6.92]** on 5,490 at run
    17 (5.98% against 3.41%). Read with its caveats: this is the **second look
    at the same question on a growing sample** — the same optional-stopping
    mechanism the pre-registered cohort above declines to exploit — and a lower
    bound of +0.72pp is a weak positive a third look could take back. The gate
    is **evidenced** on both leagues, not validated on both. **Nothing was
    changed on the strength of it**, in either direction.
  `cli fill-quality`. **This is quote persistence, not fill quality** — no
  order has ever been placed, and none can be while `live_enabled` is false.
- **The gate has never rejected a quote near kickoff.** 0 of 1,084 NFL
  rejections and 1 of 880 EPL ones sit inside T-72h; depth builds as a game
  approaches. It is a filter on early boards — which is where this ledger
  works, 57% of its non-void rows priced more than 72h out.
- **A float comparison was under-counting the venue's most common move.**
  `0.41 - 0.40` is `0.00999999999999995`, so `delta >= 0.01` is *False* for an
  exact one-tick rise, while `0.33 - 0.32` rounds the other way and registers.
  Every number in the two bullets above moved when it was fixed, and the EPL
  width-rule figure **changed sign** (-1.4pp to +0.8pp; both straddle zero, so
  the conclusion held and the sign I would have reported did not). Caught by a
  test written after the analysis, not before. Prices are integers on this
  venue and are now compared as integers.
- **ESPN's date-range API disappeared and was replaced the same run.** The
  `YYYYMMDD-YYYYMMDD` scoreboard form now returns HTTP 400 for every range on
  both leagues — probed down to a 7-day window, while single days, months and
  years all return 200, so it is the range *syntax*. `fetch_espn_games` walks
  whole months and trims to the window. Month-vs-day equivalence was checked
  before being relied on (48 NFL / 30 EPL events either way, zero ids in one
  and not the other), and both committed ESPN tables came out **byte-identical**
  to the range-fetched version. The cross-check source degraded loudly and
  nothing already correct became wrong — which is what it was designed to do.
- **The CLV mean is a fraction of a tick, and that is how it should be read.**
  One 1c Kalshi tick is worth **3.3915%** `clv_pct` at the prices this ledger
  pays — *(run 19 corrected this from 3.5253%; the old figure used the wrong
  formula, see Status)* — so the current **-0.281%** real-close figure (n=19)
  is **0.083 of a tick**, far below the smallest change the venue can express;
  the **median is exactly 0.000%** and **42.9% of settled rows closed at the
  price they were struck at**. `ledger-summary` prints a `clv_resolution` block
  beside the mean, and a `clv_precision_real_close` block beside that.
  **This does not mean CLV is unmeasurable here** — run 13's first draft said
  so and the arithmetic refused it. But the convergence estimate has moved
  twice and is not a schedule: SE is now **0.546 ticks** and **~90** real-close
  rows would resolve a quarter tick, against the ~30 runs 17–18 projected from
  a smaller, quieter cohort. The instrument works and reads **no detectable
  edge**.
  - **And it has now been asked, for the first time, whether CLV predicts
    anything here. It does not — at this n.** Splitting the 17 real-close rows
    by CLV sign: CLV<0 wins 2 of 6 (ROI -22.87%), CLV=0 wins 1 of 8 (-34.21%),
    CLV>0 wins 1 of 3 (**-38.27%**). **No ordering at all**, with the worst ROI
    on the *positive*-CLV cohort. At n = 6/8/3 that is noise and must be read
    as noise — it is **not** evidence that CLV is inverted. It is the first
    direct look at whether this project's leading indicator leads anything.
- **The whole pre-kickoff window is quiet, not just the final hour.** Run 9
  showed the last hour barely moves; run 13 replicated that on a second slate
  (28 NFL contracts) and measured the rest: over a median 74h window with 29
  captures per contract, mean |net move| is **0.0157** (NFL) and **0.0107**
  (EPL), and **30% of NFL contracts never move a single tick**. This is
  evidence against the one direction run 12 left open — a line that never moves
  is not a line leaving late information unpriced.
- **The free information Elo cannot see makes the ranking worse, not better —
  so run 11's proposed direction is now itself a rejected change.** nflverse
  ships rest, short weeks, divisional games, neutral sites, roof, weather and
  starting-QB ids, and the ingest was discarding all of it. Carried, fit
  walk-forward as a logistic on `[elo_diff + context]`, and scored on AUC over
  1,408 games (2020-2024), every tier ranks **below** an elo-only control:
  schedule **-0.0111** [-0.017, -0.005], weather **-0.0126** [-0.020, -0.006],
  qb -0.0071 [-0.017, +0.003]. None approaches the market (0.7288). Sweeping
  the L2 penalty over 15 (tier, C) settings finds **no setting where context
  beats the control** — the best is qb at C=0.1, -0.0045 with a CI straddling
  zero. **Nothing adopted.** `cli context-report --sweep-regularization`.
  - The coefficients are *sensible* — `neutral_site` lands at **-0.4534**,
    correctly undoing most of the flat +55 Elo hands a team that is not home.
    It applies to 54 of 2,499 games, so being right about 2.2% of the sample
    does not pay for the variance added to 100% of it.
  - Two tiers **improve log-loss while ranking worse**. That is exactly the
    trap run 11's AUC bound exists to catch, and it would have read as an
    improvement under every metric this project used before run 11.
- **A per-season refit is not a monotone transform, and the control caught
  it.** A logistic on `elo_diff` alone must reproduce baseline Elo's AUC
  exactly; pooled it did not (0.68389 vs 0.68532). Cause: the model refits each
  season, so the window is five *different* monotone transforms. Per season the
  control ties at **exactly 0.0, all five**. So the control is asserted per
  season, and the yardstick for the features is the elo-only tier rather than
  raw Elo — otherwise the refit effect (-0.0014) would have been credited to
  the features and made the result look better than it is. Run 11's bound is
  untouched: it concerns a single fixed transform, and this effect is two
  orders of magnitude short of the -0.046 gap to the market.
- **The NFL model's problem is discrimination, not calibration — which rules
  out every recalibration-shaped change at once.** Over all 1,942 priced games
  in the canonical window, model AUC is **0.678** against the market's
  **0.724**; paired bootstrap gap **-0.046**, 95% CI **[-0.064, -0.030]**, and
  the model ranks better in **0 of 5,000** resamples. AUC is invariant under
  any monotone transform, so no threshold move, no shrinkage, no Platt or
  isotonic fit, no fee-inclusive edge can close it — none of them reorder
  anything. The Murphy decomposition agrees: the model's deficit is mostly
  **resolution** (0.0241 vs 0.0372), not reliability (0.0055 vs 0.0005). And
  an *oracle* recalibration — isotonic fit on the very outcomes it is scored
  on — still only reaches log-loss **0.635** against the market's **0.610**.
  This is the answer to run 10's closing question, and it retires a whole
  family of proposals. `cli discrimination-report`.
- **Run 4's pre-registered prediction has resolved on 25 of 36 wagers, and the
  model's own claim is the hypothesis it falsifies.** Actual **6** wins against
  **10.32** claimed and **8.53** market-implied; at 23 wagers it was 6 against
  9.45 claimed, 7.22 selection-corrected, 7.77 market-implied, with the NFL leg
  the sharp one (corrected **4.09**, market 4.82, claimed 5.87, **actual 4**).
  Exact Poisson-binomial P(X ≤ 6) is **0.0509** under the model's claim, 0.1896
  market. **That is not a rejection**, and specifically not one that "just
  crossed" a threshold: this is the **third scoring of the same growing sample
  against the same hypothesis with no correction for having looked**, which is
  optional stopping — the mechanism that manufactures a p-value near 0.05 out
  of nothing. **The honest read is the one taken at 36, on 09-21.**
  - **Do not substitute `scorecard`'s `p_at_most_model` for this number.** It
    scores *every* settled row, not the cohort. At run 17 it reads **0.0385**
    while the pre-registered 25-of-36 reading is **still 0.0509** — the gap is
    one non-pre-registered row, not a trend. `cli scorecard` for the former;
    reconstruct the cohort from `placed_at` (1 row 09-10 + 35 rows 09-11) for
    the latter.
- **The market beats the model on every scoring rule, on the bets the model
  itself chose.** Model log-loss **0.6535** vs market **0.6030**; Brier 0.2318
  vs 0.2057; model overstatement **+15.0pp** vs the market's +7.7pp.
- **CLV is a function of reference staleness, not of skill — and not of the
  league either.** Run 9 split mean CLV by leg (NFL -1.03% on a real close,
  EPL +3.00% on a stale one). Run 10 split it by the thing actually doing the
  work, the **reference lag**, and the effect holds *within* the EPL leg as
  well as between leagues:

  | reference | n | mean CLV | pos / zero / neg |
  |---|---|---|---|
  | real close (≤1h) | 14 | **-1.41%** | 2 / 8 / 4 |
  | stale (>1h) | 9 | **+4.04%** | 5 / 4 / **0** |

  The 2 EPL wagers that *do* have a real close read **-3.19%**; the 8 stale
  ones read +4.55%. Every positive reading this project has published came
  from a reference that was not a close, and the stale cohort's +4.04% is
  *exactly* run 8's old headline — which is what confirms the decomposition.
  The lag is now stored per row (`clv_reference_lag_h`) and `ledger-summary`
  reports the two cohorts apart, so the blended average can no longer be
  quoted as a measurement. **12 of 23 readings are exactly 0.00%**, and CLV
  does not separate winners (+0.01%) from losers (+0.98%) in this sample.
- **The final hour is measured at last, on 26 contracts, and it barely moves.**
  Against a reference 25 minutes before kickoff: T-1h..T-2h mean |move|
  **0.0038**, median **0.000**, max 0.01, and **not one of 26 contracts moved
  as much as two cents**. **`*/15` capture is therefore rejected**; `*/30`
  stays. Moving the reference from T-8h to T-0.42h shifts the measured price
  by only ~0.6c -- which is *about the size of the entire effect being
  measured*, and is why the pre-cron CLV numbers were misleading rather than
  merely imprecise.
- **The 94 unmatched NFL settled markets are explained and the item is
  closed.** All 94 are **August dates -- preseason**, which nflverse does not
  carry at all (the 2026 table starts 2026-09-09). Never a defect, but it was
  reported in a way that could hide one: a real mapping failure on a covered
  date would have had to move a counter already reading 94. `verify_against_stats`
  now splits `unmatched` into out-of-coverage vs **in-coverage**, using
  per-season windows from the stats table. NFL: 30 checked, **30 agreed**, 94
  out of coverage, **0 in coverage**. Soccer: 117 / 117 / 0 / 0.
  **This is a reporting fix, not a bug fix -- the tally stays at 12.**
- **Within the settled cohort, the bigger the claimed edge, the bigger the
  overstatement — but most of that is an identity.** Split at the median
  claimed edge (17.1% at run 17): the low half realized 1.33 wins below its
  claim, the high half **3.37 below**, replicating a direction first seen at
  n = 11 and 12. **Run 18 decomposed it and the headline shrank.** Because
  `claim_gap - market_gap == market - claimed`, sorting on claimed edge
  mechanically separates the claim gap; on the backtest that accounts for
  **79-160%** of the separation and on the ledger **32%**. The ledger's
  residual is real (the high half's fair ROI is -39.36%) and **does not
  replicate** — two backtest windows of the same league disagree about its
  sign. Read this against the market, not against the model's claim.
  `cli sweep-edge-cap`.
- **The betting rule, not the rating engine, is the main defect.**
  Unconditionally NFL Elo is roughly calibrated. Conditional on a side being
  *bet* it overstates its win probability by **13.7 points**, in every
  probability bucket; on sides it *passes* it understates by 9.3. That is the
  winner's curse. `cli selection-audit`.
- **Elo carries no information the closing line lacks.** Blending
  `w*model + (1-w)*market` is optimised at **w = 0** for NFL, with log-loss
  monotonically worse in w; EPL lands on w = 0 for 5 of 6 holdout seasons.
- **The model loses at both venues, and the exchange is the dearer one.**
  Moving the NFL sample to Kalshi takes ROI from **-8.21% to -11.48%**. The
  tighter book is worth +2.1pp; the trading fee gives back -5.4pp.
  `cli venue-report`.
- **Why the cheaper venue costs more:** a sportsbook's vig is proportional, so
  its toll is flat at ~3.2% of stake at every price. Kalshi's fee is quadratic
  in notional, so as a fraction of *stake* it is `rate x (1 - price)` -- 3.3%
  on a 70c favourite, **10.6% below 15c**. The bet rule places **88.6% of its
  bets below even money**. NFL ROI is negative at every fee rate **including
  zero** (-6.10%), so the conclusion does not rest on the one coefficient
  Kalshi's API will not expose.
- **The EPL expiration lag is measured, not assumed: exactly 3.00h on 13/13
  contracts.** NFL is 3.00h x 27 and 6.00h x 3 in the same window.
- **Settlements are independently cross-checked and all agree.** 34/34 NFL and
  120/120 soccer, against ESPN's public scoreboard as a third opinion rather
  than Kalshi's own resolution alone. `espn-audit` is read every run, not
  assumed: NFL 17/17 scores and kickoffs, EPL 40/40. Its `only_espn: 6` on
  soccer is six `STATUS_SCHEDULED` fixtures with no scores — upcoming games,
  not a results gap; checked rather than assumed, because "the cross-check
  found six games the primary lacks" is the shape of a real problem.
- **160 model configurations backtested, plus 15 context-feature fits in run
  12 and 11 bet-rule bands in two phases in run 18. None beat the market.**
  Nothing adopted, `live_enabled` is `false` everywhere. The last ten
  configurations were run 17's `season_regression` grid — the one parameter
  the main sweep never varied, now closed. Run 18's edge caps are counted
  apart because they are a different kind of object: they change which sides
  get bet, not how any side is priced, and folding them into the model tally
  would inflate it.
- **EPL's +8.27% ROI is retired.** Re-run with each season as holdout it is
  1 of 6 positive; pooled **-8.30%**, sd 9.33pp.
- **Twelve bugs of one shape so far**, all a value that was not what the
  surrounding code assumed -- most recently the ledger counting every bet
  twice (run 7) and three caught inside run 8's own new code. See
  "Known-bad numbers" below. **The tally stays at 12 after run 12**: the
  pooled-control discrepancy it found was caught by a control written to catch
  it, before any number rested on it, which is the system working rather than
  a thirteenth failure of it.
- **Next pre-registration, written before the games:** the 13 wagers (12 NFL,
  1 EPL) settling through 2026-09-21 -- claimed **5.74**, selection-corrected
  **4.05**, market-implied **4.72**. **2 have settled, 0 wins**; the 11 still
  open are all NFL, kicking off 09-20T17:00Z to 09-21T00:20Z, carrying **4.87
  claimed** and **3.96 market-implied**. Both this and the 36-wager cohort
  reproduce from `placed_at` digit-for-digit and are to be scored **once, on
  09-21**.
- **The claimed-edge overstatement is the most consistently replicating result
  in the project.** Splitting the 26 settled rows at the median claimed edge
  (17.1%): the low-edge half won 4 of 13 against 5.33 claimed (**-1.33**, ROI
  **-7.54%**), the high-edge half 2 of 13 against 5.37 claimed (**-3.37**, ROI
  **-40.28%**). Run 9 measured -0.55 / -2.89 at n = 12/11. Same direction,
  larger gap, and it is run 4's selection-audit signature seen in realized
  results rather than backtest. **It is still 13 and 13.**

## Why these data sources

| Need | Source | Cost | Notes |
|---|---|---|---|
| NFL schedules, scores, closing lines (historical) | [nflverse](https://github.com/nflverse/nfl_data_py) | Free, no key | Ships actual closing moneyline/spread/total per game. Also ships the pre-kickoff context run 12 tested and rejected (rest, divisional, neutral site, roof, surface, temp, wind, starting QB) — carried since run 12, **never read by Elo** |
| Soccer results + closing odds (historical) | [football-data.co.uk](https://www.football-data.co.uk/) | Free, no key | CSV per league/season; uses bookmaker-average (`Avg*`) columns when available. **Recovered 2026-09-18** after 34-48h of every path redirecting to `http://127.0.0.1/`; the table it was replaced with came back byte-identical. While down, the committed table is used, and only while ESPN confirms it is missing no played game (`ingest/sources.py`). |
| **Live market odds (both sports, ongoing)** | **[Kalshi](https://kalshi.com)** public REST API | **Free, no key** | CFTC-regulated exchange; read-only market data needs no auth. Each contract's dollar price *is* the market-implied probability. `KXNFLGAME` / `KXEPLGAME` series. |
| **Settlement cross-check + kickoff times (both sports)** | **[ESPN public scoreboard](https://site.api.espn.com/apis/site/v2/sports/)** | **Free, no key** | Undocumented endpoint behind espn.com's scoreboard. Schedules and results only — **no odds, never feeds the model**. Publishes within minutes of full time, where football-data.co.uk publishes in batches days later. Verified against the primary source: 30/30 scores and 30/30 kickoffs agree (`cli espn-audit`). |

**Rejected, on the merits, and closed** — these are not open asks and should
not be re-raised:

| Source | Status | Why |
|---|---|---|
| [The Odds API](https://theoddsapi.com/) (~$29/mo for NFL+soccer) | **Rejected, run 2** | Kalshi covers live odds for both leagues free, and run 5's venue work showed the two price the same games the same way (corr 0.9955 over 28 games). Paying for a second view of a number we already hold is not worth $29/mo to a project with no validated edge. |
| [football-data.org](https://www.football-data.org/) (free tier, needs a human-created key) | **Rejected, run 3 — as unnecessary, not blocked** | It was wanted only for kickoff times. football-data.co.uk already ships them in a column the ingest was discarding, and ESPN now covers the gap for unpublished fixtures. |

Kalshi was not part of the original plan — it came up mid-build as a
free alternative to a paid odds API, and turned out to cover exactly the two
leagues we're starting with, so it's now the primary live-odds source.

## Architecture

```
src/sportsedge/
  ingest/       nfl_stats.py, soccer_stats.py (historical), kalshi.py (live odds)
                teams.py (Kalshi ticker -> stats-source team resolution)
                espn.py (settlement cross-check + kickoffs; carries no odds)
                sources.py (what to do when an upstream stats source is down:
                            degrade to the committed table, but only while an
                            independent source says it is missing nothing)
  models/       elo.py (rating engines), calibration.py (soccer 3-way outcome calibration)
                live.py (current-strength ratings for pricing today's games)
                features.py (pre-kickoff context: rest/venue/weather/QB — TESTED
                             AND REJECTED, run 12; kept as the evidence)
  backtest/     engine.py (walk-forward backtest, no lookahead), metrics.py
                sweep.py (parameter grid vs the closing line)
                selection.py (winner's-curse audit + model-vs-market blend)
                discrimination.py (calibration or ranking? bounds recalibration)
                context.py (does non-Elo information rank better? + L2 sweep)
  betting/      edge.py (de-vig, EV, Kelly), ledger.py (bets/ledger.csv)
                scorecard.py (settled bets vs model AND market, effective n)
                liquidity.py (is this quote fillable?), recommend.py (model vs market)
                settle.py (resolve bets, compute CLV)
                line_movement.py (price drift by time-to-kickoff)
                fill_quality.py (does a gate rejection predict an adverse move?)
                edge_decay.py (does a claimed edge survive to kickoff? as-of
                               model, no lookahead; market leg vs model leg)
  journal/      entry.py (dated markdown journal entries)
  storage/      db.py + schema.sql (SQLite historical database)
                snapshots.py (committed odds capture — see below)
```

### Odds snapshots are the one irreplaceable asset

`data/snapshots/<sport>/<date>.csv` is deliberately **not** gitignored. Live
odds cannot be reconstructed after the fact, and each session runs in a fresh
container, so these committed CSVs are the only durable record. Closing-line
value depends entirely on having captured a price before kickoff — a missed
snapshot window is permanently missing data.

### Team resolution: the ticker order differs by sport

Kalshi encodes both teams in the event ticker, but **not in the same order**:

- NFL is `AWAY+HOME` — `KXNFLGAME-26SEP21NYGLAR` is NYG *at* the Rams.
- EPL is `HOME+AWAY` — `KXEPLGAME-26SEP06ARSCFC` is Arsenal *hosting* Chelsea.

Both were verified against the stats sources (nflverse, football-data.co.uk)
rather than assumed, and both are pinned by tests. Getting either backwards
inverts every prediction for that sport while leaving aggregate metrics looking
entirely plausible.

### Model approach

- **NFL**: standard Elo (`k=20`, home advantage `+55` rating points), with an
  optional margin-of-victory K-scaling (the well-known 538-style multiplier),
  gated behind a flag so it can be A/B'd in backtest before ever being turned
  on for real recommendations.
- **Soccer**: Elo strength ratings + a **multinomial logistic regression**
  fit on prior-season (elo_diff → H/D/A outcome) pairs to produce calibrated
  3-way probabilities. This was a deliberate choice: rather than hard-code an
  assumed draw-probability formula, the draw/win/loss split is learned from
  real historical outcomes and evaluated out-of-sample (fit on seasons 1–5,
  tested on season 6, walk-forward within each).

### Betting methodology

1. Compute model win probability for each side of a market.
2. De-vig the market's own implied probabilities (two-way for NFL moneyline,
   three-way for soccer 1X2) to get a fair-odds baseline for comparison.
3. Drop any quote that isn't actually fillable (`betting/liquidity.py`: spread,
   resting size, traded volume, extreme prices). On EPL this currently removes
   ~⅓ of contracts — pricing off a stale book manufactures fake edges.
   Validated in run 14 against quote persistence (`cli fill-quality`): on NFL
   the rejected quotes really are the ones that move against you; **on EPL the
   same test finds nothing**, so that league's thresholds are buying coverage
   loss without buying reliability. Unchanged pending a backtest.
4. `edge_pct = model_prob * decimal_odds - 1`, **priced at the ask**, not the
   mid. The ask is what you'd actually pay; using the mid silently credits the
   model with half the spread on every bet. A paper bet is only logged if edge
   clears **`edge_threshold_pct`** (default 3%, see `config/leagues.yaml`).
5. Stake sizing uses **fractional Kelly** (`kelly_multiplier = 0.25` by
   default) — never full Kelly, which is too volatile for a model with
   uncertain calibration.
6. Every bet, win or loss, goes in `bets/ledger.csv` with model prob, market
   odds, edge, and (once the game closes) closing odds and CLV — closing
   line value is tracked independently of win/loss because it's a better
   short-run signal of whether the model has real skill than win rate alone.

## The deployment gate: shadow vs. live

`live_enabled` in `config/leagues.yaml` is `false` for every league, and stays
false until that league's model **beats the de-vigged closing line
out-of-sample** — not merely improves on an earlier version of itself.

While it's false the recommender still runs, but every row it writes is a
`shadow` bet: recorded as evidence, reported separately, never folded into
headline win rate or ROI. A model that loses to the market and gets deployed
anyway just launders a bias into a bet history.

Flipping that flag is the single decision that turns this from a research log
into a betting record. It should never happen as a side effect of another
change.

## Backtesting discipline

**No model change goes live without being backtested first, and the backtest
result goes in the journal even if it's bad.** The walk-forward backtest
(`src/sportsedge/backtest/engine.py`) only ever uses information available
before each game to make that game's prediction — ratings update strictly
after the prediction is recorded, so there's no lookahead leakage.

Run it yourself:

```bash
pip install -e ".[dev]"
python -m sportsedge.cli backtest-nfl       # canonical window, 2018-2024
python -m sportsedge.cli backtest-soccer    # canonical window, 1920-2425
python -m sportsedge.cli selection-audit    # is the model wrong, or the bet rule?
python -m sportsedge.cli discrimination-report   # is it calibration, or ranking?
python -m sportsedge.cli sweep-season-regression # the knob the main grid never turned
python -m sportsedge.cli sweep-edge-cap          # should the rule stop taking
                                                 #  its own biggest claims?
```

**A sweep that adds configurations to the canonical window is another look at
that window.** `sweep-season-regression` (run 17) is therefore two-phase:
values are selected on 2021-2023 and the selected value is confirmed on 2024,
which is untouched during selection. It also reports **AUC beside log-loss**,
because run 12 found two feature tiers that improved log-loss while ranking
worse — and run 17's log-loss pick did exactly that again on the holdout.
Any future parameter sweep should copy this shape rather than `sweep-nfl`'s.
`sweep-edge-cap` (run 18) copies it.

**For a rule that changes which sides get bet, the gate is ROI at de-vigged
fair odds**, not book ROI. Stake $1 per selected side and settle it at
`1 / fair_market_prob`: then 0 means the selection knows exactly what the
closing line knows, and positive means it carries information the line lacks.
Book ROI is fair ROI minus the vig, so it is negative for a rule with no
information at all, and a rule that merely pays less vig has discovered
nothing. `sweep-edge-cap` reports both and gates on the first.

Both backtests now **default** to the canonical window rather than requiring
`--seasons`. The windows used to live only in journal prose, and the example in
`cli.py`'s docstring was a different one: 2020-2024 returns -9.84% and
2223-2425 returns -8.46%, both plausible-looking numbers that are not the
pinned ones. `tests/test_benchmarks.py` pins all four exactly, so a real drift
fails CI instead of being spotted by eye. Pass `--seasons` only to ask a
different question, and state the window whenever you quote the answer — the
EPL holdout ROI moves about nine points on that choice alone.

`selection-audit` answers the two questions a parameter sweep cannot: whether
the model's errors are concentrated in the sides it chooses to bet (the
winner's curse), and whether any blend weight on the model beats the closing
line it is betting into.

## Setup

```bash
pip install -e ".[dev]"
pytest                                  # 301 tests, no network needed
cp .env.example .env                    # only needed for optional sources
python -m sportsedge.cli kalshi-nfl     # live NFL market snapshot, no key needed
python -m sportsedge.cli kalshi-epl     # live EPL market snapshot, no key needed
python -m sportsedge.cli ingest-nfl --seasons 2023 2024
python -m sportsedge.cli ingest-soccer --league E0 --seasons 2324 2425
python -m sportsedge.cli ledger-summary
```

### The recurring loop

```bash
python -m sportsedge.cli snapshot-odds        # capture live odds (run often!)
python -m sportsedge.cli recommend --dry-run  # see picks without writing
python -m sportsedge.cli recommend            # write to bets/ledger.csv
python -m sportsedge.cli settle               # resolve finished games, fill CLV,
                                              # and recover CLV on rows that
                                              # settled before the stats source
                                              # published their kickoff
python -m sportsedge.cli verify-settlements   # cross-check Kalshi vs stats source
python -m sportsedge.cli scorecard            # model vs market vs reality on
                                              # settled bets, with effective_n
python -m sportsedge.cli edge-decay           # does a claimed edge survive the
                                              # walk to kickoff, or is it a book
                                              # that has not opened yet?
```

`scorecard` is the one that answers the project's actual question. A low win
rate is not evidence against the model -- the rule bets longshots, so a low win
rate is what a *correct* model looks like. The test is whether the model's
probabilities beat the closing line's **on the bets the model chose**, which is
the narrowest place the two disagree and the only place money moves. It reports
both, plus an exact Poisson-binomial P(X <= k) so the reader sees the
expectation next to the tail probability, and counts `effective_n` on distinct
`(contract, selection)` wagers rather than ledger rows.

`recommend` is idempotent per (contract, model version), so re-running on a
schedule won't inflate the bet count.

## Journal discipline

Every meaningful session (data refresh, model change, backtest run, bet
settled) gets a dated entry in `journal/` via `src/sportsedge/journal/entry.py`.
Entries record what worked, what didn't, and why — including negative
results. **A few weeks of results is noise; the point is signal, not
confirming a bias.**

## The venue: we backtest against a sportsbook, we would trade on an exchange

`cli venue-report`. Kalshi's public API serves the current board, not a price
history, so **a Kalshi backtest of 2018-2024 does not exist** and this module
does not claim one. What it does is measure the venue and substitute it into
the historical sample. The measurements are real:

| measured 2026-09-12 | value |
|---|---|
| Kalshi de-vigged mid vs sportsbook de-vigged fair, same 28 games | **corr 0.9955**, mean abs diff 1.26pp |
| Kalshi overround at the ask | +1.04% |
| Sportsbook overround, same games | +4.28% |
| Kalshi half-spread (672 NFL + 540 EPL quotes) | median **0.5c**, flat across every price bucket |

The forecast agreement is what licenses the substitution: if the two venues
price the same games the same way, "the model loses to the de-vigged closing
line" is a statement about both. Every simulated result carries
`simulated_at_venue: True` so it can never be quoted as an observed return.

Both venues run through the **same** walk-forward loop via a `pricer`, not a
second copy of it — the week-ordering bug lived in two copies and had to be
fixed twice. The default path reproduces -8.208908995992267% and log-loss
0.6517617405253826 exactly, pinned bet-for-bet.

## The fee is reported, not enforced

Kalshi's trading fee is the larger of the two execution costs (~4.7% of stake
against the spread's ~1.7%), and `recommend.py` prices at the ask only. So
`edge_pct` overstates every logged edge by roughly the fee — 5.39pp on the
open book. `edge_after_fee_pct` and `fee_assumption` now record it per row.

The threshold still tests `edge_pct`. That began as two blockers; run 10
cleared the first, and then found the change is not worth making anyway.

1. ~~**The rate is unverified.**~~ **Verified 2026-09-14 at exactly 0.07.** No
   endpoint states the coefficient, but the docs site mirrors every page as
   markdown (`docs.kalshi.com/<path>.md`, indexed in `/llms.txt`), and
   `getting_started/fee_rounding.md` works an example carrying both sides of
   the equation: a buy with `-$0.055000` signed revenue and a model fee of
   `$0.00363825`. One contract at 5.5c inverts to
   `0.00363825 / (0.055 × 0.945) = 0.07` exactly, and the other whole-contract
   splits of that revenue give ragged rates (0.0669, 0.0665, 0.0662), so the
   reading is unambiguous. Pinned by `kalshi_engine.FEE_RATE_FIXTURE` and
   re-derived on every test run.
2. **It would break a pre-registered prediction**, still, until 2026-09-21.
   13 wagers from run 4's cohort (12 NFL, 1 EPL) are open, and run 9
   pre-registered the same 13 again. A `PRICING_VERSION` bump re-prices open
   bets, so `void_superseded_rows` would void them a week before they resolve.
3. **And the change is rejected on the evidence.** Backtested at the simulated
   venue, selecting on the after-fee edge and settling at the same price:

   | leg | p2 (threshold pre-fee) | p3 (threshold post-fee) | |
   |---|---|---|---|
   | NFL | **-10.09%** (n=1724) | **-11.48%** (n=1556) | worse by 1.39pp |
   | EPL | **-11.07%** (n=373) | **-8.99%** (n=283) | better by 2.08pp |

   The legs disagree in sign at every fee rate from 0.01 to 0.10, and neither
   comes near beating the closing line — which is what the deployment gate
   asks for, not an improvement on p2. The mechanism is the reason to care:
   the NFL bets p3 removes are the **low**-claimed-edge ones (median +4.72%
   pre-fee, median price 47c), and run 9 measured the low-edge half of the
   settled book as the half whose claimed edge is *least* overstated. A
   fee-inclusive minimum is still a minimum on claimed edge, so it selects
   harder for the model's own overstatement: run 4's selection gap sharpened,
   not repaired.

The backfill is therefore strictly derived (`market_odds_decimal` is 1/ask by
construction); no price, stake, status, selection or `pricing_version` moves.
`test_backfill_after_fee_is_derived_not_a_repricing` asserts that.
`test_fee_does_not_change_which_bets_are_flagged` and
`test_threshold_still_tests_the_pre_fee_edge` pin the decision above: a side
whose edge clears the threshold before the fee but not after it must still be
flagged. They pin the behaviour, not the opinion — a future run with a better
reason may still move it, as a `p3` bump, after clearing the deployment gate
in backtest.

## Known-bad numbers (withdrawn)

**Every bet count published before 2026-09-13 run 7 -- inflated.** Not a wrong
price but a wrong *population*: `ledger.existing_keys` includes
`pricing_version` so that a pricing bump makes an open contract eligible to be
priced again, which is correct, but re-pricing is a replacement and the code
only ever performed the insert. The 2026-09-11 p1 -> p2 bump therefore
duplicated 35 wagers rather than replacing them, and both copies always carried
the same outcome. 75 non-void rows were **40 distinct wagers**; "74 pending"
was 32, and run 4's "70 pre-registered bets" were **36**. Point estimates
survive (each pair scales claimed and realized identically) but every n was
doubled and every CI was narrow by ~sqrt(2). NFL looked handled only because
its model version happened to move at the same time and *that* path did void
its predecessors. Repaired by voiding the superseded half -- newest
`pricing_version` wins, settled duplicates included, since that is where the
double-count reaches win rate and ROI. Audited cell by cell: only `status`,
`result_logged_at` and `notes` moved. Fixed by `ledger.void_superseded_rows`,
run unconditionally inside `recommend`; `tests/test_superseded_void.py`.

**Headline ROI of -13.06% -- superseded, and not by an improvement.** The
de-duplication above takes it to +0.51%. Nothing got better: no bet changed
outcome and no price moved, but the single NFL win went from 1/15 of the book
to 1/8, taking its own ROI contribution from +11.85pp to +22.22pp. EPL alone is
-24.81% on 7 bets. Neither figure is a result at these sample sizes; the point
of recording both is that a correction moved the headline in the flattering
direction and that is exactly when to distrust it.

**Two EPL bets from 2026-09-12 run 6 -- voided.** Liverpool v Fulham and
Chelsea v Hull were priced at 15:11Z against fixtures that kicked off at 14:00Z,
by a pre-game Elo reading in-play quotes. Both sides bet had been marked *down*
by the market (Liverpool 0.66 -> 0.52, Chelsea 0.80 -> 0.41), so the "edge" was
the model's ignorance of the score. Not tradeable prices and not evidence about
the model. An audit of all 76 open rows against the new gate found exactly these
2 failing, so `PRICING_VERSION` deliberately did not move: there were no rows
priced under a superseded rule to invalidate, and bumping it would have re-logged
74 correct rows and disposed of run 4's pre-registered prediction. Gated by
`recommend.partition_in_play`; `tests/test_in_play_gate.py`.

**EPL closing-line value before run 6 -- a number that never existed.** Not a
wrong figure but an empty column: `settle_pending` fills CLV only for rows that
are still `pending`, and football-data.co.uk publishes only completed matches,
days late, so an EPL bet always settled before its kickoff could be resolved and
was never revisited. Recovered by `settle.backfill_clv`, which re-resolves the
kickoff and fills from the committed snapshots — still cutting at true kickoff,
never at Kalshi's expiry. `tests/test_clv_backfill.py`.

**NFL ROI before 2026-09-10 run 2 -- withdrawn.** The ingest stored `week` as a
string, so `"10"` sorted before `"2"` and each season ran 1, 10, 11 ... 18, 19,
2, 20 ... The model predicted week 2 from ratings that had absorbed weeks
10-18. Corrected 2018-2024 vanilla Elo is **-8.21% ROI, not -4.65%**. Log-loss
moved by ~0.001 and is effectively unaffected; all EPL figures are unaffected
and reproduce exactly. No adoption decision changes. Pinned by
`tests/test_backtest_order.py`.

**NFL CLV -- caught before it produced a number.** `commence_time` was
populated from Kalshi's `expected_expiration_time`, which lands **3-6 hours
after kickoff** on every NFL event measured (27 at +3h, 4 at +6h, 0 on time;
Kalshi has no kickoff field). Both closing-price paths treated it as kickoff,
so they could return an **in-play** quote. Demonstrated: `closing_quote_before()`
for SF @ LA returned bid 0.98 / ask 0.99 against an entry of 0.36 -- a CLV of
~+175% produced entirely by the clock, and one that would only ever look good
when the bet won. Nothing published depended on it: no candlestick CLV had been
computed and no snapshot contains an in-play row. Fixed by
`ingest/kickoff.py`; pinned by `tests/test_kickoff.py`.

**EPL's +8.27% ROI -- retired 2026-09-11 run 4.** It was reported on the
2025-26 holdout. Re-run with each season in turn as the holdout, the same
model and protocol give -11.76 / -6.57 / -12.19 / -19.35 / -5.12 / **+8.27**:
1 of 6 positive, pooled **-8.30%**, sd 9.33pp. The figure is the best of six
draws from a distribution centred near -8%, and its season has the
second-worst log-loss in the set. Never presented as validated; now treated as
withdrawn rather than merely uncelebrated.

**The committed tables were rewriting themselves on every read -- fixed, no
number affected.** pandas' default CSV float parser is not correctly rounded:
it read a stored `1.3690036900369003` back as `...005`. 585 of 2,499 NFL rows
drifted in the last bit on every refresh with no upstream change behind them.
Irrelevant at 1e-16, but it made `git diff` useless on the data (six genuine
line moves were invisible among 2,499 "changed" rows) and it meant reading the
irreplaceable snapshot store altered it. All reads now use
`float_precision="round_trip"`; pinned by `tests/test_snapshots.py`.

**Run 1's 102-config sweep is not reproducible.** Its script was never
committed and a faithful reconstruction does not match it (best 0.6396 here vs
0.6459 reported). The no-adoption conclusion is unaffected -- the gap to the
market is far larger than the discrepancy -- but the individual figures should
not be quoted. The sweep now lives in `backtest/sweep.py` with its protocol
documented.

### Where kickoff comes from, and why it matters

Kalshi timestamps are **never** a pre-game cutoff. Kickoff is resolved from the
stats sources only -- nflverse `gameday`+`gametime`, football-data.co.uk
`Date`+`Time` -- via `ingest/kickoff.py`. If a kickoff cannot be resolved, the
bet settles with **no CLV** rather than a guessed one: a missing number is
recoverable, a fabricated one is not.

An in-play price already knows the result. CLV computed against one is not a
noisy skill measurement, it is a restatement of win/loss -- which is why this
mattered more than the ROI bug that preceded it.

"Recoverable" became true rather than aspirational in run 6. Because
football-data.co.uk publishes only completed matches, and days late, an EPL
kickoff is *never* resolvable while the bet is open -- so "no CLV at
settlement" was permanent, not deferred, until `settle.backfill_clv` began
revisiting settled rows once the source catches up.

The same clock cuts the other way at the front of the pipeline:
`recommend.partition_in_play` refuses to *price* a game that has already
started. Where kickoff is unresolvable it infers one from the expiration minus
the sport's largest measured lag (NFL 6h, EPL 3h) -- deliberately the earliest
plausible kickoff, because inferring early costs a bet and inferring late
corrupts the record.

## Open questions / next steps

- **The honest null is now the leading hypothesis, and it is stated as one.**
  Sixteen runs, 160 configurations, a hard AUC bound retiring every
  recalibration-shaped change (run 11), a negative result on the obvious
  non-Elo information (run 12), run 15's finding that the market does not
  move toward this model over the entire tradeable window at either league,
  and run 17's finding that the never-swept rating parameter does not move the
  AUC gap either. Nothing found so far suggests a public-data team-strength
  model beats this closing line. That is a finding, not a failure — but adding
  further features without a reason to expect a different outcome would be.
- **The reasons against the remaining ideas are now six deep**: the AUC deficit
  is -0.046, CI [-0.064, -0.030] (run 11); context features rank worse (run
  12); the whole pre-kickoff window is quiet (run 13); season regression does
  not move the gap (run 17); the selection pathology that looked like the last
  available *bet-rule* lever is mostly an artifact of measuring the model
  against its own claim instead of against the price (run 18); **and run 20's
  promoted-team bias is real, mechanical, live — and correcting it changes
  nothing.** **There is no remaining bet-rule change with a reason to expect a
  different outcome, and the honest next step is the 09-21 cohort, not another
  parameter.**
- **Run 20's result is the most informative of the six, because of how it
  fails.** Runs 11, 12 and 17 rejected changes aimed at effects that turned out
  not to be real. Run 20 found an effect that **is** real — +0.0447, 8 of 8
  teams, a monotone decay with a mechanical explanation, and a live position on
  the board — fixed it out-of-sample, and got **nothing**: log-loss CI
  [-0.00255, +0.00058], ROI worse. That is evidence the deficit is **not
  concentrated in an identifiable subgroup waiting to be patched**, which
  retires a whole family of "find the bad subgroup" ideas rather than one of
  them. **Do not re-raise the promotion prior.** A promoted-team *feature*
  carrying information Elo lacks (form in the division below) would be a new
  question, and it is a data-source question, not a parameter question.
- ~~**The measurable question nobody has asked yet:** the gap between *claimed*
  edge and *realized* return has never been regressed, only split at the
  median.~~ — **run 18 regressed it**, on 930 backtest bets rather than
  waiting for the ledger. Regressing `won - fair_market_prob` on claimed edge
  gives **+0.463**pp per +10pp of claimed edge in 2021-2023 (CI [-0.30,
  +1.27]) and **-0.375** on the 2024 holdout (CI [-1.75, +1.24]): opposite
  signs, both straddling zero. The median split that motivated the question
  turns out to be 79-160% identity (see Status). **What remains open is the
  same regression on realized bets**, which needs a settled book much larger
  than 28 — 09-21 adds 11 rows at once, and that is still nowhere near enough.
- ~~**CLV is at 17 real-close rows and needs ~13 more to resolve a quarter
  tick.**~~ — **run 19 measured that projection and it was optimistic by a
  factor of three.** Two rows raised the SD 39%, so the requirement is **~90
  rows, not ~30**; the cohort is at **19**. The projection is unstable by
  construction because CLV variance scales with **placement lag**, which this
  project does not control (see Status). It is now reported as a running
  estimate, `n_for_target_se`, beside the mean.
  - The 11 open pre-registered wagers settle 09-20/09-21 with full final-hour
    coverage **and were struck at T-48h to T-56h**, so they should *lower* the
    SD. That is next run's falsifiable prediction.
  - **Read CLV in ticks.** One tick is **3.3915%** at this ledger's prices. The
    mean is **-0.105 ticks**, CI **[-1.175, +0.964]** — no detectable edge, on
    an interval of ±1.07 ticks.
  - **Do not propose betting later to tighten the estimate.** Placement lag is
    not a variance knob: it shrinks the noise and the estimand together.
- ~~**football-data.co.uk is down; the deadline is 09-19.**~~ — **the source
  recovered on 09-18**, and run 16's ESPN failover was built in time either
  way. ~~The failover is therefore still untested against a real gap.~~ —
  **run 19 tested it, and the gap was not an outage at all.** The primary is up
  and simply publishes on a lag: latest row 09-14, a played 09-18 fixture
  carrying two settled wagers. Primary alone leaves **3 settlements
  unmatched**; with the supplement, **123/123 agree**. **Validated**, and on a
  path that recurs every week rather than only when the host dies.
- ~~**A non-GitHub mirror of the football-data CSVs has not been looked for.**~~
  — **moot for now**; the source is back. The constraint run 16 recorded (that
  session's GitHub access was scoped to this repository alone) still holds and
  is still a fact about the runner, not about what mirrors exist.
- **Reconstructing an EPL closing line from `data/snapshots/`** is no longer
  needed to survive an outage, but it remains the only way to grow the EPL
  backtest sample with fixtures the bookmaker column never covered. Not urgent;
  doable from committed data at any later date.
- **The opening-book measurement is NFL-only, on 32 contracts.** No EPL
  contract listed during the capture window. Do not quote it as a fact about
  the venue until an EPL listing has been watched.
- **What would actually be a different bet:** information the closing line
  prices *late* or prices *badly*, not information it prices perfectly. Every
  feature run 12 tested is on the market's screen too, and the line-movement
  work says the final hour barely moves (26 contracts, none moved 2c), which
  is itself evidence the market is not leaving anything on the table here.
- **The selection gap is the thing to attack, not the ratings.** A model need
  not beat the market on every game to be bettable -- it needs to be right
  about *which* games it disagrees on. Nothing measured so far suggests Elo
  is. Elo parameter tuning is exhausted (160 configs, none beat the market)
  and retuning cannot reach a selection bias in any case.
- **Do not "fix" the selection gap with a price or edge filter without a real
  test.** Every price bucket in the NFL backtest is ROI-negative (best
  -3.90% at market >=0.50, CI [-18.9, +11.1]). A filter that improves
  backtest ROI here is selecting on noise. **Run 18 ran that real test on the
  edge filter and it failed** — 0 of 11 caps beat the closing line in either
  phase, and the best eligible one lost to doing nothing where it was chosen.
  The 29-bet band that posted +4.32% is precisely the noise this bullet warns
  about, and `sweep-edge-cap`'s pre-specified 100-bet eligibility floor is
  what keeps it from being adopted.
- **Beware the blend sweep's own bait.** It reports +10.19% ROI at w=0.05 --
  on 32 bets, CI [-73.9, +94.3], from a weight log-loss says is worse than
  betting nothing. It regenerates on every run. `summarize_blend` prints such
  rows with their log-loss delta attached for this reason.
- ~~Build the Kalshi-venue backtest~~ -- **done in run 5**
  (`backtest/kalshi_engine.py`). The exchange is the *dearer* venue: NFL ROI
  -8.21% at the sportsbook, -11.48% simulated at Kalshi.
- **Run 4's pre-registered prediction has resolved on 23 of 36 wagers, and it
  resolves against the model.** Actual **6** wins vs 9.45 claimed / 7.22
  selection-corrected / 7.77 market-implied; NFL leg actual **4** vs corrected
  **4.09**. P(X <= 6) = 0.095 under the model's own claim -- in the tail, but
  **not a rejection at any conventional level**, and 23 wagers settles nothing
  by itself. **Next pre-registration, written before the games:** the 13
  still-open wagers (12 NFL, 1 EPL) settling through 2026-09-21 -- claimed
  **5.74**, corrected **4.05**, market **4.72**.
- ~~The settled results are single-sourced~~ -- **cross-checked in run 8** and
  clean since: 30/30 NFL and 117/117 soccer agree against ESPN's public
  scoreboard. ~~NFL shows 94 unmatched settled Kalshi markets~~ -- **explained
  and closed in run 9: all 94 are August dates, i.e. preseason**, which
  nflverse does not carry (the 2026 table starts 2026-09-09). Not a defect,
  but it was reported in a way that could have hidden one, so `unmatched` is
  now split into out-of-coverage vs **in-coverage**; the in-coverage count is
  the one to watch and it is **0** on both sports.
- ~~Snapshot cadence is the binding constraint on CLV~~ -- **fixed 2026-09-13**
  by `.github/workflows/snapshot-odds.yml`, every 30 min, 10:00-04:00 UTC.
  It had looked like an account-level schedule no session could change; it was
  never a schedule problem. **Every CLV computed before that workflow's first
  run is still a T-8h to T-11h number and should be read with that attached.**
- ~~The final hour is unmeasured~~ -- **measured in run 9 on 26 NFL contracts**
  against a reference 25 minutes before kickoff. It barely moves: T-1h..T-2h
  mean |move| **0.0038**, median 0.000, and **not one of 26 contracts moved as
  much as two cents**. **`*/15` is rejected on that evidence; capture stays at
  `*/30`.** The useful number is the gap between buckets: moving the reference
  from T-8h to T-0.42h shifts the measured price only ~0.6c, which is about
  the size of the whole effect being measured -- so the pre-cron CLV readings
  were misleading rather than merely imprecise. Still one high-liquidity NFL
  slate, so "quiet" is the best case, not the typical one.
- **CLV may not be a usable signal at this venue at all, and every positive
  reading so far came from a stale reference.** Run 10 split the 23 settled
  rows by reference lag rather than by league: **≤1h reference, n=14, mean
  -1.41%; >1h reference, n=9, mean +4.04% with not one negative reading.** The
  split holds *within* the EPL leg (2 real closes read -3.19%, 8 stale read
  +4.55%), so it is a property of the measurement, not the sport. **12 of 23
  readings are exactly 0.00%** and CLV does not separate winners (+0.01%) from
  losers (+0.98%). The lag is now stored per row and reported apart, so the
  blended average cannot be quoted as a measurement. Given a market whose
  entire observed movement inside two hours is one cent, the open question is
  no longer "is the CLV number believable" but "can CLV measure anything
  here". ~~Decide it once the real-close cohort is large enough to have a
  usable standard error — not before.~~ **Decided in run 13: yes, it can.**
  The cohort's SD is 4.107%, so at n=16 the SE is **1.027% — already inside
  half a tick**, and ~30 real-close rows (about two more NFL weekends) would
  resolve a quarter tick. The reading is **no detectable CLV edge**: mean
  -1.14%, CI [-3.25, +0.64], a span of ~1.3 ticks. What is *not* licensed is
  quoting the -1.14% as a magnitude — it is 0.38 of a tick, and half the rows
  behind it never moved. `clv_resolution` in `ledger-summary` carries that
  context so it cannot be dropped again.
- ~~Kalshi's fee coefficient is unread~~ -- **read and verified in run 10 at
  exactly 0.07**, by inverting Kalshi's own worked example rather than finding
  a page that states it. See "The fee is reported, not enforced" above.
  Moving the threshold onto the fee-inclusive number (`p3`) was then
  backtested and **rejected**: it makes NFL worse, the legs disagree in sign,
  and neither clears the deployment gate.
- ~~Measure the EPL expiry lag rather than assuming 3h~~ -- **measured in run
  8: exactly 3.00h on 13/13 contracts**, via ESPN kickoffs rather than waiting
  for football-data.co.uk. The assumed constant was right. NFL in the same
  window is 3.00h x 27 and 6.00h x 3.
- **Audit the remaining joins and sort keys.** Twelve bugs of the same shape
  now. Every column whose name asserts a semantic (`*_time`, `*_date`,
  `week`, `season`) deserves an explicit check that it holds what the name
  claims -- as does every "last season" that might be in progress, every value
  that might have a *type* other than the one the code assumes, and every
  price that might not be pre-game.
- The two sports fail for *different* reasons: NFL is under-dispersed
  (model sd 0.132 vs market 0.187); EPL's dispersion is already fine.
- ~~Kalshi liquidity filter~~ -- **done** (`betting/liquidity.py`).
  ~~The 5% relative-width gate remains unvalidated against realized fill
  quality~~ -- **partly closed in run 14** (`cli fill-quality`). Realized fill
  quality is not observable here and will not be while `live_enabled` is
  false; what is observable is quote persistence, and on that test the gate
  separates cleanly on NFL (**+10.7pp** more likely to move a tick against
  you, CI [+6.4, +16.4]; the width rule alone **+18.1pp**, CI [+7.6, +32.3])
  and not at all on EPL (**+1.6pp**, CI [-0.4, +5.6]). **Nothing was changed
  on the strength of it.** The EPL null is an argument for looking at that
  league's thresholds, not for loosening them: this instrument says what a
  quote *does*, not what a looser gate would do to ROI, and that is a
  backtest. `PRICING_VERSION` is frozen until 09-21 in any case.
- **Needs the owner: nothing.** No charge and no signup form is outstanding.
  Both previously-listed items are closed on the merits (see the rejected-
  sources table above) and should not be re-raised. When a source is needed,
  the run finds one: ESPN was added in run 8 to unblock three items that had
  been waiting on someone else's publication schedule for three runs.

**The venue-agreement join fanned out across seasons -- caught in the run that
introduced it.** The first version matched the Kalshi board to the stats table
on `(home_team, away_team)`. That pair is not unique: the same fixture recurs
every season, so **30 events became 131 rows**, comparing today's contracts
against games from 2020, 2021 and 2024. It reported corr **0.4572** with a
53-point maximum disagreement, and was nearly written up as "the two venues
disagree substantially". Disambiguated by kickoff it is 28 rows at corr
**0.9955**. Fifth bug of this shape; the only reason it was caught is that the
wrong answer happened to look surprising. Pinned by
`test_agreement_join_is_kickoff_disambiguated`.
