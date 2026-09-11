"""Free historical soccer results + closing odds via football-data.co.uk CSVs.

League codes (football-data.co.uk convention): E0=EPL, E1=Championship,
D1=Bundesliga, SP1=La Liga, I1=Serie A, F1=Ligue 1, etc.
Season codes are 4-digit, e.g. '2425' for the 2024/25 season.
"""
from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pandas as pd

BASE_URL = "https://www.football-data.co.uk/mmz4281/{season}/{league}.csv"

# football-data.co.uk's `Time` column is a UK wall clock, not UTC.
_FOOTBALL_DATA_TZ = ZoneInfo("Europe/London")

LEAGUE_NAMES = {
    "E0": "EPL",
    "E1": "Championship",
    "D1": "Bundesliga",
    "SP1": "La Liga",
    "I1": "Serie A",
    "F1": "Ligue 1",
}


def fetch_soccer_games(league_code: str, seasons: list[str]) -> pd.DataFrame:
    """seasons: list of 4-digit season codes, e.g. ['2324', '2425']."""
    frames = []
    now = datetime.now(timezone.utc).isoformat()

    for season in seasons:
        url = BASE_URL.format(season=season, league=league_code)
        try:
            raw = pd.read_csv(url)
        except UnicodeDecodeError:
            # Older football-data files carry latin-1 bytes in referee names.
            raw = pd.read_csv(url, encoding="latin-1")
        raw = raw.dropna(subset=["HomeTeam", "AwayTeam", "FTR"])

        home_odds = raw["AvgH"] if "AvgH" in raw.columns else raw.get("B365H")
        draw_odds = raw["AvgD"] if "AvgD" in raw.columns else raw.get("B365D")
        away_odds = raw["AvgA"] if "AvgA" in raw.columns else raw.get("B365A")

        parsed_date = pd.to_datetime(raw["Date"], dayfirst=True)
        game_date = parsed_date.dt.strftime("%Y-%m-%d")
        season_label = f"20{season[:2]}-{season[2:]}"

        # Real kickoff, used as the cutoff for every closing-price lookup.
        # The `Time` column was previously parsed and thrown away, which left
        # the project with no kickoff for soccer at all and forced the CLV
        # path onto Kalshi's expiration timestamp -- 3+ hours after kickoff,
        # i.e. an in-play price. Older seasons predate the column.
        if "Time" in raw.columns:
            naive = pd.to_datetime(
                game_date + " " + raw["Time"].astype(str), errors="coerce")
            kickoff = (naive.dt.tz_localize(_FOOTBALL_DATA_TZ, ambiguous=True,
                                            nonexistent="shift_forward")
                            .dt.tz_convert(timezone.utc)
                            .apply(lambda t: None if pd.isna(t) else t.isoformat()))
        else:
            kickoff = pd.Series([None] * len(raw), index=raw.index)

        # Deterministic ID from (season, date, teams) rather than row index.
        # In-progress seasons get re-ingested repeatedly as results land; an
        # index-based ID silently re-points at a different fixture the moment
        # football-data.co.uk inserts or reorders a row, which would corrupt
        # the merge in storage.snapshots.write_processed().
        game_ids = [
            f"soccer_{league_code}_{season}_{d}_{h}_{a}".replace(" ", "")
            for d, h, a in zip(game_date, raw["HomeTeam"], raw["AwayTeam"])
        ]

        df = pd.DataFrame({
            "game_id": game_ids,
            "sport": "soccer",
            "league": LEAGUE_NAMES.get(league_code, league_code),
            "season": season_label,
            "week": None,
            "game_date": game_date,
            "kickoff_utc": kickoff,
            "home_team": raw["HomeTeam"],
            "away_team": raw["AwayTeam"],
            "home_score": raw["FTHG"],
            "away_score": raw["FTAG"],
            "result": raw["FTR"],
            "home_odds_decimal": home_odds,
            "away_odds_decimal": away_odds,
            "draw_odds_decimal": draw_odds,
            "spread_line": None,
            "total_line": None,
            "source": "football-data.co.uk",
            "ingested_at": now,
        })
        frames.append(df)

    return pd.concat(frames, ignore_index=True)
