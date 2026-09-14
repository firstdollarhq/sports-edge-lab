"""CSV paper-trading bet ledger: bets/ledger.csv. This is the primary
human-readable record of what the model recommended, what the market actually
offered, and what happened -- kept separate from the SQLite DB so it's easy
to open, diff in git, and eyeball for bias."""
from __future__ import annotations

import uuid
from collections.abc import Sequence
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
    # `edge_pct` is computed at the ask and EXCLUDES Kalshi's trading fee,
    # which backtest.kalshi_engine measured as the larger of the two venue
    # costs (~4.7% of stake against the spread's ~1.7%). These two columns
    # record the fee-inclusive edge and the rate assumed for it, so that the
    # overstatement is visible per row instead of being a footnote.
    #
    # They are REPORTED, not enforced: the threshold still tests `edge_pct`.
    # See recommend.FEE_RATE_ASSUMPTION for why, and expect this to change
    # once the week-1 slate settles.
    #
    # Both are None on rows written before 2026-09-12.
    "edge_after_fee_pct",
    "fee_assumption",
    # How many hours before kickoff the quote behind `clv_pct` was captured.
    #
    # CLV is only a skill signal if the reference really is the close. Before
    # the capture cron (2026-09-13) the best reference this project held sat
    # 7-11h out, and run 10 measured what that does: across the 23 settled
    # rows, the 9 with a stale reference average +4.04% CLV with NOT ONE
    # negative reading, while the 14 with a reference inside an hour average
    # -1.41%. The split holds WITHIN the EPL leg as well as between leagues,
    # so it is a property of the reference and not of the sport.
    #
    # Storing the lag is what stops that from having to be rediscovered by
    # hand: `_summarize_frame` reports CLV over the rows where the reference
    # is real, and the stale rows separately, instead of averaging the two
    # into a number that describes neither.
    #
    # None on rows settled before 2026-09-14, and on rows with no CLV at all.
    "clv_reference_lag_h",
]

