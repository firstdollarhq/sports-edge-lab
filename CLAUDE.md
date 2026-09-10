# Repo workflow notes

## Branch hygiene

Every Claude Code on the web session (including scheduled/automated runs)
works on its own freshly generated `claude/<slug>` branch — this is assigned
by the platform per session and can't be changed from within a session.

To avoid branch sprawl, **before ending a session that made commits on such a
branch, merge that branch into the repository's default branch** (currently
`claude/compassionate-shannon-rc4owt` — treat it as `main`; rename it to
`main` if/when convenient) and leave the work there. Don't leave finished
work sitting only on a throwaway per-session branch.
