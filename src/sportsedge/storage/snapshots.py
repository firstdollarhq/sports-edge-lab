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
    "home_team", "away_team", "expiration_time", "selection",
    "yes_bid", "yes_ask", "implied_prob_mid", "spread",
    "yes_bid_size", "yes_ask_size", "volume", "volume_24h", "open_interest",
    "status", "source", "fetched_at",
]

# One row per contract per fetch; re-running within a minute shouldn't create
# near-duplicate rows, so we dedupe on the contract + the minute it was taken.
_DEDUPE_KEY = ["market_ticker", "source", "fetched_minute"]


def _path_for(sport: str, day: str) -> Path:
    return SNAPSHOT_ROOT / sport / f"{day}.csv"


# _read_float_note
# ----------------
# Every read of a committed CSV passes float_precision="round_trip".
#
# pandas' default CSV float parser is fast but NOT correctly rounded: it reads
# the stored "1.3690036900369003" back as 1.3690036900369005. So the committed
# tables did not survive a read/write cycle -- 585 of 2,499 NFL rows drifted in
# the last bit on every refresh, forever, with no upstream change behind it.
#
# The numbers do not matter at 1e-16. Two things that follow from them do:
#
#   1. It made `git diff` useless on the data. The 2026-09-11 run found 12
#      genuinely revised odds cells only by scripting a column comparison,
#      because the diff reported every row as changed. Review here IS reading
#      diffs, so noise at that volume is the same as no review.
#   2. `data/snapshots/` is the project's one irreplaceable asset, and it was
#      being silently altered by the act of reading it.
#
# Neither is a modelling bug and neither changes a published number. Both are
# the same failure the journal keeps recording: a value that was not what the
# code assumed it was.


def _read_csv(path) -> pd.DataFrame:
    """Read a snapshot CSV, normalising the pre-2026-09-11 column name.

    Snapshots written before then stored Kalshi's `expected_expiration_time`
    in a column called `commence_time`, which is 3-6h after kickoff and was
    never a commencement of anything. The files are the project's one
    irreplaceable asset so they are not rewritten; the name is corrected on
    the way in instead.
    """
    df = pd.read_csv(path, float_precision="round_trip")  # see _read_float_note
    if "commence_time" in df.columns and "expiration_time" not in df.columns:
        df = df.rename(columns={"commence_time": "expiration_time"})
    return df


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

    combined = pd.concat([_read_csv(path), new], ignore_index=True) if path.exists() else new

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
    frames = [_read_csv(f) for root in roots if root.exists() for f in sorted(root.glob("*.csv"))]
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


# `ingested_at` records when a row was fetched, not anything about the game, so
# it is excluded when deciding whether a row actually moved.
_RESTAMPED_COLUMNS = ("ingested_at",)

# Belt and braces on top of the round_trip reader above: rows are compared at a
# precision a price can actually carry, so a last-bit wobble from any source
# cannot register as a line move. 17 significant digits on a moneyline is false
# precision either way.
_FLOAT_SIGFIGS = 10


def _fingerprint(df: pd.DataFrame, cols: list[str]) -> pd.Series:
    """Canonical per-row string over `cols`, stable across a CSV round-trip.

    Floats are compared at `_FLOAT_SIGFIGS` significant digits, and missing
    values get an explicit sentinel -- pandas' string dtype carries NA through
    `astype(str)` unchanged, so joining without this raises rather than
    compares, and an unplayed fixture is mostly missing values.
    """
    def canon(s: pd.Series) -> pd.Series:
        numeric = pd.to_numeric(s, errors="coerce")
        # Treat a column as numeric only if coercion lost nothing.
        if numeric.notna().equals(s.notna()) and s.notna().any():
            return numeric.map(lambda x: "" if pd.isna(x) else f"{x:.{_FLOAT_SIGFIGS}g}")
        return s.astype(str).fillna("")

    return pd.DataFrame({c: canon(df[c]) for c in cols}).agg("\x1f".join, axis=1)


def _keep_unchanged_rows(old: pd.DataFrame, combined: pd.DataFrame) -> pd.DataFrame:
    """Take the stored row verbatim wherever the refreshed row says the same thing.

    Without this every refresh rewrites every row -- a new `ingested_at` on all
    of them, plus 1-ULP churn in the re-derived odds -- which buries the handful
    that genuinely moved under thousands that did not. This repo's review
    mechanism is reading diffs, so a diff that is almost entirely noise is a
    diff nobody can read: the 2026-09-11 run found 12 revised NFL odds/total
    cells only by scripting a column-by-column comparison, because `git diff`
    reported all 2,499 rows as changed.

    Only rows that say the same thing are held back. A row whose substance
    moved -- a line revision, a corrected score, a fixture gaining a result --
    is written fresh and shows up in the diff, which is the point.
    """
    if "game_id" not in old.columns or "game_id" not in combined.columns:
        return combined

    data_cols = [c for c in combined.columns
                 if c not in _RESTAMPED_COLUMNS and c in old.columns]
    if not data_cols:
        return combined

    old = old.drop_duplicates(subset=["game_id"], keep="last")
    old_fp = pd.Series(_fingerprint(old, data_cols).values, index=old["game_id"].values)

    prior = combined["game_id"].map(old_fp)
    unchanged = prior.notna() & (prior.values == _fingerprint(combined, data_cols).values)
    if not unchanged.any():
        return combined

    stored = old.set_index("game_id").reindex(combined.loc[unchanged, "game_id"])
    for col in combined.columns:
        if col in stored.columns:
            combined.loc[unchanged, col] = stored[col].values
    return combined


def write_processed(name: str, df: pd.DataFrame) -> tuple[Path, int]:
    """Write a historical game table, merging with whatever is already there.

    Keyed on game_id so re-ingesting an in-progress season fills in scores for
    fixtures that were unplayed last time without duplicating the rows.
    """
    path = processed_path(name)
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.exists():
        old = pd.read_csv(path, float_precision="round_trip")
        combined = pd.concat([old, df], ignore_index=True)
        combined = combined.drop_duplicates(subset=["game_id"], keep="last")
        combined = _keep_unchanged_rows(old, combined)
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
    return pd.read_csv(path, float_precision="round_trip")