# A reference captured within this many hours of kickoff counts as a genuine
# closing price. One hour is not arbitrary: `line-movement` measures the mean
# absolute move inside the final two hours at 0.004 (max one cent) across 26
# NFL contracts, so a quote from inside that window and the true close differ
# by less than the tick size.
CLV_REFERENCE_MAX_LAG_H = 1.0

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
            pricing_version: str | None = None,
            edge_after_fee_pct: float | None = None,
            fee_assumption: float | None = None) -> str:
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
        "edge_after_fee_pct": edge_after_fee_pct, "fee_assumption": fee_assumption,
        # Filled at settlement, when there is a closing quote to measure against.
        "clv_reference_lag_h": None,
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

    That key makes a contract eligible for re-pricing after a version bump.
    It does NOT retire the row the bump superseded -- see
    `void_superseded_rows`, which is the other half and was missing until
    2026-09-13.
    """
    df = _load()
    if df.empty or "market_ticker" not in df.columns:
        return set()
    return {
        (r["market_ticker"], r["model_version"], r.get("pricing_version"))
        for _, r in df.iterrows()
        if r.get("market_ticker")
    }


def void_superseded_rows(version_order: "Sequence[str]", *,
                         dry_run: bool = False) -> dict:
    """Void rows that a later `pricing_version` has already re-priced.

    Re-pricing is a REPLACEMENT, and until 2026-09-13 this codebase only ever
    did the insert half of it. `existing_keys` includes `pricing_version`
    precisely so that a bump makes a contract eligible to be logged again --
    but nothing ever retired the row it replaced, so both halves stayed open
    and both were counted.

    The p1 -> p2 bump therefore did not re-price 35 wagers, it duplicated
    them: 75 non-void rows were 40 distinct (contract, selection, model)
    wagers. Every count the project published over that ledger -- "74
    pending", "70 pre-registered bets", n in every confidence interval -- was
    inflated, and the CIs were narrow by a factor of ~sqrt(2) because each
    wager was being counted as two independent trials of itself. Both halves
    of a pair always share an outcome; they are one bet written down twice.

    Which half survives is not a free choice. `pricing_version` asserts that
    the later pipeline is the correct one and the earlier is superseded, so
    the newest version wins and the older is voided. That is the same
    mechanism, and the same direction, as the 28 NFL rows voided by the
    v1 -> v2 model bump on 2026-09-10.

    Settled rows are voided too, deliberately. A settled duplicate is exactly
    where the double-count does its damage -- it lands in win rate and ROI --
    and leaving it in to avoid touching a result would keep the defect in the
    only numbers anyone reads.

    `version_order` is passed in, oldest first, rather than derived by sorting
    the strings: 'p10' sorts before 'p2' and this repo has now been bitten
    seven times by a value that was not the type or order the surrounding code
    assumed. A group containing a version not in that list is left untouched
    and reported under `unorderable` -- guessing at the order is how a correct
    row gets voided in favour of a superseded one.
    """
    rank = {v: i for i, v in enumerate(version_order)}
    df = _load()
    if df.empty or "market_ticker" not in df.columns:
        return {"voided": 0, "groups": 0, "unorderable": [], "changes": []}

    changes: list[dict] = []
    unorderable: list[tuple] = []
    groups = 0
    live_mask = df["status"] != "void"
    for key, idx in df[live_mask].groupby(
            ["market_ticker", "selection", "model_version"], dropna=False).groups.items():
        if len(idx) < 2:
            continue
        groups += 1
        versions = [df.loc[i, "pricing_version"] for i in idx]
        if any(v not in rank for v in versions):
            unorderable.append((key, versions))
            continue
        newest = max(rank[v] for v in versions)
        for i in idx:
            if rank[df.loc[i, "pricing_version"]] == newest:
                continue
            changes.append({
                "bet_id": df.loc[i, "bet_id"],
                "market_ticker": key[0],
                "selection": key[1],
                "superseded_version": df.loc[i, "pricing_version"],
                "superseded_by": version_order[newest],
                "status_before": df.loc[i, "status"],
            })
            if not dry_run:
                df.loc[i, "status"] = "void"
                df.loc[i, "result_logged_at"] = datetime.now(timezone.utc).isoformat()
                df.loc[i, "notes"] = (
                    f"voided: superseded by the {version_order[newest]} re-pricing of the "
                    f"same contract and selection. Re-pricing replaces a row; until "
                    f"2026-09-13 it only ever inserted one, so this wager was counted "
                    f"twice. No price, selection or outcome is disputed -- the surviving "
                    f"row carries the same bet at the current pricing version."
                )
    if not dry_run and changes:
        _save(df)
    return {"voided": len(changes), "groups": groups,
            "unorderable": unorderable, "changes": changes}


def backfill_after_fee_edges(rate: float, *, dry_run: bool = False) -> dict:
    """Fill `edge_after_fee_pct` on rows written before the column existed.

    This is a DERIVED column, not a re-pricing. Everything it needs is already
    in the row: `market_odds_decimal` is 1/ask by construction, so the ask, the
    fee and the fee-inclusive edge all follow from what was recorded at the
    time. No stake, selection, price or status changes, and `pricing_version`
    deliberately does not move -- nothing about which bets exist is altered.

    That distinction is the whole reason this is safe to run on the 70 open
    bets carrying run 4's pre-registered prediction. Re-pricing them would
    swap the population out from under a test that settles on 2026-09-13;
    computing a number that was always implied in them does not.
    """
    df = _load()
    if df.empty:
        return {"filled": 0, "skipped": 0}
    filled = skipped = 0
    for i, r in df.iterrows():
        if r.get("edge_after_fee_pct") is not None:
            skipped += 1
            continue
        dec, p = r.get("market_odds_decimal"), r.get("model_prob")
        if dec is None or p is None or float(dec) <= 1:
            skipped += 1
            continue
        ask = 1.0 / float(dec)
        total = ask + rate * ask * (1 - ask)
        if not 0 < total < 1:
            skipped += 1
            continue
        if not dry_run:
            df.loc[i, "edge_after_fee_pct"] = (float(p) / total - 1) * 100
            df.loc[i, "fee_assumption"] = rate
        filled += 1
    if not dry_run:
        _save(df)
    return {"filled": filled, "skipped": skipped, "rate": rate}


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
                "clv_positive_rate": None, **_clv_by_reference_quality(settled)}

    decided = settled[settled["status"] != "push"]
    wins = (decided["status"] == "won").sum()
    staked = decided["stake"].sum()
    returned = (decided["stake"] * decided["market_odds_decimal"] * (decided["status"] == "won")).sum()
    clv = settled["clv_pct"].dropna()
    return {
        **base,
        "win_rate": wins / len(decided) * 100 if len(decided) else None,
        "roi_pct": (returned - staked) / staked * 100 if staked else None,
        # Kept for continuity with every run before 2026-09-14, and NOT the
        # number to quote: it averages real closes together with references
        # from 8 hours out, which run 10 showed have opposite signs.
        "avg_clv_pct": clv.mean() if not clv.empty else None,
        "clv_positive_rate": (clv > 0).mean() * 100 if not clv.empty else None,
        **_clv_by_reference_quality(settled),
    }


def _clv_by_reference_quality(settled: pd.DataFrame) -> dict:
    """CLV over rows whose reference really is a close, and the rest apart.

    Rows settled before the lag was recorded have no `clv_reference_lag_h`.
    They are reported as `clv_unknown_reference_n` rather than being assumed
    good -- silently counting them as real closes is exactly the error this
    split exists to prevent.
    """
    empty = {"avg_clv_pct_real_close": None, "clv_real_close_n": 0,
             "avg_clv_pct_stale_reference": None, "clv_stale_reference_n": 0,
             "clv_unknown_reference_n": 0,
             "clv_reference_max_lag_h": CLV_REFERENCE_MAX_LAG_H}
    if settled.empty or "clv_pct" not in settled.columns:
        return empty

    rows = settled[settled["clv_pct"].notna()]
    if rows.empty:
        return empty

    lag = (pd.to_numeric(rows.get("clv_reference_lag_h"), errors="coerce")
           if "clv_reference_lag_h" in rows.columns
           else pd.Series([None] * len(rows), index=rows.index, dtype="float64"))
    clv = pd.to_numeric(rows["clv_pct"], errors="coerce")

    real = clv[lag.notna() & (lag <= CLV_REFERENCE_MAX_LAG_H)]
    stale = clv[lag.notna() & (lag > CLV_REFERENCE_MAX_LAG_H)]
    return {
        "avg_clv_pct_real_close": real.mean() if not real.empty else None,
        "clv_real_close_n": int(len(real)),
        "avg_clv_pct_stale_reference": stale.mean() if not stale.empty else None,
        "clv_stale_reference_n": int(len(stale)),
        "clv_unknown_reference_n": int(lag.isna().sum()),
        "clv_reference_max_lag_h": CLV_REFERENCE_MAX_LAG_H,
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
