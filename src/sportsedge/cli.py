"""Command-line entry points.

    python -m sportsedge.cli refresh-history          # rebuild durable game tables
    python -m sportsedge.cli spread-report            # what crossing the spread costs today
    python -m sportsedge.cli ingest-nfl --seasons 2023 2024
    python -m sportsedge.cli ingest-soccer --league E0 --seasons 2324 2425
    python -m sportsedge.cli backtest-nfl --seasons 2020 2021 2022 2023 2024
    python -m sportsedge.cli backtest-soccer --league E0 --seasons 2223 2324 2425
    python -m sportsedge.cli sweep-nfl                # parameter grid vs the closing line
    python -m sportsedge.cli kalshi-nfl
    python -m sportsedge.cli kalshi-epl
    python -m sportsedge.cli snapshot-odds            # capture + persist live odds
    python -m sportsedge.cli recommend --sport nfl    # model vs market -> ledger
    python -m sportsedge.cli settle                   # resolve bets + fill CLV
    python -m sportsedge.cli verify-settlements       # cross-check Kalshi vs stats
    python -m sportsedge.cli ledger-summary
"""
from __future__ import annotations

import argparse
import json
import statistics

from sportsedge import config
from sportsedge.storage import db, snapshots
from sportsedge.ingest.nfl_stats import fetch_nfl_games
from sportsedge.ingest.soccer_stats import fetch_soccer_games
from sportsedge.ingest.kalshi import snapshot_moneylines, snapshot_nfl_moneylines, snapshot_epl_moneylines
from sportsedge.models.elo import NflEloModel, SoccerEloModel
from sportsedge.models.live import build_nfl_model, build_soccer_model
from sportsedge.backtest.engine import backtest_nfl, backtest_soccer
from sportsedge.backtest import sweep
from sportsedge.betting import liquidity, recommend as recommend_mod, settle as settle_mod
from sportsedge.betting import ledger as ledger_mod
from sportsedge.betting.ledger import summarize

SPORT_TO_LEAGUE_KEY = {"nfl": "nfl", "soccer": "epl"}


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


def _nfl_season_labels(seasons):
    return {str(s) for s in seasons}


def _epl_season_labels(seasons):
    """'2526' -> '2025-26', matching the label fetch_soccer_games writes."""
    return {f"20{str(s)[:2]}-{str(s)[2:]}" for s in seasons}


def _load_games(table, seasons, label_fn, fetch, *fetch_args):
    """Prefer the committed table; fall back to a live fetch if it is absent.

    The season filter is applied AFTER loading. The committed table holds every
    season ever ingested, so reading it unfiltered silently ignores --seasons
    and hands the backtest a different sample than the one requested -- which
    in practice meant holding out the 30-game in-progress season instead of a
    completed 380-game one, and reporting the result as if it meant something.
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
    """Rebuild the durable historical game tables from the free upstream sources."""
    nfl = fetch_nfl_games(args.nfl_seasons)
    path, n = snapshots.write_processed("nfl_games", nfl)
    print(f"nfl_games -> {path} ({n} rows, {int(nfl['home_score'].notna().sum())} played)")

    epl = fetch_soccer_games("E0", args.epl_seasons)
    path, n = snapshots.write_processed("epl_games", epl)
    print(f"epl_games -> {path} ({n} rows)")

    db.init_db()
    with db.get_conn() as conn:
        db.upsert_games(conn, nfl.where(nfl.notna(), None).to_dict("records"))
        db.upsert_games(conn, epl.where(epl.notna(), None).to_dict("records"))
    print("SQLite cache rebuilt from the committed tables.")


def cmd_sweep_nfl(args):
    """Sweep the NFL Elo grid and report it against the de-vigged closing line."""
    grid = sweep.sweep_nfl(seasons=tuple(args.seasons),
                           test_seasons=tuple(args.test_seasons),
                           edge_threshold=args.edge_threshold / 100)
    summary = sweep.summarize_sweep(grid)
    print(json.dumps(summary, indent=2, default=float))

    cols = ["k", "home_advantage", "use_mov", "calibrate", "log_loss",
            "n_bets", "roi_pct", "roi_ci_lo", "roi_ci_hi", "roi_significant"]
    print("\n-- best 10 by log-loss --")
    print(grid.head(10)[cols].to_string(index=False))

    if args.out:
        grid.to_csv(args.out, index=False)
        print(f"\nfull grid -> {args.out}")


def cmd_spread_report(_args):
    """How much of the edge threshold today's bid-ask spreads eat, per venue."""
    for label, rows in (("NFL", snapshot_nfl_moneylines()), ("EPL", snapshot_epl_moneylines())):
        costs = []
        for r in rows:
            bid, ask = r.get("yes_bid"), r.get("yes_ask")
            if bid and ask and bid > 0 and ask > bid:
                costs.append((ask / ((bid + ask) / 2) - 1) * 100)
        if not costs:
            print(f"{label}: no two-sided quotes")
            continue
        costs.sort()
        over = sum(1 for c in costs if c >= 3.0)
        print(f"{label}: n={len(costs)} median={statistics.median(costs):.2f}% "
              f"p75={costs[int(len(costs) * 0.75)]:.2f}% max={costs[-1]:.2f}% "
              f"| >=3.0% (the whole edge threshold): {over}/{len(costs)}")


