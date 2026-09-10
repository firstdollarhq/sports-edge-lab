"""Command-line entry points.

    python -m sportsedge.cli refresh-history          # rebuild durable game tables
    python -m sportsedge.cli snapshot-odds            # record today's Kalshi book (CLV substrate)
    python -m sportsedge.cli backtest-nfl --seasons 2018 2019 2020 2021 2022 2023 2024 2025
    python -m sportsedge.cli backtest-soccer --league E0 --seasons 2021 2122 2223 2324 2425 2526
    python -m sportsedge.cli kalshi-nfl
    python -m sportsedge.cli kalshi-epl
    python -m sportsedge.cli spread-report            # what crossing the spread costs today
    python -m sportsedge.cli ledger-summary
"""
from __future__ import annotations

import argparse
import json
import statistics

from sportsedge.storage import db, snapshots
from sportsedge.ingest.nfl_stats import fetch_nfl_games
from sportsedge.ingest.soccer_stats import fetch_soccer_games
from sportsedge.ingest.kalshi import (
    snapshot_nfl_moneylines,
    snapshot_epl_moneylines,
    is_tradeable,
)
from sportsedge.models.elo import NflEloModel, SoccerEloModel
from sportsedge.backtest.engine import backtest_nfl, backtest_soccer
from sportsedge.betting.ledger import summarize

# Defaults reflect what is actually available as of 2026-09: NFL 2026 and
# EPL 2026/27 are both in progress.
NFL_HISTORY = list(range(2018, 2027))
EPL_HISTORY = ["1920", "2021", "2122", "2223", "2324", "2425", "2526", "2627"]


def _nfl_season_labels(seasons) -> set[str]:
    return {str(s) for s in seasons}


def _epl_season_labels(seasons) -> set[str]:
    """'2526' -> '2025-26', matching the label written by fetch_soccer_games."""
    return {f"20{str(s)[:2]}-{str(s)[2:]}" for s in seasons}


def _load_games(table: str, seasons, label_fn, fetch, *fetch_args):
    """Prefer the committed table; fall back to a live fetch if absent.

    The season filter must be applied AFTER loading: the committed table holds
    every season ever ingested, so reading it without filtering silently
    ignores --seasons and hands the backtest a different sample than asked
    for -- e.g. holding out the 30-game in-progress season instead of a
    completed 380-game one.
    """
    try:
        df = snapshots.read_processed(table)
    except FileNotFoundError:
        df = fetch(*fetch_args)
    wanted = label_fn(seasons)
    filtered = df[df["season"].astype(str).isin(wanted)]
    missing = wanted - set(filtered["season"].astype(str))
    if missing:
        print(f"[warn] no rows for seasons: {sorted(missing)}")
    if filtered.empty:
        raise SystemExit(f"No games for seasons {sorted(wanted)} in {table}")
    return filtered


def cmd_refresh_history(args):
    """Rebuild the durable historical tables from the free upstream sources."""
    nfl = fetch_nfl_games(args.nfl_seasons)
    path, n = snapshots.write_processed("nfl_games", nfl)
    print(f"nfl_games -> {path} ({n} rows, {nfl['home_score'].notna().sum()} played)")

    epl = fetch_soccer_games("E0", args.epl_seasons)
    path, n = snapshots.write_processed("epl_games", epl)
    print(f"epl_games -> {path} ({n} rows)")

    db.init_db()
    with db.get_conn() as conn:
        db.upsert_games(conn, nfl.where(nfl.notna(), None).to_dict("records"))
        db.upsert_games(conn, epl.where(epl.notna(), None).to_dict("records"))
    print("SQLite cache rebuilt from the committed tables.")


def cmd_snapshot_odds(_args):
    """Record the current Kalshi book. Run daily -- CLV cannot be backfilled."""
    rows = snapshot_nfl_moneylines() + snapshot_epl_moneylines()
    path, n = snapshots.write_snapshot(rows)
    tradeable = sum(1 for r in rows if is_tradeable(r))
    print(f"Wrote {n} quotes -> {path}")
    print(f"Passing the liquidity filter: {tradeable}/{len(rows)}")


