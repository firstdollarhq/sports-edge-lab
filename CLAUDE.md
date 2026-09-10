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
- **Escalate only:** paid data sources (The Odds API Professional ~$29/mo is
  the live example), and any source needing an account/API key that has to be
  created by a human (football-data.org's free tier needs a key).
- **Never escalate:** "should I fix this bug", "should I write a test",
  "which parameter should I try". Decide, do it, and write down why.

The one thing that is NOT a free decision: flipping `live_enabled` to `true`
in `config/leagues.yaml`. See the deployment gate below.

## The deployment gate

A league's model only goes live when it beats the **de-vigged closing line**
out-of-sample in backtest -- not when it merely improves on a previous version
of itself. Until then the recommender still runs, but every row it writes is a
`shadow` bet: recorded as evidence, excluded from headline win rate and ROI.

This is the whole point of the project. A model that loses to the market and
gets deployed anyway just launders a bias into a bet history.

## Data sources (the answer to "which data sources?")

The scheduled prompt contains an unfilled `[which data sources?]` placeholder.
Until the owner edits it, use these -- all free, no key required:

| Purpose | Source |
|---|---|
| NFL schedules, scores, closing lines | nflverse (`nfl_data_py`) |
| EPL results + closing odds | football-data.co.uk CSVs |
| Live market odds, both leagues | Kalshi public REST API (read-only) |

Not in use: football-data.org (needs a free API key someone must create),
The Odds API (paid). Both are owner decisions.

## Odds snapshots are irreplaceable -- capture them

`data/snapshots/` is deliberately **not** gitignored. Live odds cannot be
reconstructed after the fact and the container is wiped between runs, so the
committed CSVs are the only durable record. Closing-line value depends entirely
on having captured a pre-kickoff price, so `snapshot-odds` should run more
often than the games close. A missed window is permanently missing data.

## Branch hygiene

Every Claude Code on the web session (including scheduled/automated runs)
works on its own freshly generated `claude/<slug>` branch — this is assigned
by the platform per session and can't be changed from within a session.

To avoid branch sprawl, **before ending a session that made commits on such a
branch, merge that branch into the repository's default branch** (currently
`claude/compassionate-shannon-rc4owt` — treat it as `main`; rename it to
`main` if/when convenient) and leave the work there. Don't leave finished
work sitting only on a throwaway per-session branch.