def cmd_backtest_nfl(args):
    games = _load_games("nfl_games", args.seasons, _nfl_season_labels,
                        fetch_nfl_games, args.seasons)
    model = NflEloModel(use_mov_multiplier=args.mov)
    result = backtest_nfl(games, model, edge_threshold=args.edge_threshold / 100)
    print(json.dumps({k: v for k, v in result.items() if k != "bets"}, indent=2, default=str))
    print(f"Bets flagged: {len(result['bets'])}")


def cmd_backtest_soccer(args):
    games = _load_games("epl_games", args.seasons, _epl_season_labels,
                        fetch_soccer_games, args.league, args.seasons)
    model = SoccerEloModel()
    result = backtest_soccer(games, model, edge_threshold=args.edge_threshold / 100)
    print(json.dumps({k: v for k, v in result.items() if k != "bets"}, indent=2, default=str))
    print(f"Bets flagged: {len(result['bets'])}")


def cmd_kalshi_nfl(_args):
    _print_snapshot(snapshot_nfl_moneylines())


def cmd_kalshi_epl(_args):
    _print_snapshot(snapshot_epl_moneylines())


def _print_snapshot(rows):
    for r in rows[:20]:
        print(f"{r['away_team']} @ {r['home_team']:<16} {r['selection']:<5} "
              f"mid={r['implied_prob_mid']} spread={r['spread']}")
    print(f"... {len(rows)} contracts total")


def cmd_snapshot_odds(args):
    """Capture live odds to the committed snapshot store.

    This is the job that must run often: odds are not reconstructable after the
    fact, so a missed window is permanently missing data.
    """
    total = {}
    for sport in args.sports:
        rows = snapshot_moneylines(sport)
        keep, drop = liquidity.partition(rows, **config.liquidity_kwargs())
        res = snapshots.append_snapshot(rows, sport=sport)
        total[sport] = {"contracts": len(rows), "fillable": len(keep),
                        "rejected": len(drop), **res}
    print(json.dumps(total, indent=2, default=str))


def _load_games_for(sport: str):
    key = SPORT_TO_LEAGUE_KEY[sport]
    league_cfg = config.league(key)
    seasons = league_cfg["rating_seasons"]
    if sport == "nfl":
        return fetch_nfl_games([int(s) for s in seasons])
    return fetch_soccer_games(league_cfg["league_code"], [str(s) for s in seasons])


def cmd_recommend(args):
    cfg = config.load()
    threshold = (args.edge_threshold if args.edge_threshold is not None
                 else cfg["edge_threshold_pct"]) / 100
    kelly_mult = cfg["kelly_multiplier"]
    stake = cfg.get("flat_stake", 1.0)

    out = {}
    for sport in args.sports:
        key = SPORT_TO_LEAGUE_KEY[sport]
        games = _load_games_for(sport)
        rows = snapshot_moneylines(sport)
        snapshots.append_snapshot(rows, sport=sport)

        # Recommend only on quotes that pass the liquidity gate. This was
        # missing: partition() was applied in snapshot-odds but not here, so
        # the recommender priced against the raw board and could log a bet on
        # a quote the project's own filter rejects -- exactly the "fake edge
        # against a price nobody is offering" that liquidity.py exists to stop.
        rows, rejected = liquidity.partition(rows, **config.liquidity_kwargs())

        if sport == "nfl":
            model = build_nfl_model(games, use_mov=args.mov)
            recs = recommend_mod.recommend_nfl(
                rows, model, edge_threshold=threshold, kelly_multiplier=kelly_mult)
        else:
            model, calibrator = build_soccer_model(games)
            recs = recommend_mod.recommend_soccer(
                rows, model, calibrator, edge_threshold=threshold, kelly_multiplier=kelly_mult)

        live = config.is_live_enabled(key)
        mode = ledger_mod.LIVE if live else ledger_mod.SHADOW
        logged, skipped = 0, 0
        if not args.dry_run:
            seen = ledger_mod.existing_keys()
            for r in recs:
                if (r["market_ticker"], r["model_version"],
                        r.get("pricing_version")) in seen:
                    skipped += 1
                    continue
                ledger_mod.add_bet(
                    sport=r["sport"], league=r["league"], game_id=r["event_ticker"],
                    matchup=r["matchup"], market=r["market"], selection=r["selection"],
                    model_prob=r["model_prob"], model_version=r["model_version"],
                    market_odds_decimal=r["market_odds_decimal"], book=r["book"],
                    edge_pct=r["edge_pct"], stake=stake,
                    kelly_fraction=r["kelly_fraction"], mode=mode,
                    market_ticker=r["market_ticker"],
                    market_fair_prob=r["market_fair_prob"],
                    expiration_time=r.get("expiration_time"),
                    kickoff_utc=r.get("kickoff_utc"),
                    pricing_version=r.get("pricing_version"),
                    notes="" if live else "model not cleared by backtest; shadow only",
                )
                logged += 1

        out[sport] = {
            "contracts": len(rows),
            "illiquid_skipped": len(rejected), "recommendations": len(recs),
            "mode": mode, "live_enabled": live,
            "logged": logged, "skipped_duplicate": skipped,
            "flagged_rate_pct": round(100 * len(recs) / max(1, len(rows)), 1),
        }
        for r in sorted(recs, key=lambda x: -x["edge_pct"])[:args.top]:
            print(f"  [{mode}] {r['matchup']:<34} {r['selection']:<5} "
                  f"model={r['model_prob']:.3f} fair={r['market_fair_prob']:.3f} "
                  f"ask={r['price_ask']:.2f} edge={r['edge_pct']:+.1f}%")
    print(json.dumps(out, indent=2, default=str))


