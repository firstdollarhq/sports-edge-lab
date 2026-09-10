"""Team identity resolution between Kalshi tickers and our stats sources.

Kalshi encodes both teams in the *event* ticker and the single team a market
refers to in the *market* ticker's suffix:

    event  KXNFLGAME-26SEP21NYGLAR
    market KXNFLGAME-26SEP21NYGLAR-NYG   -> this market is "NYG wins"

The suffix is authoritative, so we never have to fuzzy-match the printed team
name ("New York G") to a stats-source name.

**Ticker team order differs by sport, and it is not guessable** -- both were
verified empirically against the stats sources before being encoded here:

- NFL  ticker is AWAY + HOME  (KXNFLGAME-26SEP21NYGLAR = NYG at LA)
  checked against nflverse home/away for all 15 games of 2026 week 2.
- EPL  ticker is HOME + AWAY  (KXEPLGAME-26SEP06ARSCFC = Arsenal hosting Chelsea)
  checked against football-data.co.uk for the 2026-09-05/06 fixtures.

Getting this backwards silently inverts every prediction, so
`tests/test_teams.py` pins both orders.
"""
from __future__ import annotations

import re

# --- NFL: Kalshi code -> nflverse abbreviation ------------------------------
# nflverse uses LA (not LAR) and JAX (not JAC); everything else is identical.
NFL_KALSHI_TO_NFLVERSE = {
    "LAR": "LA",
    "JAC": "JAX",
}

NFLVERSE_TEAMS = {
    "ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE", "DAL", "DEN",
    "DET", "GB", "HOU", "IND", "JAX", "KC", "LA", "LAC", "LV", "MIA",
    "MIN", "NE", "NO", "NYG", "NYJ", "PHI", "PIT", "SEA", "SF", "TB",
    "TEN", "WAS",
}

# --- EPL: Kalshi code -> football-data.co.uk team name ----------------------
# football-data uses short forms ("Man United", "Nott'm Forest"), so this map
# is written against the names actually present in the E0 CSVs.
EPL_KALSHI_TO_FOOTBALL_DATA = {
    "ARS": "Arsenal",
    "AVL": "Aston Villa",
    "BOU": "Bournemouth",
    "BRE": "Brentford",
    "BRI": "Brighton",
    "CFC": "Chelsea",
    "COV": "Coventry",
    "CRY": "Crystal Palace",
    "EVE": "Everton",
    "FUL": "Fulham",
    "HUL": "Hull",
    "IPS": "Ipswich",
    "LEE": "Leeds",
    "LFC": "Liverpool",
    "MCI": "Man City",
    "MUN": "Man United",
    "NEW": "Newcastle",
    "NFO": "Nott'm Forest",
    "SUN": "Sunderland",
    "TOT": "Tottenham",
}

# Kalshi's 3-way soccer markets carry a literal draw contract.
DRAW_CODE = "TIE"

# KXNFLGAME-26SEP21NYGLAR -> date part '26SEP21', teams part 'NYGLAR'
_EVENT_RE = re.compile(r"^KX(?:NFL|EPL)GAME-(\d{2}[A-Z]{3}\d{2})([A-Z]+)$")


class TeamResolutionError(ValueError):
    """Raised when a Kalshi ticker cannot be mapped to known teams.

    Deliberately loud rather than silently skipped: an unresolved ticker means
    either a new team (promotion/relocation) or a Kalshi format change, and
    both need a human look before we price anything off that market.
    """


def resolve_nfl_team(code: str) -> str:
    """Kalshi NFL code -> nflverse abbreviation."""
    team = NFL_KALSHI_TO_NFLVERSE.get(code, code)
    if team not in NFLVERSE_TEAMS:
        raise TeamResolutionError(f"Unknown NFL team code from Kalshi: {code!r}")
    return team


def resolve_epl_team(code: str) -> str:
    """Kalshi EPL code -> football-data.co.uk team name."""
    try:
        return EPL_KALSHI_TO_FOOTBALL_DATA[code]
    except KeyError:
        raise TeamResolutionError(
            f"Unknown EPL team code from Kalshi: {code!r} "
            "(newly promoted club? add it to EPL_KALSHI_TO_FOOTBALL_DATA)"
        ) from None


def _split_team_codes(blob: str, valid: set[str]) -> tuple[str, str]:
    """Split a concatenated two-team blob ('NYGLAR') into its parts.

    Codes are 2-3 chars and not self-delimiting, so we try every split point
    and require exactly one that leaves two recognised codes. Ambiguity is an
    error rather than a guess.
    """
    candidates = [
        (blob[:i], blob[i:])
        for i in (2, 3)
        if blob[:i] in valid and blob[i:] in valid
    ]
    if len(candidates) != 1:
        raise TeamResolutionError(
            f"Cannot unambiguously split team codes from {blob!r} "
            f"(found {len(candidates)} valid splits)"
        )
    return candidates[0]


def parse_event_ticker(event_ticker: str, sport: str) -> dict:
    """Parse a Kalshi event ticker into home/away teams in stats-source naming.

    Returns {'home_team', 'away_team', 'home_code', 'away_code', 'date_code'}.
    """
    m = _EVENT_RE.match(event_ticker)
    if not m:
        raise TeamResolutionError(f"Unrecognised Kalshi event ticker: {event_ticker!r}")
    date_code, blob = m.group(1), m.group(2)

    if sport == "nfl":
        valid = set(NFL_KALSHI_TO_NFLVERSE) | NFLVERSE_TEAMS
        first, second = _split_team_codes(blob, valid)
        # NFL ticker order is AWAY + HOME (verified against nflverse).
        away_code, home_code = first, second
        return {
            "home_team": resolve_nfl_team(home_code),
            "away_team": resolve_nfl_team(away_code),
            "home_code": home_code,
            "away_code": away_code,
            "date_code": date_code,
        }

    if sport == "soccer":
        valid = set(EPL_KALSHI_TO_FOOTBALL_DATA)
        first, second = _split_team_codes(blob, valid)
        # EPL ticker order is HOME + AWAY (verified against football-data.co.uk).
        home_code, away_code = first, second
        return {
            "home_team": resolve_epl_team(home_code),
            "away_team": resolve_epl_team(away_code),
            "home_code": home_code,
            "away_code": away_code,
            "date_code": date_code,
        }

    raise TeamResolutionError(f"Unsupported sport for ticker parsing: {sport!r}")


def market_team_code(ticker: str, event_ticker: str) -> str:
    """Extract the team code a single market refers to, from its ticker suffix."""
    if not ticker.startswith(event_ticker + "-"):
        raise TeamResolutionError(
            f"Market ticker {ticker!r} does not extend event ticker {event_ticker!r}"
        )
    return ticker[len(event_ticker) + 1:]


def selection_for(ticker: str, event_ticker: str, sport: str) -> str:
    """Map a Kalshi market to 'home' | 'away' | 'draw' for this event."""
    code = market_team_code(ticker, event_ticker)
    if sport == "soccer" and code == DRAW_CODE:
        return "draw"
    teams = parse_event_ticker(event_ticker, sport)
    if code == teams["home_code"]:
        return "home"
    if code == teams["away_code"]:
        return "away"
    raise TeamResolutionError(
        f"Market {ticker!r} refers to {code!r}, which is neither side of {event_ticker!r}"
    )
