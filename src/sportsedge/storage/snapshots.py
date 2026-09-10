"""Durable, git-committed odds snapshots and historical game tables.

WHY CSV IN GIT RATHER THAN THE SQLITE DB
----------------------------------------
Each scheduled run gets a fresh, ephemeral container. `data/sportsedge.db` is
gitignored, so it does not survive between runs -- every run was starting from
zero local history.

That is survivable for the historical game tables, which can be rebuilt on
demand from free sources. It is NOT survivable for live odds: closing line
value cannot be reconstructed retroactively. A Kalshi quote that was not
recorded before kickoff is gone permanently, and CLV is the best short-run
signal of model skill we have. Every unrecorded day is data lost for good.

So: the durable record is plain CSV committed to git (small, diffable,
reviewable, survives the container), and SQLite is demoted to a derived cache
rebuilt from those CSVs whenever it is needed.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

DATA_ROOT = Path(__file__).parents[3] / "data"
SNAPSHOT_DIR = DATA_ROOT / "snapshots"
PROCESSED_DIR = DATA_ROOT / "processed"

SNAPSHOT_COLUMNS = [
    "sport", "league", "event_ticker", "market_ticker", "game_id", "home_team",
    "away_team", "commence_time", "selection", "yes_bid", "yes_ask",
    "implied_prob_mid", "executable_prob_yes", "spread_cost_frac", "volume",
    "volume_24h", "open_interest", "yes_bid_size", "yes_ask_size", "status",
    "source", "fetched_at",
]


def snapshot_path(day: str | None = None) -> Path:
    day = day or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return SNAPSHOT_DIR / "kalshi" / f"{day}.csv"


def write_snapshot(rows: list[dict], day: str | None = None) -> tuple[Path, int]:
    """Append rows to today's snapshot file, de-duplicated on (market, fetched_at).

    Appending rather than overwriting means running twice in a day gives two
    observations of the book, which is strictly more information -- price
    movement through the day is itself a signal.
    """
    if not rows:
        return snapshot_path(day), 0

    path = snapshot_path(day)
    path.parent.mkdir(parents=True, exist_ok=True)

    new = pd.DataFrame(rows)
    for col in SNAPSHOT_COLUMNS:
        if col not in new.columns:
            new[col] = None
    new = new[SNAPSHOT_COLUMNS]

    if path.exists():
        existing = pd.read_csv(path)
        combined = pd.concat([existing, new], ignore_index=True)
    else:
        combined = new

    combined = combined.drop_duplicates(subset=["market_ticker", "fetched_at"], keep="last")
    combined = combined.sort_values(["fetched_at", "event_ticker", "selection"])
    combined.to_csv(path, index=False)
    return path, len(new)


def load_snapshots(sport: str | None = None) -> pd.DataFrame:
    """Every snapshot ever recorded, concatenated. This is the CLV substrate."""
    files = sorted((SNAPSHOT_DIR / "kalshi").glob("*.csv"))
    if not files:
        return pd.DataFrame(columns=SNAPSHOT_COLUMNS)
    df = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
    if sport:
        df = df[df["sport"] == sport]
    return df


# -- historical game tables ---------------------------------------------------

def processed_path(name: str) -> Path:
    return PROCESSED_DIR / f"{name}.csv"


def write_processed(name: str, df: pd.DataFrame) -> tuple[Path, int]:
    """Write a historical game table, merging with whatever is already there.

    Keyed on game_id so re-ingesting an in-progress season fills in scores for
    games that were unplayed last time without duplicating rows.
    """
    path = processed_path(name)
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.exists():
        existing = pd.read_csv(path)
        combined = pd.concat([existing, df], ignore_index=True)
        combined = combined.drop_duplicates(subset=["game_id"], keep="last")
    else:
        combined = df

    combined = combined.sort_values(["season", "game_date", "game_id"])
    combined.to_csv(path, index=False)
    return path, len(combined)


def read_processed(name: str) -> pd.DataFrame:
    path = processed_path(name)
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found -- run `python -m sportsedge.cli refresh-history` first"
        )
    return pd.read_csv(path)
