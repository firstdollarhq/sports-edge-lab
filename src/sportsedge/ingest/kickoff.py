"""Resolve a contract's TRUE kickoff time from the stats sources.

Why this module exists
----------------------
Kalshi's market payload contains no kickoff field. `expected_expiration_time`
and `occurrence_datetime` are identical to each other and both land *after*
the game starts -- measured across all 31 NFL events on the 2026-09-10 board,
27 were +3h and 4 were +6h, and none were +0h. The snapshot schema originally
stored that value in a column called `commence_time`, and two consumers then
treated it as kickoff:

  * `ingest.kalshi.closing_quote_before()` cut its candlestick search there,
  * `betting.settle._closing_odds()` cut its snapshot search there.

Both therefore accepted prices from *inside* the game. For SF @ LA on
2026-09-10 the candlestick path returned bid 0.98 / ask 0.99 -- a price from
after the result was decided -- against an entry of 0.36. That is a CLV of
roughly +175% manufactured entirely by the clock, and CLV is the metric this
project designated as its better short-run skill signal. Contaminated, it
becomes a near-deterministic function of the result: the model looks like it
has enormous closing-line skill precisely when it wins.

Same class of bug as the `week`-as-string ordering error: a mislabelled field,
quiet, with aggregates that still look plausible.

The rule this module enforces
-----------------------------
Kickoff comes from the stats source or it does not come at all. nflverse
publishes `gameday` + `gametime` for future games; football-data.co.uk
publishes `Date` + `Time` for completed ones. CLV is only ever computed at
settlement, by which point both sources have the match, so there is no window
where a guess is needed -- and callers that cannot resolve a kickoff must
report no CLV rather than fall back to the expiration timestamp.

No CLV is a missing number. Fake CLV is a wrong conclusion.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd

from sportsedge.storage import snapshots

# sport -> committed processed table holding that sport's schedule
_TABLE = {"nfl": "nfl_games", "soccer": "epl_games"}

# A Kalshi expiration is 3-6h after kickoff for NFL and ~3h for EPL, and the
# ticker's date code can sit a day off the stats source's local match date for
# late kickoffs. Two days each way comfortably covers both without being loose
# enough to collide with a rematch -- league schedules never repeat a fixture
# inside a week.
_MATCH_TOLERANCE = timedelta(days=2)

_cache: dict[str, pd.DataFrame] = {}


class KickoffUnavailable(Exception):
    """The stats source has no usable kickoff for this contract."""


def _schedule(sport: str) -> pd.DataFrame:
    if sport not in _TABLE:
        raise ValueError(f"Unsupported sport: {sport!r}")
    if sport not in _cache:
        df = snapshots.read_processed(_TABLE[sport])
        if "kickoff_utc" not in df.columns:
            df = df.assign(kickoff_utc=None)
        df = df.assign(_kick=pd.to_datetime(df["kickoff_utc"], errors="coerce", utc=True))
        _cache[sport] = df
    return _cache[sport]


def clear_cache() -> None:
    """Drop the memoised schedules (call after a re-ingest)."""
    _cache.clear()


def resolve_kickoff(sport: str, home_team: str, away_team: str,
                    near: str | datetime | None = None) -> datetime | None:
    """True kickoff (tz-aware UTC) for this fixture, or None if unknown.

    `near` is any timestamp known to be close to the game -- in practice
    Kalshi's expiration, which is a few hours late but never days off. It
    disambiguates the home-and-away pair across a season.

    Returns None rather than raising so callers can degrade to "no CLV"; use
    `require_kickoff` when the absence is itself an error worth surfacing.
    """
    try:
        sched = _schedule(sport)
    except (FileNotFoundError, ValueError):
        return None

    hit = sched[(sched["home_team"] == home_team) & (sched["away_team"] == away_team)]
    hit = hit[hit["_kick"].notna()]
    if hit.empty:
        return None

    if near is None:
        # Unambiguous only if the pairing occurs once in the whole table.
        return hit["_kick"].iloc[0].to_pydatetime() if len(hit) == 1 else None

    anchor = pd.to_datetime(near, utc=True, errors="coerce")
    if pd.isna(anchor):
        return None

    gap = (hit["_kick"] - anchor).abs()
    best = gap.idxmin()
    if gap.loc[best] > _MATCH_TOLERANCE:
        return None
    return hit.loc[best, "_kick"].to_pydatetime()


def require_kickoff(sport: str, home_team: str, away_team: str,
                    near: str | datetime | None = None) -> datetime:
    ko = resolve_kickoff(sport, home_team, away_team, near)
    if ko is None:
        raise KickoffUnavailable(
            f"no kickoff for {away_team} @ {home_team} ({sport}) near {near!r}")
    return ko


def expiration_lag(sport: str, home_team: str, away_team: str,
                   expiration: str | datetime) -> timedelta | None:
    """How far Kalshi's expiration sits after the real kickoff.

    Exposed so the offset stays measured rather than assumed: a regression
    test asserts it is strictly positive, which is what makes the expiration
    unusable as a pre-game cutoff.
    """
    ko = resolve_kickoff(sport, home_team, away_team, expiration)
    if ko is None:
        return None
    exp = pd.to_datetime(expiration, utc=True, errors="coerce")
    if pd.isna(exp):
        return None
    return exp.to_pydatetime() - ko


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
