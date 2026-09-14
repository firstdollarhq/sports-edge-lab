"""The CLV recovery pass over rows that settled before their kickoff was known.

Background: `settle_pending` computes CLV once, at settlement, and only looks
at rows that are still pending. nflverse publishes the NFL schedule in advance
so a kickoff is always available there; football-data.co.uk publishes only
completed matches and publishes them days late, so an EPL bet settles from
Kalshi while no stats source can yet say when the match started. Without a
second pass that CLV is lost permanently, despite the prices being present in
the committed snapshots the whole time.

The tests that matter most here are the two that constrain what the pass may
NOT do: it may not reach for the expiration when the kickoff is missing (that
is the run-3 lookahead bug, one sport over), and it may not touch anything
about the bet except the closing-line columns.
"""
import pandas as pd
import pytest

import sportsedge.betting.ledger as ledger_mod
import sportsedge.betting.settle as settle_mod
import sportsedge.ingest.kickoff as kickoff_mod
import sportsedge.storage.snapshots as snapshots_mod


KICKOFF = "2026-09-12T14:00:00+00:00"
EXPIRY = "2026-09-12T17:00:00Z"
TICKER = "KXEPLGAME-26SEP12CRYIPS-CRY"


@pytest.fixture
def lab(tmp_path, monkeypatch):
    """An isolated ledger plus a stub snapshot history and EPL schedule."""
    monkeypatch.setattr(ledger_mod, "LEDGER_PATH", tmp_path / "ledger.csv")
    kickoff_mod.clear_cache()

    # Two captured quotes: one comfortably pre-kickoff, one from inside the
    # match. Only the first may ever be used.
    quotes = {
        "pre": {"market_ticker": TICKER, "fetched_at": "2026-09-12T06:11:15+00:00",
                "yes_ask": 0.40},
        "inplay": {"market_ticker": TICKER, "fetched_at": "2026-09-12T15:02:47+00:00",
                   "yes_ask": 0.95},
    }

    def fake_latest_before(sport, market_ticker, cutoff):
        rows = [q for q in quotes.values()
                if q["market_ticker"] == market_ticker and q["fetched_at"] < str(cutoff)]
        return max(rows, key=lambda r: r["fetched_at"]) if rows else None

    monkeypatch.setattr(snapshots_mod, "latest_before", fake_latest_before)
    monkeypatch.setattr(settle_mod.snapshots, "latest_before", fake_latest_before)
    return tmp_path


def _settled_epl_bet(*, kickoff_utc=None, status="lost", clv=None):
    """A settled EPL row, by default with no kickoff and no CLV."""
    bet_id = ledger_mod.add_bet(
        sport="soccer", league="EPL", game_id="KXEPLGAME-26SEP12CRYIPS",
        matchup="Ipswich @ Crystal Palace", market="moneyline", selection="home",
        model_prob=0.55, model_version="soccer-elo-v2", market_odds_decimal=2.5,
        book="kalshi", edge_pct=37.5, stake=1.0, market_ticker=TICKER,
        expiration_time=EXPIRY, kickoff_utc=kickoff_utc, pricing_version="p2",
    )
    df = ledger_mod._load()
    i = df.index[df["bet_id"] == bet_id][0]
    df.loc[i, "status"] = status
    if clv is not None:
        df.loc[i, "clv_pct"] = clv
    ledger_mod._save(df)
    return bet_id


def _stats_table_has_the_match(monkeypatch, present: bool):
    """Stand in for football-data.co.uk having (or not yet having) the fixture."""
    rows = []
    if present:
        rows.append({"home_team": "Crystal Palace", "away_team": "Ipswich",
                     "kickoff_utc": KICKOFF})
    df = pd.DataFrame(rows, columns=["home_team", "away_team", "kickoff_utc"])
    monkeypatch.setattr(snapshots_mod, "read_processed", lambda name: df)
    monkeypatch.setattr(kickoff_mod.snapshots, "read_processed", lambda name: df)
    kickoff_mod.clear_cache()


