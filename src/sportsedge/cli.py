"""Command-line entry points.

    python -m sportsedge.cli refresh-history          # rebuild durable game tables
    python -m sportsedge.cli spread-report            # what crossing the spread costs today
    python -m sportsedge.cli ingest-nfl --seasons 2023 2024
    python -m sportsedge.cli ingest-soccer --league E0 --seasons 2324 2425
    python -m sportsedge.cli backtest-nfl       # canonical window 2018-2024
    python -m sportsedge.cli backtest-soccer    # canonical window 1920-2425
                                                # (both default to
                                                #  backtest.benchmarks; pass
                                                #  --seasons only to ask a
                                                #  different question, and say
                                                #  which window you used)
    python -m sportsedge.cli sweep-nfl                # parameter grid vs the closing line
    python -m sportsedge.cli selection-audit          # is the model wrong, or the bet rule?
    python -m sportsedge.cli venue-report             # what trading on Kalshi instead costs
    python -m sportsedge.cli kalshi-nfl
    python -m sportsedge.cli kalshi-epl
    python -m sportsedge.cli snapshot-odds            # capture + persist live odds
    python -m sportsedge.cli recommend --sport nfl    # model vs market -> ledger
    python -m sportsedge.cli settle                   # resolve bets + fill CLV
                                                      # (also recovers CLV on
                                                      #  rows settled before the
                                                      #  stats source caught up)
    python -m sportsedge.cli espn-audit               # ESPN vs the primary stats source
    python -m sportsedge.cli verify-settlements       # cross-check Kalshi vs stats
                                                      #  (primary + ESPN gap-fill)
    python -m sportsedge.cli line-movement            # price drift by time-to-kickoff
    python -m sportsedge.cli fill-quality             # does the liquidity gate
                                                      #  reject quotes that move
                                                      #  against you?
    python -m sportsedge.cli edge-decay               # does a claimed edge
                                                      #  survive to kickoff?
    python -m sportsedge.cli scorecard                 # model vs market vs reality
    python -m sportsedge.cli discrimination-report     # calibration, or ranking?
    python -m sportsedge.cli context-report            # does non-Elo info rank better?
    python -m sportsedge.cli ledger-summary
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from datetime import timedelta

import pandas as pd

from sportsedge import config
from sportsedge.storage import db, snapshots
from sportsedge.ingest.nfl_stats import fetch_nfl_games
from sportsedge.ingest.soccer_stats import fetch_soccer_games
from sportsedge.ingest.kalshi import snapshot_moneylines, snapshot_nfl_moneylines, snapshot_epl_moneylines
from sportsedge.ingest import espn
from sportsedge.ingest import kickoff as kickoff_mod
from sportsedge.ingest import sources
from sportsedge.models.elo import NflEloModel, SoccerEloModel
from sportsedge.models.live import build_nfl_model, build_soccer_model
from sportsedge.backtest.engine import backtest_nfl, backtest_soccer
from sportsedge.backtest import (sweep, selection, kalshi_engine, benchmarks,
                                 discrimination, context)
from sportsedge.models import features
from sportsedge.betting import liquidity, recommend as recommend_mod, settle as settle_mod
from sportsedge.betting import ledger as ledger_mod
from sportsedge.betting import scorecard
from sportsedge.betting import line_movement
from sportsedge.betting import fill_quality
from sportsedge.betting import edge_decay
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


def _warn(msg: str) -> None:
    """Warnings go to stderr, not stdout.

    Several commands print nothing but a JSON document, and a `[warn]` line on
    stdout makes that document unparseable by anything downstream. The EPL
    source outage of 2026-09-17 put one in front of every `edge-decay` and
    `verify-settlements` run.
    """
    print(msg, file=sys.stderr)


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
        _warn(f"[warn] no rows for seasons: {sorted(missing)}")
    if filtered.empty:
        raise SystemExit(f"No games for seasons {sorted(wanted)} in {table}")
    return filtered


def cmd_refresh_history(args):
    """Rebuild the durable historical game tables from the free upstream sources.

    Every upstream step is independently fault-tolerant, and the command still
    exits non-zero if any of them failed. Before 2026-09-17 the two primary
    fetches ran bare: football-data.co.uk started redirecting every request to
    `http://127.0.0.1/`, `fetch_soccer_games` raised, and the ESPN refresh and
    SQLite rebuild that follow it never ran. One dead source took down the
    refresh of three live ones, and the fix for that is not to trust the dead
    source less but to stop letting it speak for the others.
    """
    failures = []

    def _refresh(label, table, fetch, *fetch_args):
        """Fetch and write one table; on failure keep whatever is committed."""
        try:
            df = fetch(*fetch_args)
        except Exception as exc:  # noqa: BLE001 -- a dead source is data, not a crash
            failures.append(f"{label}: {type(exc).__name__}: {exc}")
            _warn(f"[warn] {label} refresh failed ({exc}); keeping existing table")
            try:
                return snapshots.read_processed(table)
            except FileNotFoundError:
                _warn(f"[warn] and no committed {table} to fall back to")
                return None
        path, n = snapshots.write_processed(table, df)
        played = int(df["home_score"].notna().sum())
        print(f"{table} -> {path} ({n} rows, {played} played)")
        return df

    nfl = _refresh("nflverse", "nfl_games", fetch_nfl_games, args.nfl_seasons)
    epl = _refresh("football-data.co.uk", "epl_games",
                   fetch_soccer_games, "E0", args.epl_seasons)

    # ESPN schedules/results. Deliberately written to their OWN tables and
    # never merged into the two above: those carry the closing odds the model
    # trains on, ESPN carries none, and a merge would leave a table whose odds
    # columns are populated for some rows and empty for others for reasons
    # that have nothing to do with the market. See ingest/espn.py.
    # `--espn-end` defaults to three weeks AHEAD, not to `--espn-start`.
    #
    # Two separate reasons, both learned here rather than designed in:
    #  * ESPN's `dates` takes a single day OR a range, so passing the start
    #    alone is a valid request for exactly one day -- which returned 0 rows,
    #    wrote an empty table, and printed a success line while doing it.
    #  * Ending at *today* covers results but not fixtures, and the schedule is
    #    wanted for both. Without future rows the in-play gate falls back to
    #    `expiration - largest observed lag` for every upcoming game
    #    (recommend._gate_kickoff), which is deliberately conservative but is
    #    still an inference where a published kickoff exists. Three weeks
    #    comfortably covers the furthest contract currently on either board.
    espn_end = args.espn_end or (
        kickoff_mod.utcnow() + timedelta(days=21)).strftime("%Y-%m-%d")
    for sport, table in (("nfl", "espn_nfl_games"), ("soccer", "espn_epl_games")):
        try:
            games = espn.fetch_espn_games(sport, args.espn_start, espn_end)
        except Exception as exc:  # a cross-check source must never break refresh
            _warn(f"[warn] ESPN {sport} refresh failed ({exc}); keeping existing table")
            continue
        if games.empty:
            # Never let an empty fetch overwrite a populated table. An upstream
            # hiccup should look like a warning, not like a league with no
            # fixtures -- the second is indistinguishable from "nothing to
            # verify" at every downstream call site.
            _warn(f"[warn] ESPN {sport} returned 0 games for "
                  f"{args.espn_start}..{espn_end}; keeping existing table")
            continue
        path, n = snapshots.write_processed(table, games)
        played = int(games["home_score"].notna().sum())
        print(f"{table} -> {path} ({n} rows total, {len(games)} fetched, {played} played)")

    db.init_db()
    with db.get_conn() as conn:
        for df in (nfl, epl):
            if df is not None:
                db.upsert_games(conn, df.where(df.notna(), None).to_dict("records"))
    print("SQLite cache rebuilt from the committed tables.")
    kickoff_mod.clear_cache()

    # Loud at the end, after everything that COULD be refreshed has been. A
    # partial refresh that exits 0 is the failure mode this whole function was
    # rewritten to avoid: the tables on disk look fine and nobody is told that
    # one of them is yesterday's.
    if failures:
        raise SystemExit("refresh incomplete -- kept the committed table for:\n  "
                         + "\n  ".join(failures))


def cmd_espn_audit(args):
    """Measure ESPN's agreement with the source we already hold.

    CLAUDE.md requires a new source be "verified against something we already
    hold before any number derived from it is published". This is that check,
    kept as a command so it re-runs every time rather than once.
    """
    out = {}
    for sport, table in (("nfl", "nfl_games"), ("soccer", "epl_games")):
        if sport not in args.sports:
            continue
        end = args.end or kickoff_mod.utcnow().strftime("%Y-%m-%d")
        games = espn.fetch_espn_games(sport, args.start, end)
        out[sport] = espn.audit_against_primary(games, snapshots.read_processed(table))
    print(json.dumps(out, indent=2, default=str))


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


def cmd_selection_audit(args):
    """Is the model wrong, or is the betting rule picking out its errors?

    Prints, per sport: calibration on the sides the rule bets vs the sides it
    passes, then the blend sweep against the de-vigged closing line.
    """
    for sport in args.sports:
        sides = selection.nfl_sides() if sport == "nfl" else selection.epl_sides()
        audit = selection.selection_audit(sides)
        print(f"\n{'=' * 68}\n{sport.upper()}  --  {audit['n_sides']} priced sides, "
              f"{audit['n_flagged']} flagged ({audit['flagged_rate_pct']:.1f}%)\n{'=' * 68}")

        print(f"\n{'model prob':>12} {'n':>6} {'claimed':>9} {'actual':>9} {'gap':>8}   (all sides)")
        for r in audit["all"]["by_bucket"]:
            print(f"{r['bucket']:>12} {r['n']:6d} {r['claimed']:9.3f} {r['actual']:9.3f} {r['gap']:+8.3f}")

        for label in ("flagged", "passed"):
            sub = audit[label]
            if not sub.get("n"):
                continue
            print(f"\n{'model prob':>12} {'n':>6} {'claimed':>9} {'actual':>9} {'gap':>8}   ({label})")
            for r in sub["by_bucket"]:
                print(f"{r['bucket']:>12} {r['n']:6d} {r['claimed']:9.3f} {r['actual']:9.3f} {r['gap']:+8.3f}")
            print(f"{'OVERALL':>12} {sub['n']:6d} {sub['claimed']:9.3f} {sub['actual']:9.3f} {sub['gap']:+8.3f}")

        print(f"\nselection gap (flagged minus passed): {audit['selection_gap']:+.3f}")
        print("  negative => the rule bets the sides the model gets wrong (winner's curse)")

        blend = selection.blend_sweep(sides)
        print(f"\n{'w':>6} {'log-loss':>10} {'vs mkt':>9} {'n_bets':>7} {'ROI':>9} {'95% CI':>20}")
        for r in blend.itertuples():
            roi = f"{r.roi_pct:+8.2f}%" if r.roi_pct is not None else f"{'--':>9}"
            ci = (f"[{r.roi_ci_lo:+6.1f},{r.roi_ci_hi:+6.1f}]"
                  if r.roi_ci_lo is not None else "")
            print(f"{r.w:6.2f} {r.log_loss:10.4f} {r.vs_market:+9.4f} {r.n_bets:7d} {roi} {ci:>20}")
        print("\n" + json.dumps(selection.summarize_blend(blend, sides), indent=2, default=float))


def cmd_venue_report(args):
    """Every ROI this project has published is model-vs-sportsbook. We would
    trade on Kalshi. This reports what that substitution costs.

    Read the header before the table: the exchange numbers are SIMULATED --
    Kalshi's public API serves the current board, not a price history, so a
    real exchange backtest of 2018-2024 does not exist. What is real here is
    the venue's microstructure, measured from the captured snapshots, and the
    agreement check that licenses substituting it into the historical sample.
    """
    print(json.dumps(kalshi_engine.summarize("nfl"), indent=2, default=float))

    nfl = _load_games("nfl_games", args.nfl_seasons, _nfl_season_labels,
                      fetch_nfl_games, args.nfl_seasons)
    epl = _load_games("epl_games", args.epl_seasons, _epl_season_labels,
                      fetch_soccer_games, "E0", args.epl_seasons)

    jobs = (
        ("NFL", "nfl", lambda g, **kw: backtest_nfl(g, NflEloModel(), **kw), nfl),
        ("EPL", "soccer", lambda g, **kw: backtest_soccer(g, SoccerEloModel(), **kw), epl),
    )
    for label, sport, fn, games in jobs:
        res = kalshi_engine.compare_venues(fn, games, sport=sport,
                                           edge_threshold=args.edge_threshold / 100)
        print(f"\n{'=' * 72}\n{label}  --  half-spread {res['half_spread']:.4f}, "
              f"fee {res['fee_rate']:.3f} "
              f"({'verified' if res['fee_rate_verified'] else 'UNVERIFIED'}), "
              f"log-loss {res['log_loss']:.4f}\n"
              f"{'=' * 72}")
        print(f"{'venue':<20} {'n':>6} {'win%':>7} {'ROI':>9} {'95% CI':>20} {'sig':>5}")
        for name, key in (("sportsbook (real)", "sportsbook"),
                          ("kalshi (SIMULATED)", "kalshi_simulated")):
            r = res[key]
            ci = (f"[{r['roi_ci95_pct'][0]:+6.1f},{r['roi_ci95_pct'][1]:+6.1f}]"
                  if r["roi_ci95_pct"] else "")
            print(f"{name:<20} {r['n_bets']:6d} {r['win_rate']:7.2f} "
                  f"{r['roi_pct']:+8.2f}% {ci:>20} {str(r['significant_at_95']):>5}")
        print(f"{'delta':<20} {res['bets_delta']:+6d} {'':>7} {res['roi_delta_pp']:+8.2f}pp")

        print(f"\nfee sensitivity -- the coefficient is verified at "
              f"{kalshi_engine.DEFAULT_FEE_RATE:.2f}, so the matching row is the real "
              f"one; the rest show how much the conclusion leans on it:")
        fs = kalshi_engine.fee_sensitivity(fn, games, sport=sport,
                                           edge_threshold=args.edge_threshold / 100)
        print(fs.to_string(index=False))


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


def _rating_games(sport: str):
    """Rating-season games plus a provenance dict saying where they came from.

    Used by `recommend` and by `verify-settlements`, which is to say by every
    path that prices or checks a LIVE board. It fetches upstream and falls back
    to the committed table only when upstream is down -- and the fallback is
    gated on ESPN reporting no played game the table is missing, so a league
    whose results have actually moved on cannot be priced from a stale rating
    set. See ingest/sources.py for why that gate is a game count and not a
    timestamp.
    """
    key = SPORT_TO_LEAGUE_KEY[sport]
    league_cfg = config.league(key)
    seasons = league_cfg["rating_seasons"]
    if sport == "nfl":
        return sources.load_games(sport, [int(s) for s in seasons], _nfl_season_labels,
                                  fetch_nfl_games, [int(s) for s in seasons])
    codes = [str(s) for s in seasons]
    return sources.load_games(sport, codes, _epl_season_labels, fetch_soccer_games,
                              league_cfg["league_code"], codes)


def _load_games_for(sport: str):
    """Back-compat wrapper: games only, raising if they cannot be trusted."""
    games, prov = _rating_games(sport)
    if not prov["usable"]:
        raise SystemExit(sources.describe(prov))
    if prov["degraded"]:
        _warn(f"[warn] {sources.describe(prov)}")
    return games


def cmd_recommend(args):
    cfg = config.load()
    threshold = (args.edge_threshold if args.edge_threshold is not None
                 else cfg["edge_threshold_pct"]) / 100
    kelly_mult = cfg["kelly_multiplier"]
    stake = cfg.get("flat_stake", 1.0)

    out = {}
    for sport in args.sports:
        key = SPORT_TO_LEAGUE_KEY[sport]
        games, prov = _rating_games(sport)
        if prov["degraded"]:
            _warn(f"[warn] {sources.describe(prov)}")
        if not prov["usable"]:
            # Capture the board anyway -- odds are irreplaceable and the model
            # is not involved in capturing them -- then decline to price it.
            # A price from rating data that is behind the league is worse than
            # no price, because it is indistinguishable from a real one.
            snapshots.append_snapshot(snapshot_moneylines(sport), sport=sport)
            out[sport] = {"skipped": "rating data not usable",
                          "provenance": prov, "logged": 0}
            continue
        rows = snapshot_moneylines(sport)
        snapshots.append_snapshot(rows, sport=sport)

        # Recommend only on quotes that pass the liquidity gate. This was
        # missing: partition() was applied in snapshot-odds but not here, so
        # the recommender priced against the raw board and could log a bet on
        # a quote the project's own filter rejects -- exactly the "fake edge
        # against a price nobody is offering" that liquidity.py exists to stop.
        rows, rejected = liquidity.partition(rows, **config.liquidity_kwargs())

        # Drop contracts whose game is already under way. The models here are
        # pre-game models, so against an in-play quote the gap between model
        # and market measures how far behind the model is, not an edge -- and
        # it lands on whichever side is currently losing. Counted separately
        # so a gated board is visible in the summary rather than silent.
        rows, in_play = recommend_mod.partition_in_play(sport, rows)

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
                    edge_after_fee_pct=r.get("edge_after_fee_pct"),
                    fee_assumption=r.get("fee_assumption"),
                    notes="" if live else "model not cleared by backtest; shadow only",
                )
                logged += 1

        out[sport] = {
            "contracts": len(rows),
            "illiquid_skipped": len(rejected), "in_play_skipped": len(in_play),
            "recommendations": len(recs),
            "mode": mode, "live_enabled": live,
            "logged": logged, "skipped_duplicate": skipped,
            "flagged_rate_pct": round(100 * len(recs) / max(1, len(rows)), 1),
            "provenance": prov,
        }
        for r in sorted(recs, key=lambda x: -x["edge_pct"])[:args.top]:
            after = r.get("edge_after_fee_pct")
            after_s = "    n/a" if after is None else f"{after:+6.1f}%"
            print(f"  [{mode}] {r['matchup']:<34} {r['selection']:<5} "
                  f"model={r['model_prob']:.3f} fair={r['market_fair_prob']:.3f} "
                  f"ask={r['price_ask']:.2f} edge={r['edge_pct']:+6.1f}% "
                  f"after-fee={after_s}")

    # Retire whatever this run's pricing version has replaced. Unconditional,
    # and after logging rather than before, so a version bump can never again
    # leave both halves of a re-priced wager open at once.
    sup = ledger_mod.void_superseded_rows(
        recommend_mod.PRICING_VERSIONS, dry_run=args.dry_run)
    out["superseded_voided"] = {k: sup[k] for k in ("voided", "groups", "unorderable")}
    print(json.dumps(out, indent=2, default=str))


def cmd_settle(args):
    res = settle_mod.settle_pending(dry_run=args.dry_run)
    print(json.dumps(res, indent=2, default=str))

    # Always follow settlement with the recovery pass. EPL contracts finalize
    # on Kalshi hours-to-days before football-data.co.uk publishes the match,
    # so a bet settled by the run above routinely cannot have a CLV yet; this
    # is what goes back for it once the stats source catches up. Running it
    # unconditionally is the point -- a recovery pass someone has to remember
    # to invoke is how the number goes missing in the first place.
    if not args.no_backfill:
        back = settle_mod.backfill_clv(dry_run=args.dry_run)
        print("\n-- CLV backfill (settled rows that had none) --")
        print(json.dumps(back, indent=2, default=str))


def _verification_games(sport: str):
    """Primary results, extended with ESPN's for fixtures the primary lacks.

    Without this the cross-check simply reports `unmatched_games` for anything
    football-data.co.uk has not published yet -- which is precisely the cohort
    most in need of checking, since those are the bets that just settled. A
    settlement nobody could cross-check was counted as "verified 90/90" while
    the 7 rows that actually mattered sat in the unmatched pile.

    Primary rows win; ESPN only fills gaps, so the existing verification is
    bit-for-bit unchanged on every game the primary already had.
    """
    games = _load_games_for(sport)
    try:
        extra = snapshots.read_processed(
            {"nfl": "espn_nfl_games", "soccer": "espn_epl_games"}[sport])
    except (FileNotFoundError, KeyError):
        return games

    played = games.dropna(subset=["home_score", "away_score"])
    have = {(str(g["game_date"])[:10], g["home_team"], g["away_team"])
            for _, g in played.iterrows()}
    extra = extra.dropna(subset=["home_score", "away_score"])
    keep = [i for i, r in extra.iterrows()
            if (str(r["game_date"])[:10], r["home_team"], r["away_team"]) not in have]
    if not keep:
        return games
    return pd.concat([games, extra.loc[keep]], ignore_index=True)


def cmd_verify_settlements(args):
    out = {}
    for sport in args.sports:
        games = _verification_games(sport) if args.cross_source else _load_games_for(sport)
        r = settle_mod.verify_against_stats(games, sport)
        r["source"] = "primary+espn" if args.cross_source else "primary"
        out[sport] = r
    print(json.dumps(out, indent=2, default=str))


def cmd_line_movement(args):
    """How much the line moves as kickoff approaches, per time-to-kickoff bucket."""
    out = {sp: line_movement.summarize(sp) for sp in args.sports}
    print(json.dumps(out, indent=2, default=str))


def cmd_fill_quality(args):
    """Does a liquidity-gate rejection predict a quote that moves against you?"""
    out = {sp: fill_quality.summarize(sp) for sp in args.sports}
    print(json.dumps(out, indent=2, default=str))


def cmd_edge_decay(args):
    """Does a claimed edge survive the walk to kickoff, once the book is open?"""
    out = {}
    for sport in args.sports:
        games, prov = _rating_games(sport)
        if prov["degraded"]:
            _warn(f"[warn] {sources.describe(prov)}")
        if not prov["usable"]:
            out[sport] = {"skipped": "rating data not usable", "provenance": prov}
            continue
        out[sport] = edge_decay.summarize(sport, games=games,
                                          min_span_hours=args.min_span_hours)
        out[sport]["provenance"] = prov
    print(json.dumps(out, indent=2, default=str))


def cmd_ledger_summary(_args):
    print(json.dumps(summarize(), indent=2, default=str))


def cmd_discrimination_report(args):
    """Calibration or discrimination? Bounds every recalibration-shaped change."""
    out = {}
    if "nfl" in args.sports:
        games = _load_games("nfl_games", benchmarks.NFL_SEASONS, _nfl_season_labels,
                            fetch_nfl_games, list(benchmarks.NFL_SEASONS))
        res = backtest_nfl(games, NflEloModel())
        out["nfl"] = discrimination.discrimination_report(res["predictions"])
    if "soccer" in args.sports:
        games = _load_games("epl_games", benchmarks.EPL_SEASONS, _epl_season_labels,
                            fetch_soccer_games, "E0", list(benchmarks.EPL_SEASONS))
        res = backtest_soccer(games, SoccerEloModel())
        out["soccer"] = discrimination.discrimination_report(res["predictions"])
    print(json.dumps(out, indent=2, default=str))


def cmd_context_report(args):
    """Does information Elo cannot see rank games better than Elo can?

    NFL only: nflverse ships rest/venue/weather/QB per game and
    football-data.co.uk ships none of it, so there is no soccer leg to run.
    """
    games = _load_games("nfl_games", benchmarks.NFL_SEASONS, _nfl_season_labels,
                        fetch_nfl_games, list(benchmarks.NFL_SEASONS))
    out = context.context_report(games, tiers=tuple(args.tiers),
                                 edge_threshold=args.edge_threshold / 100,
                                 min_train_games=args.min_train_games)

    if args.sweep_regularization:
        out["regularization_sweep"] = context.regularization_sweep(
            games, edge_threshold=args.edge_threshold / 100,
            min_train_games=args.min_train_games)

    print(json.dumps(out, indent=2, default=str))

    if not out["control_ok"]:
        raise SystemExit(
            "CONTROL FAILED: a logistic on elo_diff alone must reproduce baseline "
            f"Elo's AUC exactly, and it differs by {out['control_auc_delta']!r}. "
            "Every other number in this report is void until that is explained.")


def cmd_scorecard(args):
    print(json.dumps(scorecard.summarize(tuple(args.sports)), indent=2, default=str))


def build_parser():
    parser = argparse.ArgumentParser(prog="sportsedge")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("refresh-history")
    p.add_argument("--espn-start", default="2026-08-01")
    p.add_argument("--espn-end", default=None)
    p.add_argument("--nfl-seasons", nargs="+", type=int, default=list(range(2018, 2027)))
    p.add_argument("--epl-seasons", nargs="+",
                   default=["1920", "2021", "2122", "2223", "2324", "2425", "2526", "2627"])
    p.set_defaults(func=cmd_refresh_history)

    p = sub.add_parser("selection-audit")
    p.add_argument("--sports", nargs="+", default=["nfl", "soccer"])
    p.set_defaults(func=cmd_selection_audit)

    p = sub.add_parser("venue-report", help="model vs market at Kalshi, not a sportsbook")
    p.add_argument("--nfl-seasons", nargs="+", type=int, default=list(range(2018, 2025)))
    p.add_argument("--epl-seasons", nargs="+",
                   default=["1920", "2021", "2122", "2223", "2324", "2425", "2526"])
    p.add_argument("--edge-threshold", type=float, default=3.0, help="percent")
    p.set_defaults(func=cmd_venue_report)

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
    p.add_argument("--seasons", nargs="+", type=int,
                   default=list(benchmarks.NFL_SEASONS),
                   help="default is the canonical regression window "
                        f"{benchmarks.NFL_SEASONS[0]}-{benchmarks.NFL_SEASONS[-1]}; "
                        "a different window gives a different number, not a regression")
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
    p.add_argument("--league", default=benchmarks.EPL_LEAGUE)
    p.add_argument("--seasons", nargs="+", default=list(benchmarks.EPL_SEASONS),
                   help="default is the canonical regression window "
                        f"{benchmarks.EPL_SEASONS[0]}-{benchmarks.EPL_SEASONS[-1]}; "
                        "holdout ROI swings ~9 points on this choice alone")
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
    p.add_argument("--no-backfill", action="store_true",
                   help="skip the CLV recovery pass over already-settled rows")
    p.set_defaults(func=cmd_settle)

    p = sub.add_parser("espn-audit",
                       help="measure ESPN's agreement with the primary stats source")
    p.add_argument("--sports", nargs="+", default=["nfl", "soccer"])
    p.add_argument("--start", default="2026-08-01")
    p.add_argument("--end", default=None)
    p.set_defaults(func=cmd_espn_audit)

    p = sub.add_parser("verify-settlements")
    p.add_argument("--no-cross-source", dest="cross_source", action="store_false",
                   help="check against the primary stats source only")
    p.add_argument("--sports", nargs="+", default=["nfl", "soccer"])
    p.set_defaults(func=cmd_verify_settlements)

    p = sub.add_parser("line-movement",
                       help="price drift by time-to-kickoff (is a T-8h CLV cut stale?)")
    p.add_argument("--sports", nargs="+", default=["nfl", "soccer"])
    p.set_defaults(func=cmd_line_movement)

    p = sub.add_parser("fill-quality",
                       help="does the liquidity gate reject quotes that move against you?")
    p.add_argument("--sports", nargs="+", default=["nfl", "soccer"])
    p.set_defaults(func=cmd_fill_quality)

    p = sub.add_parser("scorecard",
                       help="settled bets vs what the model AND the market expected")
    p.add_argument("--sports", nargs="+", default=["nfl", "soccer"])
    p.set_defaults(func=cmd_scorecard)

    p = sub.add_parser("discrimination-report",
                       help="can recalibration fix the model, or is it the ranking?")
    p.add_argument("--sports", nargs="+", default=["nfl", "soccer"])
    p.set_defaults(func=cmd_discrimination_report)

    p = sub.add_parser("context-report",
                       help="does rest/venue/weather/QB rank better than Elo alone?")
    p.add_argument("--tiers", nargs="+", default=list(features.TIERS))
    p.add_argument("--edge-threshold", type=float, default=3.0, help="percent")
    p.add_argument("--min-train-games", type=int, default=400)
    p.add_argument("--sweep-regularization", action="store_true",
                   help="is the degradation overfitting? sweep the L2 penalty")
    p.set_defaults(func=cmd_context_report)

    p = sub.add_parser("edge-decay",
                       help="does a claimed edge survive to kickoff, or is it "
                            "an un-opened book?")
    p.add_argument("--sports", nargs="+", default=["nfl", "soccer"])
    p.add_argument("--min-span-hours", type=float, default=edge_decay.MIN_SPAN_HOURS)
    p.set_defaults(func=cmd_edge_decay)

    p = sub.add_parser("ledger-summary")
    p.set_defaults(func=cmd_ledger_summary)

    return parser


def main():
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