def cmd_backtest_nfl(args):
    games = _load_games("nfl_games", args.seasons, _nfl_season_labels,
                        fetch_nfl_games, args.seasons)
    model = NflEloModel(use_mov_multiplier=args.mov)
    result = backtest_nfl(games, model, edge_threshold=args.edge_threshold / 100)
    print(json.dumps({k: v for k, v in result.items() if k != "bets"}, indent=2, default=str))
    print(f"Bets flagged: {len(result['bets'])} of {result['n_games']} games")


def cmd_backtest_soccer(args):
    games = _load_games("epl_games", args.seasons, _epl_season_labels,
                        fetch_soccer_games, args.league, args.seasons)
    model = SoccerEloModel()
    result = backtest_soccer(games, model, edge_threshold=args.edge_threshold / 100)
    print(json.dumps({k: v for k, v in result.items() if k != "bets"}, indent=2, default=str))
    print(f"Bets flagged: {len(result['bets'])} of {result['n_games']} games")


def _print_book(rows):
    for r in rows[:20]:
        flag = "OK " if is_tradeable(r) else "SKIP"
        print(f"{flag} {r['event_ticker']:<28} {str(r['selection']):<20} "
              f"bid {r['yes_bid']} ask {r['yes_ask']} oi {r['open_interest']}")
    print(f"... {len(rows)} markets total, {sum(1 for r in rows if is_tradeable(r))} tradeable")


def cmd_kalshi_nfl(_args):
    _print_book(snapshot_nfl_moneylines())


def cmd_kalshi_epl(_args):
    _print_book(snapshot_epl_moneylines())


def cmd_spread_report(_args):
    """How much of the edge threshold the bid-ask spread eats, per venue."""
    for label, rows in (("NFL", snapshot_nfl_moneylines()), ("EPL", snapshot_epl_moneylines())):
        costs = [r["spread_cost_frac"] * 100 for r in rows if r.get("spread_cost_frac") is not None]
        if not costs:
            print(f"{label}: no two-sided quotes")
            continue
        costs.sort()
        over = sum(1 for c in costs if c >= 3.0)
        print(f"{label}: n={len(costs)} median={statistics.median(costs):.2f}% "
              f"p75={costs[int(len(costs) * 0.75)]:.2f}% max={costs[-1]:.2f}% "
              f"| >=3.0% (whole threshold): {over}/{len(costs)}")


def cmd_ledger_summary(_args):
    print(json.dumps(summarize(), indent=2, default=str))


def main():
    parser = argparse.ArgumentParser(prog="sportsedge")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("refresh-history")
    p.add_argument("--nfl-seasons", nargs="+", type=int, default=NFL_HISTORY)
    p.add_argument("--epl-seasons", nargs="+", default=EPL_HISTORY)
    p.set_defaults(func=cmd_refresh_history)

    p = sub.add_parser("snapshot-odds")
    p.set_defaults(func=cmd_snapshot_odds)

    p = sub.add_parser("backtest-nfl")
    p.add_argument("--seasons", nargs="+", type=int, default=NFL_HISTORY)
    p.add_argument("--edge-threshold", type=float, default=3.0, help="percent")
    p.add_argument("--mov", action="store_true", help="use margin-of-victory K scaling")
    p.set_defaults(func=cmd_backtest_nfl)

    p = sub.add_parser("backtest-soccer")
    p.add_argument("--league", default="E0")
    p.add_argument("--seasons", nargs="+", default=EPL_HISTORY)
    p.add_argument("--edge-threshold", type=float, default=3.0, help="percent")
    p.set_defaults(func=cmd_backtest_soccer)

    p = sub.add_parser("kalshi-nfl")
    p.set_defaults(func=cmd_kalshi_nfl)

    p = sub.add_parser("kalshi-epl")
    p.set_defaults(func=cmd_kalshi_epl)

    p = sub.add_parser("spread-report")
    p.set_defaults(func=cmd_spread_report)

    p = sub.add_parser("ledger-summary")
    p.set_defaults(func=cmd_ledger_summary)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
