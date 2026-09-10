"""Free historical soccer results + closing odds via football-data.co.uk CSVs.

League codes (football-data.co.uk convention): E0=EPL, E1=Championship,
D1=Bundesliga, SP1=La Liga, I1=Serie A, F1=Ligue 1, etc.
Season codes are 4-digit, e.g. '2425' for the 2024/25 season.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

BASE_URL = "https://www.football-data.co.uk/mmz4281/{season}/{league}.csv"

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
        raw = pd.read_csv(url)
        raw = raw.dropna(subset=["HomeTeam", "AwayTeam", "FTR"])

        home_odds = raw["AvgH"] if "AvgH" in raw.columns else raw.get("B365H")
        draw_odds = raw["AvgD"] if "AvgD" in raw.columns else raw.get("B365D")
        away_odds = raw["AvgA"] if "AvgA" in raw.columns else raw.get("B365A")

        game_date = pd.to_datetime(raw["Date"], dayfirst=True).dt.strftime("%Y-%m-%d")
        season_label = f"20{season[:2]}-{season[2:]}"

        df = pd.DataFrame({
            "game_id": [
                f"soccer_{league_code}_{season}_{i}" for i in range(len(raw))
            ],
            "sport": "soccer",
            "league": LEAGUE_NAMES.get(league_code, league_code),
            "season": season_label,
            "week": None,
            "game_date": game_date,
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
