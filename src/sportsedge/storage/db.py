"""SQLite storage for games, odds snapshots, predictions, bets, and backtest runs."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

SCHEMA_PATH = Path(__file__).parent / "schema.sql"
DEFAULT_DB_PATH = Path(__file__).parents[3] / "data" / "sportsedge.db"


def init_db(db_path: Path = DEFAULT_DB_PATH) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.executescript(SCHEMA_PATH.read_text())


@contextmanager
def get_conn(db_path: Path = DEFAULT_DB_PATH):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def upsert_games(conn: sqlite3.Connection, rows: list[dict]) -> int:
    """Insert or replace game rows. Each dict must match the `games` table columns."""
    if not rows:
        return 0
    cols = list(rows[0].keys())
    placeholders = ",".join(f":{c}" for c in cols)
    sql = f"INSERT OR REPLACE INTO games ({','.join(cols)}) VALUES ({placeholders})"
    conn.executemany(sql, rows)
    return len(rows)


def upsert_market_snapshots(conn: sqlite3.Connection, rows: list[dict]) -> int:
    if not rows:
        return 0
    cols = list(rows[0].keys())
    placeholders = ",".join(f":{c}" for c in cols)
    sql = f"INSERT INTO market_snapshots ({','.join(cols)}) VALUES ({placeholders})"
    conn.executemany(sql, rows)
    return len(rows)


def upsert_predictions(conn: sqlite3.Connection, rows: list[dict]) -> int:
    if not rows:
        return 0
    cols = list(rows[0].keys())
    placeholders = ",".join(f":{c}" for c in cols)
    sql = f"INSERT OR REPLACE INTO predictions ({','.join(cols)}) VALUES ({placeholders})"
    conn.executemany(sql, rows)
    return len(rows)


def insert_backtest_run(conn: sqlite3.Connection, row: dict) -> None:
    cols = list(row.keys())
    placeholders = ",".join(f":{c}" for c in cols)
    sql = f"INSERT OR REPLACE INTO backtest_runs ({','.join(cols)}) VALUES ({placeholders})"
    conn.execute(sql, row)
