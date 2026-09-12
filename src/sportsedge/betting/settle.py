"""Settle pending bets and compute closing-line value.

Nothing called `record_result()` outside the test suite before this module, so
even if bets had existed they would have sat pending forever and the `clv_pct`
column -- described in the README as a better short-run skill signal than win
rate -- would have stayed empty permanently.

Settlement source: Kalshi's own market resolution (`result` = 'yes'/'no' on a
finalized market). That is the same contract we priced, so it settles both
sports through one path and cannot disagree with the thing we actually bet.
`verify_against_stats()` cross-checks those settlements against the independent
stats source, because a single self-consistent source is exactly how a silent
mapping bug survives.

CLV: the last price we captured before kickoff, from the committed snapshot
history. It is therefore only as good as snapshot cadence -- a bet placed and
settled between two daily snapshots gets no closing price, and we record that
as missing rather than substituting the settlement price (which would score a
guaranteed +100% CLV and be pure fiction).
"""
from __future__ import annotations

import pandas as pd

from sportsedge.betting import ledger as ledger_mod
from sportsedge.ingest import kickoff as kickoff_mod
from sportsedge.ingest.kalshi import fetch_settled_results
from sportsedge.storage import snapshots


def _clv_pct(placed_odds: float, closing_odds: float) -> float:
    """Positive when we got a better price than the close."""
    return (placed_odds / closing_odds - 1) * 100


def _teams_from_matchup(bet: pd.Series) -> tuple[str, str] | None:
    """('home', 'away') for a bet, from the stored matchup 'AWAY @ HOME'."""
    matchup = bet.get("matchup")
    if not matchup or " @ " not in str(matchup):
        return None
    away, home = str(matchup).split(" @ ", 1)
    return home.strip(), away.strip()


def _kickoff_for(bet: pd.Series) -> str | None:
    """True kickoff for a bet, ISO 8601, or None if the stats source lacks it."""
    stored = bet.get("kickoff_utc")
    if stored and not pd.isna(stored):
        return str(stored)

    teams = _teams_from_matchup(bet)
    if teams is None:
        return None
    ko = kickoff_mod.resolve_kickoff(bet.get("sport"), teams[0], teams[1],
                                     bet.get("expiration_time"))
    return None if ko is None else ko.isoformat()


def settle_pending(*, sports: tuple[str, ...] = ("nfl", "soccer"),
                   dry_run: bool = False) -> dict:
    """Resolve every pending bet whose Kalshi contract has finalized."""
    df = ledger_mod._load()
    if df.empty:
        return {"pending": 0, "settled": 0, "clv_filled": 0, "unresolved": 0, "changes": []}

    pending = df[df["status"] == "pending"]
    if pending.empty:
        return {"pending": 0, "settled": 0, "clv_filled": 0, "unresolved": 0, "changes": []}

    results: dict[str, str] = {}
    for sport in sports:
        try:
            results.update(fetch_settled_results(sport))
        except Exception as exc:  # network/API problem shouldn't lose the rest
            results.setdefault("__errors__", "")
            print(f"warning: could not fetch settled {sport} markets: {exc}")

    settled = clv_filled = unresolved = 0
    changes = []

    for idx, bet in pending.iterrows():
        ticker = bet.get("market_ticker")
        if not ticker or ticker not in results:
            unresolved += 1
            continue

        status = "won" if results[ticker] == "yes" else "lost"
        resolved_kickoff = _kickoff_for(bet)
        closing = _closing_odds(bet)
        clv = None
        if closing is not None and bet.get("market_odds_decimal"):
            clv = _clv_pct(float(bet["market_odds_decimal"]), closing)
            clv_filled += 1

        changes.append({
            "bet_id": bet["bet_id"], "matchup": bet.get("matchup"),
            "selection": bet.get("selection"), "status": status,
            "closing_odds_decimal": closing, "clv_pct": clv,
            "kickoff_utc": resolved_kickoff,
            "clv_missing_reason": None if clv is not None else (
                "no kickoff in stats source" if resolved_kickoff is None
                else "no snapshot captured before kickoff"),
        })
        settled += 1

        if not dry_run:
            df.loc[idx, "status"] = status
            df.loc[idx, "result_logged_at"] = pd.Timestamp.now(tz="UTC").isoformat()
            if resolved_kickoff is not None:
                df.loc[idx, "kickoff_utc"] = resolved_kickoff
            if closing is not None:
                df.loc[idx, "closing_odds_decimal"] = closing
            if clv is not None:
                df.loc[idx, "clv_pct"] = clv

    if not dry_run and settled:
        ledger_mod._save(df)

    return {"pending": len(pending), "settled": settled, "clv_filled": clv_filled,
            "unresolved": unresolved, "changes": changes}