def test_clv_is_recovered_once_the_stats_source_catches_up(lab, monkeypatch):
    """The whole point: a row settled without a kickoff is not a lost cause."""
    bet_id = _settled_epl_bet()

    # First attempt, the day of the match: football-data.co.uk has nothing yet.
    _stats_table_has_the_match(monkeypatch, False)
    early = settle_mod.backfill_clv()
    assert early["filled"] == 0
    assert early["changes"][0]["reason"] == "no kickoff in stats source"

    # Days later the fixture is published and the same pass recovers it.
    _stats_table_has_the_match(monkeypatch, True)
    late = settle_mod.backfill_clv()
    assert late["filled"] == 1

    row = ledger_mod._load().set_index("bet_id").loc[bet_id]
    # Priced at 2.5 (40c), closed at the pre-kickoff 40c ask -> flat.
    assert float(row["closing_odds_decimal"]) == pytest.approx(2.5)
    assert float(row["clv_pct"]) == pytest.approx(0.0)
    assert str(row["kickoff_utc"]).startswith("2026-09-12T14:00")


def test_backfill_never_falls_back_to_the_expiration(lab, monkeypatch):
    """The run-3 lookahead bug, guarded on the recovery path.

    Kalshi's expiry sits hours after kickoff. If the pass ever cut its search
    there instead, it would pick up the 95c in-play quote and book a CLV of
    roughly -61% that is a restatement of the result, not a price we could
    have traded at. With no resolvable kickoff the answer must be "no CLV".
    """
    _settled_epl_bet()
    _stats_table_has_the_match(monkeypatch, False)

    res = settle_mod.backfill_clv()

    assert res["filled"] == 0
    row = ledger_mod._load().iloc[0]
    assert pd.isna(row["clv_pct"])
    assert pd.isna(row["closing_odds_decimal"])


def test_backfill_ignores_the_in_play_quote_even_when_kickoff_is_known(lab, monkeypatch):
    """Having a kickoff is not licence to use the later price."""
    _settled_epl_bet()
    _stats_table_has_the_match(monkeypatch, True)

    settle_mod.backfill_clv()

    row = ledger_mod._load().iloc[0]
    # 1/0.95 = 1.052..., which the 0.40 pre-kickoff ask must beat out.
    assert float(row["closing_odds_decimal"]) == pytest.approx(2.5)


def test_backfill_changes_nothing_except_the_closing_line_columns(lab, monkeypatch):
    """Same guarantee `backfill_after_fee_edges` gives: derived, not a re-pricing."""
    _settled_epl_bet()
    before = ledger_mod._load().iloc[0].to_dict()

    _stats_table_has_the_match(monkeypatch, True)
    settle_mod.backfill_clv()
    after = ledger_mod._load().iloc[0].to_dict()

    mutable = {"kickoff_utc", "closing_odds_decimal", "clv_pct",
               "clv_reference_lag_h"}
    for col in before:
        if col in mutable:
            continue
        assert before[col] == after[col] or (
            pd.isna(before[col]) and pd.isna(after[col])
        ), f"backfill moved {col}: {before[col]!r} -> {after[col]!r}"


def test_backfill_leaves_pending_bets_alone(lab, monkeypatch):
    """Open positions belong to `settle_pending`; this pass is recovery only."""
    _settled_epl_bet(status="pending")
    _stats_table_has_the_match(monkeypatch, True)

    res = settle_mod.backfill_clv()

    assert res["candidates"] == 0
    assert pd.isna(ledger_mod._load().iloc[0]["clv_pct"])


def test_backfill_never_overwrites_an_existing_clv(lab, monkeypatch):
    _settled_epl_bet(kickoff_utc=KICKOFF, clv=12.5)
    _stats_table_has_the_match(monkeypatch, True)

    res = settle_mod.backfill_clv()

    assert res["candidates"] == 0
    assert float(ledger_mod._load().iloc[0]["clv_pct"]) == pytest.approx(12.5)


def test_backfill_is_idempotent(lab, monkeypatch):
    _settled_epl_bet()
    _stats_table_has_the_match(monkeypatch, True)

    first = settle_mod.backfill_clv()
    snapshot = ledger_mod._load().to_dict()
    second = settle_mod.backfill_clv()

    assert first["filled"] == 1
    assert second["filled"] == 0 and second["candidates"] == 0
    assert ledger_mod._load().to_dict() == snapshot


def test_dry_run_reports_without_writing(lab, monkeypatch):
    _settled_epl_bet()
    _stats_table_has_the_match(monkeypatch, True)

    res = settle_mod.backfill_clv(dry_run=True)

    assert res["filled"] == 1
    assert pd.isna(ledger_mod._load().iloc[0]["clv_pct"])