def cmd_settle(args):
    res = settle_mod.settle_pending(dry_run=args.dry_run)
    print(json.dumps(res, indent=2, default=str))


def cmd_verify_settlements(args):
    out = {}
    for sport in args.sports:
        games = _load_games_for(sport)
        r = settle_mod.verify_against_stats(games, sport)
        out[sport] = r
    print(json.dumps(out, indent=2, default=str))


def cmd_ledger_summary(_args):
    print(json.dumps(summarize(), indent=2, default=str))


def main():
    parser = argparse.ArgumentParser(prog="sportsedge")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("refresh-history")
    p.add_argument("--nfl-seasons", nargs="+", type=int, default=list(range(2018, 2027)))
    p.add_argument("--epl-seasons", nargs="+",
                   default=["1920", "2021", "2122", "2223", "2324", "2425", "2526", "2627"])
    p.set_defaults(func=cmd_refresh_history)

    p = sub.add_parser("spread-report")
    p.set_defaults(func=cmd_spread_report)

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

    p = sub.add_parser("sweep-nfl", help="NFL parameter grid vs the closing line")
    p.add_argument("--seasons", nargs="+", type=int, default=list(sweep.DEFAULT_SEASONS))
    p.add_argument("--test-seasons", nargs="+", type=int,
                   default=list(sweep.DEFAULT_TEST_SEASONS))
    p.add_argument("--edge-threshold", type=float, default=3.0, help="percent")
    p.add_argument("--out", default=None, help="write the full grid to this CSV")
    p.set_defaults(func=cmd_sweep_nfl)

    p = sub.add_parser("backtest-soccer")
    p.add_argument("--league", default="E0")
    p.add_argument("--seasons", nargs="+", required=True)
    p.add_argument("--edge-threshold", type=float, default=3.0, help="percent")
    p.set_defaults(func=cmd_backtest_soccer)

    p = sub.add_parser("kalshi-nfl")
    p.set_defaults(func=cmd_kalshi_nfl)

    p = sub.add_parser("kalshi-epl")
    p.set_defaults(func=cmd_kalshi_epl)

    p = sub.add_parser("snapshot-odds")
    p.add_argument("--sports", nargs="+", default=["nfl", "soccer"])
    p.set_defaults(func=cmd_snapshot_odds)

    p = sub.add_parser("recommend")
    p.add_argument("--sports", nargs="+", default=["nfl", "soccer"])
    p.add_argument("--edge-threshold", type=float, default=None, help="percent")
    p.add_argument("--mov", action="store_true")
    p.add_argument("--dry-run", action="store_true", help="print without writing the ledger")
    p.add_argument("--top", type=int, default=10)
    p.set_defaults(func=cmd_recommend)

    p = sub.add_parser("settle")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_settle)

    p = sub.add_parser("verify-settlements")
    p.add_argument("--sports", nargs="+", default=["nfl", "soccer"])
    p.set_defaults(func=cmd_verify_settlements)

    p = sub.add_parser("ledger-summary")
    p.set_defaults(func=cmd_ledger_summary)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
