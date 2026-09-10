"""Command-line entry points.

    python -m sportsedge.cli ingest-nfl --seasons 2023 2024
    python -m sportsedge.cli ingest-soccer --league E0 --seasons 2324 2425
    python -m sportsedge.cli backtest-nfl --seasons 2020 2021 2022 2023 2024
    python -m sportsedge.cli backtest-soccer --league E0 --seasons 2223 2324 2425
    python -m sportsedge.cli kalshi-nfl
    python -m sportsedge.cli kalshi-epl
    python -m sportsedge.cli ledger-summary
"""
from __future__ import annotations

import argparse
import json

from sportsedge.storage import db
from sportsedge.ingest.nfl_stats import fetch_nfl_games
from sportsedge.ingest.soccer_stats import fetch_soccer_games
from sportsedge.ingest.kalshi import snapshot_nfl_moneylines, snapshot_epl_moneylines
from sportsedge.models.elo import NflEloModel, SoccerEloModel
from sportsedge.backtest.engine import backtest_nfl, backtest_soccer
from sportsedge.betting.ledger import summarize


def cmd_ingest_nfl(args):
    db.init_db()
    games = fetch_nfl_games(args.seasons)
    with db.get_conn() as conn:
        n = db.upsert_games(conn, games.to_dict("records"))
    print(f"Ingested {n} NFL games ({games['season'].nunique()} seasons)")


def cmd_ingest_soccer(args):
    db.init_db()
    games = fetch_soccer_games(args.league, args.seasons)
    with db.get_conn() as conn:
        n = db.upsert_games(conn, games.to_dict("records"))
    print(f"Ingested {n} {args.league} games ({games['season'].nunique()} seasons)")


def cmd_backtest_nfl(args):
    games = fetch_nfl_games(args.seasons)
    model = NflEloModel(use_mov_multiplier=args.mov)
    result = backtest_nfl(games, model, edge_threshold=args.edge_threshold / 100)
    print(json.dumps({k: v for k, v in result.items() if k != "bets"}, indent=2, default=str))
    print(f"Bets flagged: {len(result['bets'])}")


def cmd_backtest_soccer(args):
    games = fetch_soccer_games(args.league, args.seasons)
    model = SoccerEloModel()
    result = backtest_soccer(games, model, edge_threshold=args.edge_threshold / 100)
    print(json.dumps({k: v for k, v in result.items() if k != "bets"}, indent=2, default=str))
    print(f"Bets flagged: {len(result['bets'])}")


def cmd_kalshi_nfl(_args):
    rows = snapshot_nfl_moneylines()
    for r in rows[:20]:
        print(r["event_ticker"], r["selection"], r["implied_prob_mid"])
    print(f"... {len(rows)} markets total")


def cmd_kalshi_epl(_args):
    rows = snapshot_epl_moneylines()
    for r in rows[:20]:
        print(r["event_ticker"], r["selection"], r["implied_prob_mid"])
    print(f"... {len(rows)} markets total")


def cmd_ledger_summary(_args):
    print(json.dumps(summarize(), indent=2, default=str))


def main():
    parser = argparse.ArgumentParser(prog="sportsedge")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("ingest-nfl")
    p.add_argument("--seasons", nargs="+", type=int, required=True)
    p.set_defaults(func=cmd_ingest_nfl)

    p = sub.add_parser("ingest-soccer")
    p.add_argument("--league", default="E0")
    p.add_argument("--seasons", nargs="+", required=True)
    p.set_defaults(func=cmd_ingest_soccer)

    p = sub.add_parser("backtest-nfl")
    p.add_argument("--seasons", nargs="+", type=int, required=True)
    p.add_argument("--edge-threshold", type=float, default=3.0, help="percent")
    p.add_argument("--mov", action="store_true", help="use margin-of-victory K scaling")
    p.set_defaults(func=cmd_backtest_nfl)

    p = sub.add_parser("backtest-soccer")
    p.add_argument("--league", default="E0")
    p.add_argument("--seasons", nargs="+", required=True)
    p.add_argument("--edge-threshold", type=float, default=3.0, help="percent")
    p.set_defaults(func=cmd_backtest_soccer)

    p = sub.add_parser("kalshi-nfl")
    p.set_defaults(func=cmd_kalshi_nfl)

    p = sub.add_parser("kalshi-epl")
    p.set_defaults(func=cmd_kalshi_epl)

    p = sub.add_parser("ledger-summary")
    p.set_defaults(func=cmd_ledger_summary)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