def test_missing_snapshot_is_reported_distinctly_from_missing_kickoff(lab, monkeypatch):
    """The two failures need different fixes, so they must not read alike.

    'no kickoff' means wait for the stats source. 'no snapshot' means our own
    capture cadence missed the window -- and that one is never recoverable,
    because a price we did not record cannot be reconstructed later.
    """
    _settled_epl_bet()
    _stats_table_has_the_match(monkeypatch, True)
    monkeypatch.setattr(settle_mod.snapshots, "latest_before",
                        lambda *a, **k: None)

    res = settle_mod.backfill_clv()

    assert res["filled"] == 0
    assert res["changes"][0]["reason"] == "no snapshot captured before kickoff"
    # The kickoff is still recorded: it is what distinguishes the two cases.
    assert str(ledger_mod._load().iloc[0]["kickoff_utc"]).startswith("2026-09-12T14:00")


# -- the reference lag ---------------------------------------------------------
#
# CLV compares the price we got to "the close". Before the capture cron the
# best reference this project held sat 7-11h before kickoff, and run 10
# measured that the sign of CLV flips with that lag: +4.04% mean over the 9
# rows with a stale reference (not one negative), -1.41% over the 14 with a
# reference inside the hour. Recording the lag is what lets the two be
# reported apart instead of averaged into a number describing neither.


def test_settlement_records_how_stale_the_reference_was(lab, monkeypatch):
    """The quote is 7.81h before kickoff, and the row must say so."""
    _settled_epl_bet()
    _stats_table_has_the_match(monkeypatch, True)

    res = settle_mod.backfill_clv()

    assert res["filled"] == 1
    row = ledger_mod._load().iloc[0]
    # 06:11:15 -> 14:00:00 is 7h 48m 45s.
    assert float(row["clv_reference_lag_h"]) == pytest.approx(7.8125)
    assert res["changes"][0]["clv_reference_lag_h"] == pytest.approx(7.8125)


def test_lag_is_backfilled_onto_rows_that_already_have_clv(lab, monkeypatch):
    """The cohort that produced the finding settled before the column existed.

    Those rows have a CLV and no lag, so the recovery pass has to reach them
    too -- otherwise the split has nothing to report on for the only 23 rows
    the project has.
    """
    _settled_epl_bet(kickoff_utc=KICKOFF, clv=12.5)
    _stats_table_has_the_match(monkeypatch, True)

    res = settle_mod.backfill_clv()

    # Nothing to fill on the CLV pass -- this row already had one.
    assert res["candidates"] == 0 and res["filled"] == 0
    assert res["reference_lags_filled"] == 1
    row = ledger_mod._load().iloc[0]
    assert float(row["clv_reference_lag_h"]) == pytest.approx(7.8125)
    # And the CLV it already carried is untouched.
    assert float(row["clv_pct"]) == pytest.approx(12.5)


def test_lag_backfill_never_restates_an_existing_clv(lab, monkeypatch):
    """A later snapshot must not silently re-price a settled row."""
    _settled_epl_bet(kickoff_utc=KICKOFF, clv=99.0)
    _stats_table_has_the_match(monkeypatch, True)

    settle_mod.backfill_clv()

    row = ledger_mod._load().iloc[0]
    assert float(row["clv_pct"]) == pytest.approx(99.0)
    assert pd.isna(row["closing_odds_decimal"])


def test_summary_splits_clv_by_reference_quality(lab, monkeypatch):
    """A real close and an 8-hour-old reference must not be averaged together."""
    _settled_epl_bet(kickoff_utc=KICKOFF, clv=6.0)          # stale, 7.81h
    df = ledger_mod._load()
    df.loc[0, "clv_reference_lag_h"] = 7.8125
    # A second row whose reference is a genuine close.
    df.loc[1] = df.loc[0]
    df.loc[1, "bet_id"] = "realclose"
    df.loc[1, "clv_pct"] = -2.0
    df.loc[1, "clv_reference_lag_h"] = 0.25
    # A third from before the column existed: unknown, and never assumed good.
    df.loc[2] = df.loc[0]
    df.loc[2, "bet_id"] = "unknownref"
    df.loc[2, "clv_pct"] = 40.0
    df.loc[2, "clv_reference_lag_h"] = None
    ledger_mod._save(df)

    s = ledger_mod.summarize()["shadow"]

    assert s["clv_real_close_n"] == 1
    assert s["avg_clv_pct_real_close"] == pytest.approx(-2.0)
    assert s["clv_stale_reference_n"] == 1
    assert s["avg_clv_pct_stale_reference"] == pytest.approx(6.0)
    assert s["clv_unknown_reference_n"] == 1
    # The undifferentiated average still exists, and is none of the three.
    assert s["avg_clv_pct"] == pytest.approx((6.0 - 2.0 + 40.0) / 3)
