"""How much rating history stands behind a price.

Elo hands a team it has never seen `default_rating` and then walks that number
toward the truth one game at a time. In a league with promotion that is not a
neutral prior: a side that has just come up is, on average, well below the
division it is entering, so its first weeks are priced off a rating the book
has no evidence for.

MEASURED, run 20, EPL 2019-20..2025-26. Over the 8 teams making their first
appearance in the table, the model's probability for the debutant side ran
**+0.0447** above the de-vigged market, against a realized 0.2434 -- the
market's 0.2451 was almost exactly right, so the gap is the model's. It is
the signature of the 1500 start and not a coincidence:

    games 0-4   +0.1016      games 10-18  +0.0413
    games 5-9   +0.0738      games 19-37  +0.0237

and all 8 teams were biased the same way (cluster-bootstrap 95% CI over teams
[+0.0253, +0.0634]). The bet rule amplifies it: 62.5% of debutant sides got
flagged against 36.4% of established ones, at a mean claimed edge of +35.8%
against +19.2%.

CORRECTING IT WAS TRIED AND REJECTED. Seeding a promoted side below the book
fixes the bias out-of-sample and buys nothing: pooled over six seasons the
log-loss change was -0.000987 with a season-cluster CI of [-0.0025, +0.0006],
and ROI moved the WRONG way (-8.296% -> -8.918%). See the run 20 journal
entry for the sweep. This module is what survived it -- a counter, so the next
promoted side shows up in a run summary instead of being rediscovered in a
year.

Nothing here gates a bet. It reports.
"""
from __future__ import annotations

import pandas as pd

# Half a season. A reporting line, NOT a tuned parameter and NOT a filter:
# the decay table above is smooth, so any cut here is arbitrary, and this one
# is only picked so "thin" means "the book has seen less of this team than it
# has of anybody else in the division".
THIN_HISTORY_GAMES = 20


def team_game_counts(games: pd.DataFrame) -> dict[str, int]:
    """Games per team in the rating table -- exactly what the Elo book was built from."""
    if games is None or not len(games):
        return {}
    counts = pd.concat([games["home_team"], games["away_team"]]).value_counts()
    return {str(k): int(v) for k, v in counts.items()}


def thin_history(recs: list[dict], games: pd.DataFrame,
                 threshold: int = THIN_HISTORY_GAMES) -> dict:
    """Which recommendations lean on a team the rating book barely knows.

    A price depends on BOTH ratings -- `elo_diff` is a difference -- so a
    fixture counts as thin when either side is thin, whichever way the bet
    went. Teams absent from the table entirely count as 0 games, which is the
    debutant case and the one that matters.
    """
    counts = team_game_counts(games)
    flagged, teams = 0, {}
    for r in recs:
        involved = [t for t in (r.get("home_team"), r.get("away_team")) if t]
        thin = {t: counts.get(t, 0) for t in involved if counts.get(t, 0) < threshold}
        if thin:
            flagged += 1
            teams.update(thin)
    return {
        "threshold_games": threshold,
        "flagged": flagged,
        "flagged_pct": round(100 * flagged / len(recs), 1) if recs else 0.0,
        "teams": dict(sorted(teams.items())),
    }
