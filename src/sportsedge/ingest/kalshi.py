"""Free, public, no-auth-required market data from Kalshi (CFTC-regulated
event-contract exchange). Read-only market data (prices/order books) does not
require an API key -- only order placement does. We use this as the primary
live "market odds" source since Kalshi's $-denominated yes price on a binary
contract *is* the market-implied probability directly.

NFL: series KXNFLGAME, one binary market per team ("<team> wins").
EPL: series KXEPLGAME, one binary market per team plus a separate "Tie" market.
"""
from __future__ import annotations

from datetime import datetime, timezone

import requests

BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"


def _get(path: str, params: dict | None = None) -> dict:
    resp = requests.get(f"{BASE_URL}{path}", params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()


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


def _mid_prob(market: dict) -> float | None:
    bid = market.get("yes_bid_dollars")
    ask = market.get("yes_ask_dollars")
    if bid is None or ask is None:
        return None
    bid, ask = float(bid), float(ask)
    if bid == 0 and ask == 0:
        return None
    return (bid + ask) / 2


def snapshot_nfl_moneylines() -> list[dict]:
    """One row per team per upcoming game, selection='home'/'away' inferred
    from event ticker team order is NOT reliable from this endpoint alone --
    we tag by team name and let the join step match to nflverse home/away."""
    markets = fetch_series_markets("KXNFLGAME")
    now = datetime.now(timezone.utc).isoformat()
    rows = []
    for m in markets:
        prob = _mid_prob(m)
        rows.append({
            "sport": "nfl",
            "league": "NFL",
            "event_ticker": m.get("event_ticker"),
            "game_id": None,
            "home_team": None,  # resolved downstream via event title / roster join
            "away_team": None,
            "commence_time": m.get("expected_expiration_time"),
            "selection": m.get("yes_sub_title"),  # team name as printed by Kalshi
            "yes_bid": m.get("yes_bid_dollars"),
            "yes_ask": m.get("yes_ask_dollars"),
            "implied_prob_mid": prob,
            "source": "kalshi",
            "fetched_at": now,
        })
    return rows


def snapshot_epl_moneylines() -> list[dict]:
    markets = fetch_series_markets("KXEPLGAME")
    now = datetime.now(timezone.utc).isoformat()
    rows = []
    for m in markets:
        prob = _mid_prob(m)
        rows.append({
            "sport": "soccer",
            "league": "EPL",
            "event_ticker": m.get("event_ticker"),
            "game_id": None,
            "home_team": None,
            "away_team": None,
            "commence_time": m.get("expected_expiration_time"),
            "selection": m.get("yes_sub_title"),  # team name, or 'Tie'
            "yes_bid": m.get("yes_bid_dollars"),
            "yes_ask": m.get("yes_ask_dollars"),
            "implied_prob_mid": prob,
            "source": "kalshi",
            "fetched_at": now,
        })
    return rows
