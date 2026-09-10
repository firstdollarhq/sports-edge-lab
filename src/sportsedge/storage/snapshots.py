"""Durable, version-controlled odds snapshot store.

Why this exists: `data/*.db` is gitignored and every scheduled run gets a fresh
container, so anything written only to SQLite is gone the moment the run ends.
Odds are not reconstructable after the fact -- you cannot go back and ask what
Kalshi was quoting last Tuesday. Without a durable capture, closing-line value
can never be computed, which would gut the project's single best short-run
skill signal.

So snapshots are appended to committed CSVs, partitioned by UTC date:

    data/snapshots/<sport>/<YYYY-MM-DD>.csv

CSV rather than SQLite specifically because it diffs in git, which makes the
odds history auditable alongside the code that acted on it.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

SNAPSHOT_ROOT = Path(__file__).parents[3] / "data" / "snapshots"

COLUMNS = [
    "sport", "league", "event_ticker", "market_ticker", "game_id",
    "home_team", "away_team", "commence_time", "selection",
    "yes_bid", "yes_ask", "implied_prob_mid", "spread",
    "yes_bid_size", "yes_ask_size", "volume", "volume_24h", "open_interest",
    "status", "source", "fetched_at",
]

# One row per contract per fetch; re-running within a minute shouldn't create
# near-duplicate rows, so we dedupe on the contract + the minute it was taken.
_DEDUPE_KEY = ["market_ticker", "source", "fetched_minute"]


def _path_for(sport: str, day: str) -> Path:
    return SNAPSHOT_ROOT / sport / f"{day}.csv"


def append_snapshot(rows: list[dict], *, sport: str, now: datetime | None = None) -> dict:
    """Append snapshot rows to today's CSV for `sport`, de-duplicating.

    Returns {'written', 'skipped', 'path'}.
    """
    if not rows:
        return {"written": 0, "skipped": 0, "path": None}

    now = now or datetime.now(timezone.utc)
    day = now.strftime("%Y-%m-%d")
    path = _path_for(sport, day)
    path.parent.mkdir(parents=True, exist_ok=True)

    new = pd.DataFrame(rows)
    for col in COLUMNS:
        if col not in new.columns:
            new[col] = None
    new = new[COLUMNS]

    combined = pd.concat([pd.read_csv(path), new], ignore_index=True) if path.exists() else new

    combined["fetched_minute"] = combined["fetched_at"].astype(str).str.slice(0, 16)
    before = len(combined)
    combined = combined.drop_duplicates(subset=_DEDUPE_KEY, keep="last")
    combined = combined.drop(columns=["fetched_minute"])

    existing = before - len(new)
    written = len(combined) - existing
    combined.sort_values(["fetched_at", "event_ticker", "selection"]).to_csv(path, index=False)
    return {"written": max(0, written), "skipped": len(new) - max(0, written), "path": str(path)}


def load_snapshots(sport: str | None = None) -> pd.DataFrame:
    """Load the full committed snapshot history (optionally for one sport)."""
    roots = [SNAPSHOT_ROOT / sport] if sport else (
        [p for p in SNAPSHOT_ROOT.iterdir() if p.is_dir()] if SNAPSHOT_ROOT.exists() else []
    )
    frames = [pd.read_csv(f) for root in roots if root.exists() for f in sorted(root.glob("*.csv"))]
    if not frames:
        return pd.DataFrame(columns=COLUMNS)
    return pd.concat(frames, ignore_index=True)


def latest_before(sport: str, market_ticker: str, cutoff: str) -> dict | None:
    """The last quote we captured for a contract before `cutoff` (ISO 8601).

    This is how closing odds are derived for CLV: the final price we observed
    before kickoff. It is only as good as our snapshot cadence, which is why
    the snapshot job should run more often than once a day.
    """
    df = load_snapshots(sport)
    if df.empty:
        return None
    sub = df[(df["market_ticker"] == market_ticker) & (df["fetched_at"].astype(str) < cutoff)]
    if sub.empty:
        return None
    return sub.sort_values("fetched_at").iloc[-1].to_dict()


# -- historical game tables ---------------------------------------------------
#
# Same durability argument as the odds snapshots above, weaker force: game
# tables CAN be rebuilt from nflverse and football-data.co.uk, so losing them
# costs time rather than information. They are committed anyway because a
# backtest that silently re-downloads its own inputs on every run is a
# backtest whose sample can change underneath a result you already published.

PROCESSED_DIR = Path(__file__).parents[3] / "data" / "processed"


def processed_path(name: str) -> Path:
    return PROCESSED_DIR / f"{name}.csv"


def write_processed(name: str, df: pd.DataFrame) -> tuple[Path, int]:
    """Write a historical game table, merging with whatever is already there.

    Keyed on game_id so re-ingesting an in-progress season fills in scores for
    fixtures that were unplayed last time without duplicating the rows.
    """
    path = processed_path(name)
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.exists():
        combined = pd.concat([pd.read_csv(path), df], ignore_index=True)
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
