"""Free, public, no-auth-required market data from Kalshi (CFTC-regulated
event-contract exchange). Read-only market data (prices/order books) does not
require an API key -- only order placement does. We use this as the primary
live "market odds" source since Kalshi's $-denominated yes price on a binary
contract *is* the market-implied probability directly.

NFL: series KXNFLGAME, one binary market per team ("<team> wins").
EPL: series KXEPLGAME, one binary market per team plus a separate "Tie" market.

FIELD NAMES -- verified against the live API 2026-09-10. The v2 /markets
response does NOT contain `volume`, `open_interest`, or `liquidity`. It
carries `volume_fp`, `volume_24h_fp`, `open_interest_fp`, `yes_bid_size_fp`,
`yes_ask_size_fp`, and `liquidity_dollars`. Of these, `liquidity_dollars`
read 0.0000 on all 122 open NFL+EPL markets sampled, so it is useless as a
liquidity filter -- use volume / open interest / resting size instead.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import requests

from sportsedge.betting.edge import executable_price, mid_price, spread_cost_fraction

BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"


def _get(path: str, params: dict | None = None) -> dict:
    resp = requests.get(f"{BASE_URL}{path}", params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()


def _f(value) -> float | None:
    """Kalshi returns numbers as strings ('0.1700', '3378013.38')."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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


def _market_row(m: dict, sport: str, league: str, fetched_at: str) -> dict:
    """One normalized snapshot row. Records BOTH the mid (fair-value estimate)
    and the executable ask (what you would actually pay), plus the liquidity
    fields needed to decide whether the quote is real or stale."""
    bid = _f(m.get("yes_bid_dollars"))
    ask = _f(m.get("yes_ask_dollars"))
    return {
        "sport": sport,
        "league": league,
        "event_ticker": m.get("event_ticker"),
        "market_ticker": m.get("ticker"),
        "game_id": None,
        "home_team": None,  # resolved downstream via event title / roster join
        "away_team": None,
        "commence_time": m.get("expected_expiration_time"),
        "selection": m.get("yes_sub_title"),  # team name as printed by Kalshi, or 'Tie'
        "yes_bid": bid,
        "yes_ask": ask,
        "implied_prob_mid": mid_price(bid, ask),
        "executable_prob_yes": executable_price(bid, ask, "yes"),
        "spread_cost_frac": spread_cost_fraction(bid, ask) if bid and ask else None,
        "volume": _f(m.get("volume_fp")),
        "volume_24h": _f(m.get("volume_24h_fp")),
        "open_interest": _f(m.get("open_interest_fp")),
        "yes_bid_size": _f(m.get("yes_bid_size_fp")),
        "yes_ask_size": _f(m.get("yes_ask_size_fp")),
        "status": m.get("status"),
        "source": "kalshi",
        "fetched_at": fetched_at,
    }


def snapshot_series(series_ticker: str, sport: str, league: str) -> list[dict]:
    markets = fetch_series_markets(series_ticker)
    now = datetime.now(timezone.utc).isoformat()
    return [_market_row(m, sport, league, now) for m in markets]


def snapshot_nfl_moneylines() -> list[dict]:
    return snapshot_series("KXNFLGAME", "nfl", "NFL")


def snapshot_epl_moneylines() -> list[dict]:
    return snapshot_series("KXEPLGAME", "soccer", "EPL")


# -- liquidity gating ---------------------------------------------------------

MIN_OPEN_INTEREST = 500.0
MIN_VOLUME = 500.0
MIN_RESTING_SIZE = 50.0
MAX_SPREAD_COST_FRAC = 0.02


def is_tradeable(row: dict, *, min_open_interest: float = MIN_OPEN_INTEREST,
                 min_volume: float = MIN_VOLUME, min_resting_size: float = MIN_RESTING_SIZE,
                 max_spread_cost: float = MAX_SPREAD_COST_FRAC) -> bool:
    """Is this quote a real, fillable price rather than a stale or token one?

    Deliberately conservative: a quote that fails any of these is excluded
    rather than discounted. `liquidity_dollars` is NOT used -- it reads zero
    on every market we have sampled.
    """
    if row.get("executable_prob_yes") is None:
        return False
    if (row.get("open_interest") or 0) < min_open_interest:
        return False
    if (row.get("volume") or 0) < min_volume:
        return False
    if min(row.get("yes_bid_size") or 0, row.get("yes_ask_size") or 0) < min_resting_size:
        return False
    cost = row.get("spread_cost_frac")
    if cost is None or cost > max_spread_cost:
        return False
    return True


# -- historical prices via candlesticks ---------------------------------------
#
# The settled-market record is useless for reconstructing a closing price:
# once a market settles the book empties, so previous_yes_bid_dollars reads
# 0.0000 and previous_yes_ask_dollars reads 1.0000 on every settled market.
# The candlestick endpoint keeps the real bid/ask series, so that is what we
# use to recover a genuine pre-kickoff closing quote.


def fetch_candlesticks(series_ticker: str, market_ticker: str, start_ts: int,
                       end_ts: int, period_interval: int = 60) -> list[dict]:
    """period_interval is in minutes (1, 60, or 1440)."""
    path = f"/series/{series_ticker}/markets/{market_ticker}/candlesticks"
    data = _get(path, params={"start_ts": start_ts, "end_ts": end_ts,
                              "period_interval": period_interval})
    return data.get("candlesticks", [])


def closing_quote_before(series_ticker: str, market_ticker: str, kickoff: datetime,
                         lookback_hours: int = 72) -> dict | None:
    """Last two-sided quote strictly BEFORE kickoff.

    Taking the final candle before settlement would capture in-play prices --
    a market that closes hours after kickoff has already absorbed the result.
    That would be lookahead leakage dressed up as a closing line.
    """
    end_ts = int(kickoff.timestamp())
    start_ts = int((kickoff - timedelta(hours=lookback_hours)).timestamp())
    candles = fetch_candlesticks(series_ticker, market_ticker, start_ts, end_ts)

    for candle in reversed(candles):
        if candle.get("end_period_ts", 0) > end_ts:
            continue
        bid = _f((candle.get("yes_bid") or {}).get("close_dollars"))
        ask = _f((candle.get("yes_ask") or {}).get("close_dollars"))
        if bid is None or ask is None or bid <= 0 or ask <= 0 or ask <= bid:
            continue
        return {
            "market_ticker": market_ticker,
            "ts": datetime.fromtimestamp(candle["end_period_ts"], timezone.utc).isoformat(),
            "yes_bid": bid,
            "yes_ask": ask,
            "implied_prob_mid": mid_price(bid, ask),
            "executable_prob_yes": executable_price(bid, ask, "yes"),
            "spread_cost_frac": spread_cost_fraction(bid, ask),
            "volume": _f(candle.get("volume_fp")),
            "open_interest": _f(candle.get("open_interest_fp")),
        }
    return None