def backfill_clv(*, dry_run: bool = False) -> dict:
    """Fill CLV on settled bets whose kickoff reached the stats source late.

    Why this exists
    ---------------
    `settle_pending` computes CLV exactly once, at settlement, and only ever
    iterates rows that are still `pending`. For NFL that is sufficient:
    nflverse publishes the whole season's schedule in advance, so a game's
    kickoff is known weeks before it is played and CLV is always computable at
    the moment the market finalizes.

    football-data.co.uk publishes only COMPLETED matches, and publishes them
    days late -- on 2026-09-12 its 2026-27 file still ended at 2026-09-06. So
    an EPL contract settles from Kalshi within minutes of the final whistle,
    at a moment when no stats source can yet say when that match kicked off.
    `_closing_odds` then correctly declines to guess and the bet settles with
    `clv_pct` empty.

    Nothing ever went back for it. The row is no longer pending, so every
    later run skips it, and the CLV -- which the README calls the better
    short-run skill signal than win rate -- was lost permanently, even though
    every price needed to compute it was already sitting in the committed
    snapshots. That made EPL CLV coverage structurally zero rather than merely
    thin, and it would have done so silently: the missing-reason string is
    per-bet and never surfaced in an aggregate.

    What this pass does and does not do
    -----------------------------------
    It revisits settled rows with no CLV, re-resolves the kickoff now that the
    stats source may have caught up, and fills the number from the snapshot
    history. It fills `kickoff_utc`, `closing_odds_decimal` and `clv_pct` and
    touches nothing else -- not status, result, stake, selection, price, edge
    or pricing_version. It never overwrites a CLV that is already present.

    The cutoff is still the true kickoff, exactly as in `_closing_odds`, so a
    late fill cannot admit an in-play price that settlement would have
    rejected. A backfill that reached for the expiration instead would rebuild
    the precise lookahead bug run 3 removed, one sport over and a week later.
    """
    # The schedule is memoised, and the entire premise of this pass is that
    # the stats table has changed since it was last read.
    kickoff_mod.clear_cache()

    df = ledger_mod._load()
    if df.empty:
        return {"candidates": 0, "filled": 0, "still_missing": 0, "changes": []}

    settled_no_clv = df[
        df["status"].isin(ledger_mod.SETTLED_STATUSES) & df["clv_pct"].isna()
    ]
    if settled_no_clv.empty:
        return {"candidates": 0, "filled": 0, "still_missing": 0, "changes": []}

    filled = 0
    changes = []

    for idx, bet in settled_no_clv.iterrows():
        resolved_kickoff = _kickoff_for(bet)
        closing = _closing_odds(bet)
        clv = None
        if closing is not None and bet.get("market_odds_decimal"):
            clv = _clv_pct(float(bet["market_odds_decimal"]), closing)

        changes.append({
            "bet_id": bet["bet_id"], "matchup": bet.get("matchup"),
            "sport": bet.get("sport"), "status": bet.get("status"),
            "kickoff_utc": resolved_kickoff,
            "closing_odds_decimal": closing, "clv_pct": clv,
            "reason": None if clv is not None else (
                "no kickoff in stats source" if resolved_kickoff is None
                else "no snapshot captured before kickoff"),
        })

        if clv is not None:
            filled += 1

        if not dry_run:
            # Record the kickoff even when no CLV follows from it: it changes
            # the diagnosis from "the stats source is behind" to "our snapshot
            # cadence missed the window", and those need different fixes.
            if resolved_kickoff is not None:
                df.loc[idx, "kickoff_utc"] = resolved_kickoff
            if closing is not None:
                df.loc[idx, "closing_odds_decimal"] = closing
            if clv is not None:
                df.loc[idx, "clv_pct"] = clv

    if not dry_run and changes:
        ledger_mod._save(df)

    return {"candidates": len(settled_no_clv), "filled": filled,
            "still_missing": len(settled_no_clv) - filled, "changes": changes}


