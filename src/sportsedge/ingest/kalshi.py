"""Free, public, no-auth-required market data from Kalshi (CFTC-regulated
event-contract exchange). Read-only market data (prices/order books) does not
require an API key -- only order placement does. We use this as the primary
live "market odds" source since Kalshi's $-denominated yes price on a binary
contract *is* the market-implied probability directly.

NFL: series KXNFLGAME, one binary market per team ("<team> wins").
EPL: series KXEPLGAME, one binary market per team plus a separate "Tie" market.

Teams are resolved from ticker structure (see ingest/teams.py), not from the
printed team names, so no fuzzy name matching is involved.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

import requests

from sportsedge.ingest.teams import (
    TeamResolutionError,
    parse_event_ticker,
    selection_for,
)

BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"

SERIES = {"nfl": "KXNFLGAME", "soccer": "KXEPLGAME"}
LEAGUE = {"nfl": "NFL", "soccer": "EPL"}

# Paginating several series back-to-back reliably trips Kalshi's rate limiter,
# and this runs unattended on a schedule, so a 429 must not cost the run.
MAX_RETRIES = 5
BACKOFF_BASE = 2.0
RETRY_STATUSES = {429, 500, 502, 503, 504}


def _get(path: str, params: dict | None = None) -> dict:
    last_exc = None
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(f"{BASE_URL}{path}", params=params, timeout=15)
            resp.raise_for_status()
            return resp.json()
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else None
            if status not in RETRY_STATUSES or attempt == MAX_RETRIES - 1:
                raise
            last_exc = exc
        except requests.RequestException as exc:
            if attempt == MAX_RETRIES - 1:
                raise
            last_exc = exc
        time.sleep(BACKOFF_BASE ** attempt)
    raise last_exc  # pragma: no cover - loop always returns or raises above


def fetch_series_markets(series_ticker: str, status: str = "open") -> list[dict]:
    """Paginate through all markets for a series ticker (e.g. KXNFLGAME)."""
    markets: list[dict] = []
    cursor = None
    while True:
        params = {"series_ticker": series_ticker, "status": status, "limit": 200}
        if cursor:
            params["cursor"] = cursor
        page = _get("/markets", params=params)
        markets.extend(page.get("markets", []))
        cursor = page.get("cursor")
        if not cursor or not page.get("markets"):
            break
    return markets


def _f(value) -> float | None:
    """Kalshi returns dollar amounts as strings; coerce to float or None."""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _mid_prob(market: dict) -> float | None:
    bid = _f(market.get("yes_bid_dollars"))
    ask = _f(market.get("yes_ask_dollars"))
    if bid is None or ask is None:
        return None
    if bid == 0 and ask == 0:
        return None
    return (bid + ask) / 2


def snapshot_moneylines(sport: str) -> list[dict]:
    """One row per tradeable contract for every open game in the series.

    Rows carry full home/away identity plus the liquidity fields needed to
    decide whether a quote is actually fillable (see betting/liquidity.py).
    """
    if sport not in SERIES:
        raise ValueError(f"Unsupported sport: {sport!r}")

    markets = fetch_series_markets(SERIES[sport])
    now = datetime.now(timezone.utc).isoformat()
    rows: list[dict] = []

    for m in markets:
        event_ticker = m.get("event_ticker")
        ticker = m.get("ticker")
        if not event_ticker or not ticker:
            continue
        try:
            teams = parse_event_ticker(event_ticker, sport)
            selection = selection_for(ticker, event_ticker, sport)
        except TeamResolutionError:
            # Unresolvable ticker: skip the row rather than guess a side, but
            # let it surface in the snapshot count mismatch.
            continue

        bid = _f(m.get("yes_bid_dollars"))
        ask = _f(m.get("yes_ask_dollars"))
        rows.append({
            "sport": sport,
            "league": LEAGUE[sport],
            "event_ticker": event_ticker,
            "market_ticker": ticker,
            "game_id": None,          # resolved at join time against the stats source
            "home_team": teams["home_team"],
            "away_team": teams["away_team"],
            "commence_time": m.get("expected_expiration_time"),
            "selection": selection,   # 'home' | 'away' | 'draw'
            "yes_bid": bid,
            "yes_ask": ask,
            "implied_prob_mid": _mid_prob(m),
            "spread": None if bid is None or ask is None else round(ask - bid, 4),
            "yes_bid_size": _f(m.get("yes_bid_size_fp")),
            "yes_ask_size": _f(m.get("yes_ask_size_fp")),
            "volume": _f(m.get("volume_fp")),
            "volume_24h": _f(m.get("volume_24h_fp")),
            "open_interest": _f(m.get("open_interest_fp")),
            "status": m.get("status"),
            "source": "kalshi",
            "fetched_at": now,
        })
    return rows


def snapshot_nfl_moneylines() -> list[dict]:
    return snapshot_moneylines("nfl")


def snapshot_epl_moneylines() -> list[dict]:
    return snapshot_moneylines("soccer")


def fetch_settled_results(sport: str) -> dict[str, str]:
    """Map market_ticker -> Kalshi settlement ('yes' | 'no') for finalized markets.

    Kalshi's own resolution is a useful independent cross-check on the stats
    source, and it covers both sports through one code path.
    """
    if sport not in SERIES:
        raise ValueError(f"Unsupported sport: {sport!r}")
    out: dict[str, str] = {}
    for m in fetch_series_markets(SERIES[sport], status="settled"):
        result = m.get("result")
        if result in ("yes", "no") and m.get("ticker"):
            out[m["ticker"]] = result
    return out
