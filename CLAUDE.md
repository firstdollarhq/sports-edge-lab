# Repo workflow notes

## Standing instruction: act autonomously, escalate only money and accounts

Set by the repo owner on 2026-09-10. This applies to every session, including
scheduled/automated runs:

> Make all possible decisions yourself and troubleshoot everything. Only bubble
> up to me when it involves **money** (e.g. purchasing an API subscription) or
> **setting up an account** that you are unable to create.

Concretely, in this repo that means:

- **Do:** diagnose and fix failures, build the missing plumbing, change model
  parameters, add/repair tests, refactor, update docs, and run the full
  ingest → snapshot → recommend → settle loop without asking first.
- **Do:** backtest any proposed model change and adopt or reject it on the
  evidence. Rejecting is a decision too -- make it and record it.
- **Escalate only:** an actual charge on a card, or an actual signup form a
  human must complete. Nothing else.
- **Never escalate:** "should I fix this bug", "should I write a test",
  "which parameter should I try", "which data sources", "how often should this
  run", "should I add this workflow". Decide, do it, and write down why.
- **Stop re-escalating settled questions.** The Odds API was rejected on the
  merits in run 2 (Kalshi covers live *and* historical for free) and
  football-data.org's key turned out to be unnecessary (football-data.co.uk
  already ships kickoff times in a column the ingest was discarding). Neither
  is an open question. Carrying a dead escalation forward from run to run is
  its own kind of dishonesty about the project's state.

**Sharpened by the owner, 2026-09-13, in these words:**

> I keep telling you to find your own data sources. [...] **I am not a
> decision maker in this.**

Run 7's summary had violated this twice in one message: it listed snapshot
cadence as "Needs you" and carried the `[which data sources?]` placeholder
forward as an open item. Both were mine to settle, and both are now settled
below. **The owner is not a fallback for a decision that is merely hard or
merely has a cost.** If a run finds itself writing "needs the owner" about
anything other than a payment or a signup, that is the signal to go and solve
it instead: the snapshot-cadence problem looked like an account-level schedule
nobody in a session could change, and the actual fix was a GitHub Actions cron
that took twenty minutes to write.

The one thing that is NOT a free decision: flipping `live_enabled` to `true`
in `config/leagues.yaml`. See the deployment gate below.

## The deployment gate

A league's model only goes live when it beats the **de-vigged closing line**
out-of-sample in backtest -- not when it merely improves on a previous version
of itself. Until then the recommender still runs, but every row it writes is a
`shadow` bet: recorded as evidence, excluded from headline win rate and ROI.

This is the whole point of the project. A model that loses to the market and
gets deployed anyway just launders a bias into a bet history.

## Data sources -- SETTLED, do not ask again

The stored scheduled prompt contains a literal `[which data sources?]`
placeholder that was never filled in. **It is not a question. It is a
template the owner never edited, and the owner has said plainly (2026-09-13)
that they are not the decision maker here.** The sources below were chosen in
this repo, on the evidence, and they are the answer. A run that re-raises
"which data sources?" is re-asking a question that has been answered three
times.

| Purpose | Source | Why |
|---|---|---|
| NFL schedules, scores, closing lines | nflverse (`nfl_data_py`) | Free, no key. Ships actual closing moneyline/spread/total per game |
| EPL results + closing odds | football-data.co.uk CSVs | Free, no key. Bookmaker-average columns; also ships kickoff times |
| Live market odds, both leagues | Kalshi public REST API | Free, no key, read-only. Contract price *is* the implied probability |

**Rejected, on the merits, and closed:**

- **The Odds API** (~$29/mo Professional for NFL+soccer) -- rejected run 2.
  Kalshi covers live odds for both leagues free, and the venue-agreement work
  in run 5 showed the two price the same games the same way (corr 0.9955 over
  28 games). Paying for a second view of a number we already have is not worth
  $29/mo to a project with no validated edge. **Not an open ask. Do not list
  it as one.**
- **football-data.org** (free tier, needs a human-created key) -- rejected run
  3, as *unnecessary*, not as blocked. The only thing it was wanted for was
  kickoff times, and football-data.co.uk already ships them in a column the
  ingest was discarding.

**If a new source is needed, find one and wire it up.** The bar is: free, no
human-created account, and verified against something we already hold before
any number derived from it is published. Only an actual charge or an actual
signup form that a human must complete is worth surfacing -- and surface it as
a finding, not as a question blocking the run.

## Scheduled runs write (set by the owner, 2026-09-11)