def _closing_odds(bet: pd.Series) -> float | None:
    """Last observed pre-kickoff ask for this contract, as decimal odds.

    The cutoff is the TRUE kickoff from the stats source, never Kalshi's
    expiration. The expiration lands 3-6h after the ball is snapped, so using
    it admitted in-play quotes -- and an in-play quote is a price that already
    knows the result, which turns CLV into a restatement of win/loss dressed
    up as evidence of skill.

    If the kickoff cannot be resolved we return None and the bet settles with
    no CLV. That is the intended behaviour: a missing number is recoverable,
    a fabricated one is not.
    """
    ticker, sport = bet.get("market_ticker"), bet.get("sport")
    if not ticker or not sport:
        return None

    cutoff = _kickoff_for(bet)
    if cutoff is None:
        return None
    row = snapshots.latest_before(sport, ticker, str(cutoff))
    if not row:
        return None
    ask = row.get("yes_ask")
    if ask is None or pd.isna(ask) or float(ask) <= 0:
        return None
    return 1.0 / float(ask)


_MONTHS = {m: i for i, m in enumerate(
    ["JAN", "FEB", "MAR", "APR", "MAY", "JUN",
     "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], start=1)}


def ticker_date(date_code: str) -> str:
    """'26SEP21' -> '2026-09-21'."""
    year = 2000 + int(date_code[:2])
    month = _MONTHS[date_code[2:5]]
    return f"{year:04d}-{month:02d}-{int(date_code[5:]):02d}"


def _lookup_by_date(by_key: dict, teams: dict, tolerance_days: int = 1) -> str | None:
    """Find a game by (date, home, away), allowing +/-1 day.

    The tolerance covers timezone skew between Kalshi's scheduled date and the
    stats source's game date (late kickoffs, matches played abroad).
    """
    target = pd.Timestamp(ticker_date(teams["date_code"]))
    for offset in range(-tolerance_days, tolerance_days + 1):
        day = (target + pd.Timedelta(days=offset)).strftime("%Y-%m-%d")
        hit = by_key.get((day, teams["home_team"], teams["away_team"]))
        if hit is not None:
            return hit
    return None


def verify_against_stats(games: pd.DataFrame, sport: str) -> dict:
    """Cross-check Kalshi settlements against the independent stats source.

    Returns counts plus any disagreements. A non-empty `mismatches` list means
    either our home/away mapping is wrong or a market resolved unusually --
    both worth stopping for.
    """
    from sportsedge.ingest.teams import parse_event_ticker, market_team_code

    results = fetch_settled_results(sport)
    played = games.dropna(subset=["home_score", "away_score"])

    # Key on date as well as teams: the same pairing recurs across preseason,
    # both halves of a home-and-away season, and playoffs. Matching on teams
    # alone silently compares a market to a different game.
    by_key: dict[tuple[str, str, str], str] = {
        (str(g["game_date"])[:10], g["home_team"], g["away_team"]): g["result"]
        for _, g in played.iterrows()
    }

    checked, agreed, mismatches, unmatched = 0, 0, [], 0
    for ticker, settlement in results.items():
        event_ticker = ticker.rsplit("-", 1)[0]
        try:
            teams = parse_event_ticker(event_ticker, sport)
            code = market_team_code(ticker, event_ticker)
        except Exception:
            continue

        actual = _lookup_by_date(by_key, teams)
        if actual is None:
            unmatched += 1
            continue

        if sport == "soccer" and code == "TIE":
            expected = "yes" if actual == "D" else "no"
        elif code == teams["home_code"]:
            expected = "yes" if actual == "H" else "no"
        elif code == teams["away_code"]:
            expected = "yes" if actual == "A" else "no"
        else:
            continue

        checked += 1
        if expected == settlement:
            agreed += 1
        else:
            mismatches.append({
                "ticker": ticker, "kalshi": settlement, "expected": expected,
                "home": teams["home_team"], "away": teams["away_team"], "result": actual,
            })

    return {"checked": checked, "agreed": agreed, "unmatched_games": unmatched,
            "mismatches": mismatches}
