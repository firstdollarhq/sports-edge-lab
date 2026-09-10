"""CSV paper-trading bet ledger: bets/ledger.csv. This is the primary
human-readable record of what the model recommended, what the market actually
offered, and what happened -- kept separate from the SQLite DB so it's easy
to open, diff in git, and eyeball for bias."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

LEDGER_PATH = Path(__file__).parents[3] / "bets" / "ledger.csv"

COLUMNS = [
    "bet_id", "placed_at", "sport", "league", "game_id", "matchup", "market",
    "selection", "model_prob", "model_version", "market_odds_decimal", "book",
    "edge_pct", "stake", "kelly_fraction", "status", "closing_odds_decimal",
    "clv_pct", "result_logged_at", "notes",
]


def _load() -> pd.DataFrame:
    if LEDGER_PATH.exists():
        return pd.read_csv(LEDGER_PATH).astype(object).where(pd.notnull, None)
    return pd.DataFrame(columns=COLUMNS).astype(object)


def _save(df: pd.DataFrame) -> None:
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(LEDGER_PATH, index=False)


def add_bet(*, sport: str, league: str, game_id: str, matchup: str, market: str,
            selection: str, model_prob: float, model_version: str,
            market_odds_decimal: float, book: str, edge_pct: float, stake: float,
            kelly_fraction: float | None = None, notes: str = "") -> str:
    df = _load()
    bet_id = str(uuid.uuid4())[:8]
    row = {
        "bet_id": bet_id,
        "placed_at": datetime.now(timezone.utc).isoformat(),
        "sport": sport, "league": league, "game_id": game_id, "matchup": matchup,
        "market": market, "selection": selection, "model_prob": model_prob,
        "model_version": model_version, "market_odds_decimal": market_odds_decimal,
        "book": book, "edge_pct": edge_pct, "stake": stake,
        "kelly_fraction": kelly_fraction, "status": "pending",
        "closing_odds_decimal": None, "clv_pct": None, "result_logged_at": None,
        "notes": notes,
    }
    df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    _save(df)
    return bet_id


def record_result(bet_id: str, status: str, closing_odds_decimal: float | None = None) -> None:
    df = _load()
    idx = df.index[df["bet_id"] == bet_id]
    if len(idx) == 0:
        raise KeyError(f"No bet with id {bet_id}")
    i = idx[0]
    df.loc[i, "status"] = status
    df.loc[i, "result_logged_at"] = datetime.now(timezone.utc).isoformat()
    if closing_odds_decimal is not None:
        df.loc[i, "closing_odds_decimal"] = closing_odds_decimal
        placed_odds = df.loc[i, "market_odds_decimal"]
        df.loc[i, "clv_pct"] = (placed_odds / closing_odds_decimal - 1) * 100
    _save(df)


def summarize() -> dict:
    df = _load()
    settled = df[df["status"].isin(["won", "lost", "push"])]
    if settled.empty:
        return {"total_bets": len(df), "settled": 0, "win_rate": None, "roi_pct": None,
                "avg_edge_pct": df["edge_pct"].mean() if not df.empty else None,
                "avg_clv_pct": None}
    decided = settled[settled["status"] != "push"]
    wins = (decided["status"] == "won").sum()
    staked = decided["stake"].sum()
    returned = (decided["stake"] * decided["market_odds_decimal"] * (decided["status"] == "won")).sum()
    return {
        "total_bets": len(df),
        "settled": len(settled),
        "win_rate": wins / len(decided) * 100 if len(decided) else None,
        "roi_pct": (returned - staked) / staked * 100 if staked else None,
        "avg_edge_pct": df["edge_pct"].mean(),
        "avg_clv_pct": settled["clv_pct"].dropna().mean() if settled["clv_pct"].notna().any() else None,
    }