Earlier scheduled prompts carried a "do not post, send, change, or delete
anything" line, which made review runs read-only and meant they captured no
odds. The owner has lifted it: **scheduled runs capture, commit and settle**,
and snapshot cadence can be as high as needed.

If a stored prompt still contains that read-only line, this note overrides it
for repository work. **Note it once in the journal entry and move on** -- it
does not need a paragraph in every run's summary. The override has been
settled since 2026-09-11; repeating it at the owner each run is the same noise
as re-escalating a closed question.

## Odds snapshots are irreplaceable -- capture them

`data/snapshots/` is deliberately **not** gitignored. Live odds cannot be
reconstructed after the fact and the container is wiped between runs, so the
committed CSVs are the only durable record. Closing-line value depends entirely
on having captured a pre-kickoff price, so `snapshot-odds` should run more
often than the games close. A missed window is permanently missing data.

## Run cadence -- SETTLED, do not ask again

Decided 2026-09-13 after the owner declined to be the decision maker. Two jobs
at two very different rates, because they have very different costs:

| Job | Cadence | Where |
|---|---|---|
| **Capture** (`snapshot-odds`) | **every 30 min**, 10:00-04:00 UTC | `.github/workflows/snapshot-odds.yml` |
| **Review** (settle, backtest, journal) | **once daily**, ~06:00 UTC | the stored Claude schedule, unchanged |

**Why capture does not belong in a Claude session.** `snapshot-odds` needs no
key, no model and no game tables -- it is one unauthenticated GET against a
public REST API. Spending a review session on it bought exactly one capture
per day against slates that start at 11:00Z, which is how `closing_odds_decimal`
came to hold a T-8h to T-11h price and why run 7 had to record that the column
has never held a closing price. A GitHub Actions cron does the same job ~38
times a day for free and needs nobody to be awake.

This was sitting behind a wrong assumption for a full run: cadence looked like
an account-level schedule that no session could change, so run 7 wrote it down
as "needs the owner". It was never a schedule problem.

**The Action captures and commits. It does not price.** No `recommend`, no
`settle`, nothing that touches `bets/ledger.csv`. Capture is append-only and
safe to run unattended; a bet written by a job nobody is reading is how the
record gets quietly corrupted. Pricing stays in a session that writes a
journal entry explaining itself.

Two things that will eventually bite, written down now rather than
rediscovered:

- GitHub delays scheduled workflows under load and occasionally drops one.
  `*/30` means "about every 30-45 minutes". That is fine -- it moves
  worst-case staleness from ~11h to ~1h -- but it is not a guarantee, and a
  gap in `data/snapshots/` is a dropped run, not a bug.
- GitHub disables scheduled workflows on a repo with 60 days of no activity.
  This repo commits daily, so it will not trigger; if capture ever goes
  silent, check that first.

**Cadence stays at `*/30` -- ASKED AND ANSWERED, run 13 (2026-09-16).**
The standing instruction here was to measure the final hour once captures
existed inside it and go to `*/15` if the line moved a lot. The captures now
exist -- NFL closing quotes at a median of T-0.42h, EPL at T-0.12h at best --
and the line does not move:

| bucket | NFL mean abs move | EPL mean abs move | share moving >= 0.02 |
|---|---|---|---|
| T-1h..T-2h | 0.0036 | 0.0050 | 0% both |
| T-2h..T-4h | 0.0036 | 0.0067 | 0% both |

Over the *entire* pre-kickoff window (median first capture T-74h, 29 captures
per NFL contract) the mean absolute net move is **0.0157** for NFL and
**0.0107** for EPL, and **30% of NFL contracts never moved a single tick**.
The venue quotes whole cents, so the final two hours are moving less than the
smallest change the venue can express. `*/15` would resolve movement that is
not there. **Do not raise it without a new reason; a thicker book or a second
venue would be one, "we have not tried it" is not.**

The same measurement retires a metric -- see run 13's journal entry. CLV at
this venue is quantisation noise at current sample sizes, and
`ledger-summary` now prints `clv_resolution` next to the CLV mean so that is
visible without re-deriving it. **Do not quote a CLV mean without the tick
value beside it.**

## Branch hygiene

Every Claude Code on the web session (including scheduled/automated runs)
works on its own freshly generated `claude/<slug>` branch — this is assigned
by the platform per session and can't be changed from within a session.

To avoid branch sprawl, **before ending a session that made commits on such a
branch, merge that branch into the repository's default branch** (currently
`claude/compassionate-shannon-rc4owt` — treat it as `main`; rename it to
`main` if/when convenient) and leave the work there. Don't leave finished
work sitting only on a throwaway per-session branch.
