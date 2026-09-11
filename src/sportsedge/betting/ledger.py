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
    # Added once the live pipeline existed:
    "mode",              # 'shadow' (model not validated) | 'live' (paper bet)
    "market_ticker",     # Kalshi contract, for settlement + CLV lookup
    "market_fair_prob",  # de-vigged market probability at recommendation time
    # Kalshi's market expiration -- 3-6h AFTER kickoff, useful only as a coarse
    # anchor for matching the fixture. Was called `commence_time` until
    # 2026-09-11, under which name it was used as the pre-game cutoff for
    # closing-price lookups and quietly admitted in-play prices into CLV.
    "expiration_time",
    # The real kickoff, resolved from the stats source. None means "unknown",
    # and an unknown kickoff means no CLV -- never a fallback to expiry.
    "kickoff_utc",
    # Which pricing pipeline produced this row (see recommend.PRICING_VERSION).
    # Tracked alongside model_version so that a change to the gate/de-vig/
    # ask-pricing invalidates stale rows even when the model never moved.
    "pricing_version",
]

# Shadow rows record what an unvalidated model *would* have done. They are
# evidence, not results, so they are reported separately and never folded into
# headline win rate or ROI.
SHADOW = "shadow"
LIVE = "live"

SETTLED_STATUSES = ("won", "lost", "push")


# Identifier columns must round-trip as strings. A bet_id is 8 hex chars, so
# roughly 2% of them are all digits ('80412665') and pandas would infer int64 on
# read -- after which every lookup by the string id silently misses and
# settlement raises KeyError. Same hazard for any all-numeric ticker.
_ID_COLUMNS = {"bet_id": str, "game_id": str, "market_ticker": str}


def _load() -> pd.DataFrame:
    if LEDGER_PATH.exists():
        df = pd.read_csv(LEDGER_PATH, dtype=_ID_COLUMNS)
        return df.astype(object).where(pd.notnull(df), None)
    return pd.DataFrame(columns=COLUMNS).astype(object)


def _save(df: pd.DataFrame) -> None:
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(LEDGER_PATH, index=False)


def add_bet(*, sport: str, league: str, game_id: str, matchup: str, market: str,
            selection: str, model_prob: float, model_version: str,
            market_odds_decimal: float, book: str, edge_pct: float, stake: float,
            kelly_fraction: float | None = None, notes: str = "",
            mode: str = SHADOW, market_ticker: str | None = None,
            market_fair_prob: float | None = None,
            expiration_time: str | None = None,
            kickoff_utc: str | None = None,
            pricing_version: str | None = None) -> str:
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
        "notes": notes, "mode": mode, "market_ticker": market_ticker,
        "market_fair_prob": market_fair_prob, "expiration_time": expiration_time,
        "kickoff_utc": kickoff_utc, "pricing_version": pricing_version,
    }
    df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    _save(df)
    return bet_id


def existing_keys() -> set[tuple]:
    """(market_ticker, model_version, pricing_version) already in the ledger.

    The recommender runs on a schedule against overlapping snapshots, so without
    this every run would re-log the same open game and inflate the bet count.

    `pricing_version` is part of the key on purpose. Deduping on the model
    alone meant a change to the pricing pipeline -- the liquidity gate, the
    de-vig, ask-vs-mid -- left existing rows in place and refused to re-price
    them, because the model string had not moved. That is how 12 EPL rows
    survived the 2026-09-10 liquidity fix that voided their NFL counterparts.
    """
    df = _load()
    if df.empty or "market_ticker" not in df.columns:
        return set()
    return {
        (r["market_ticker"], r["model_version"], r.get("pricing_version"))
        for _, r in df.iterrows()
        if r.get("market_ticker")
    }


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


def _summarize_frame(df: pd.DataFrame) -> dict:
    settled = df[df["status"].isin(SETTLED_STATUSES)] if not df.empty else df
    # Voided rows are withdrawn evidence, not open positions. Counting them as
    # pending overstated the live book by 30 rows and folded prices the
    # project has explicitly disowned into avg_edge_pct -- including two
    # voided EPL rows whose "edges" were +206% and +64%, which alone moved the
    # shadow average by more than 10 points.
    voided = df[df["status"] == "void"] if not df.empty else df
    open_bets = len(df) - len(settled) - len(voided)
    active = df[~df["status"].isin([*SETTLED_STATUSES, "void"])] if not df.empty else df
    base = {
        "total_bets": len(df) - len(voided),
        "settled": len(settled),
        "pending": open_bets,
        "void": len(voided),
        "avg_edge_pct": (
            pd.concat([settled, active])["edge_pct"].mean()
            if not df.empty and (len(settled) + len(active)) else None
        ),
    }
    if df.empty or settled.empty:
        return {**base, "win_rate": None, "roi_pct": None, "avg_clv_pct": None,
                "clv_positive_rate": None}

    decided = settled[settled["status"] != "push"]
    wins = (decided["status"] == "won").sum()
    staked = decided["stake"].sum()
    returned = (decided["stake"] * decided["market_odds_decimal"] * (decided["status"] == "won")).sum()
    clv = settled["clv_pct"].dropna()
    return {
        **base,
        "win_rate": wins / len(decided) * 100 if len(decided) else None,
        "roi_pct": (returned - staked) / staked * 100 if staked else None,
        "avg_clv_pct": clv.mean() if not clv.empty else None,
        "clv_positive_rate": (clv > 0).mean() * 100 if not clv.empty else None,
    }


def summarize() -> dict:
    """Headline stats for LIVE paper bets, with shadow evidence reported apart.

    Keeping these separate is the whole point: shadow rows come from models that
    have not cleared backtest, so blending them into a single win rate would
    describe nothing real.
    """
    df = _load()
    if df.empty:
        return {**_summarize_frame(df), "shadow": _summarize_frame(df)}

    mode = df["mode"] if "mode" in df.columns else pd.Series([LIVE] * len(df))
    mode = mode.fillna(LIVE)
    live_df = df[mode != SHADOW]
    shadow_df = df[mode == SHADOW]
    return {**_summarize_frame(live_df), "shadow": _summarize_frame(shadow_df)}
