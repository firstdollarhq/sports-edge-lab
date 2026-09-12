"""The venue: what trading on an exchange instead of a sportsbook costs.

Three things are pinned here, in descending order of how much damage getting
them wrong would do.

1. **The pricer refactor changed nothing.** `engine.backtest_nfl` and
   `backtest_soccer` now route every price through a `Pricer`. If the default
   path drifts by so much as a bet, every ROI figure this project has published
   becomes unreproducible. So the default is asserted identical to an explicit
   `SportsbookPricer`, bet for bet.

2. **The agreement join is disambiguated by kickoff.** The first version joined
   the Kalshi board to the stats table on (home_team, away_team), which is not
   unique across seasons: 30 events fanned out to 131 rows and the reported
   correlation fell from 0.9955 to 0.4572. Five runs, five bugs of this shape.
   The regression here builds a table where one fixture recurs in three seasons
   and asserts the current board matches exactly one of them.

3. **The fee is regressive in stake.** fee/stake = rate * (1 - price), so the
   cost of trading a 15c longshot is several times the cost of trading a 75c
   favourite -- while a sportsbook's proportional vig is flat across the board.
   This is the whole reason the exchange turns out to be the more expensive
   venue for this particular bet rule, which bets below even money 88.6% of the
   time. It reads as a footnote and it is worth 3.3 points of ROI.
"""
from __future__ import annotations

import pandas as pd
import pytest

from sportsedge.backtest import kalshi_engine as ke
from sportsedge.backtest.engine import SportsbookPricer, backtest_nfl
from sportsedge.models.elo import NflEloModel
from sportsedge.ingest import kickoff


# -- fixtures -----------------------------------------------------------------


def _game(gid, season, week, home, away, hs, aws, ho, ao, kick):
    return {"game_id": gid, "season": season, "week": week, "game_date": kick[:10],
            "home_team": home, "away_team": away, "home_score": hs, "away_score": aws,
            "result": "H" if hs > aws else ("A" if aws > hs else "D"),
            "home_odds_decimal": ho, "away_odds_decimal": ao, "kickoff_utc": kick}


@pytest.fixture
def games():
    """Two seasons of a tiny league, with book prices on every game."""
    rows = []
    for season in (2023, 2024):
        for week in range(1, 7):
            rows.append(_game(f"{season}_{week:02d}_A_B", season, week, "A", "B",
                              24, 17 + week, 1.75, 2.30,
                              f"{season}-09-{10 + week:02d}T17:00:00+00:00"))
            rows.append(_game(f"{season}_{week:02d}_C_D", season, week, "C", "D",
                              13, 27, 2.60, 1.60,
                              f"{season}-09-{10 + week:02d}T20:00:00+00:00"))
    return pd.DataFrame(rows)


@pytest.fixture
def snapshot_root(tmp_path):
    """A captured Kalshi board: two events, both 1c wide."""
    d = tmp_path / "nfl"
    d.mkdir(parents=True)
    rows = []
    for ev, home, away, bid_h in (("KXNFLGAME-24SEP11AB", "A", "B", 0.57),
                                  ("KXNFLGAME-24SEP11CD", "C", "D", 0.38)):
        for sel, bid in (("home", bid_h), ("away", round(1 - bid_h - 0.01, 2))):
            rows.append({"sport": "nfl", "league": "NFL", "event_ticker": ev,
                         "market_ticker": f"{ev}-{sel}", "game_id": None,
                         "home_team": home, "away_team": away,
                         "expiration_time": "2024-09-12T00:00:00Z", "selection": sel,
                         "yes_bid": bid, "yes_ask": round(bid + 0.01, 2),
                         "implied_prob_mid": round(bid + 0.005, 3), "spread": 0.01,
                         "yes_bid_size": 500, "yes_ask_size": 500, "volume": 5000,
                         "volume_24h": 1000, "open_interest": 2000, "status": "active",
                         "source": "kalshi", "fetched_at": "2024-09-11T12:00:00+00:00"})
    pd.DataFrame(rows).to_csv(d / "2024-09-11.csv", index=False)
    return str(tmp_path)


# -- 1. the refactor is behaviour-preserving ----------------------------------


def test_pricer_default_matches_book(games):
    """No pricer and an explicit SportsbookPricer must agree, bet for bet.

    Every published ROI figure depends on this. A drift of one bet here is a
    silent restatement of the project's entire results table.
    """
    a = backtest_nfl(games, NflEloModel(), edge_threshold=0.03)
    b = backtest_nfl(games, NflEloModel(), edge_threshold=0.03, pricer=SportsbookPricer())
    assert a["log_loss"] == b["log_loss"]
    assert a["roi"] == b["roi"]
    assert [x["game_id"] for x in a["bets"]] == [x["game_id"] for x in b["bets"]]
    assert [x["decimal_odds"] for x in a["bets"]] == [x["decimal_odds"] for x in b["bets"]]


def test_sportsbook_pricer_returns_the_book_quote():
    assert SportsbookPricer().decimal_odds(0.5, 1.91) == 1.91


def test_pricer_returning_none_skips_the_side(games):
    """An untradeable synthetic quote must produce no bet, not a crash."""

    class NoMarket:
        def decimal_odds(self, fair_prob, book_decimal_odds):
            return None

    res = backtest_nfl(games, NflEloModel(), edge_threshold=0.03, pricer=NoMarket())
    assert res["bets"] == []
    assert res["roi"]["n_bets"] == 0
    # The forecast is venue-independent and must still be scored.
    assert res["log_loss"] > 0


# -- 2. the join ---------------------------------------------------------------


def test_agreement_join_is_kickoff_disambiguated(monkeypatch, snapshot_root):
    """The same fixture recurs every season; only today's game may match.

    Regression for the fanout that turned 30 Kalshi events into 131 rows and
    reported a 0.46 correlation between two venues that actually agree at 0.9955.
    """
    sched = pd.DataFrame([
        # A hosts B in three different seasons -- the non-unique key.
        _game("2022_01_A_B", 2022, 1, "A", "B", 20, 10, 5.00, 1.20,
              "2022-09-11T17:00:00+00:00"),
        _game("2023_01_A_B", 2023, 1, "A", "B", 20, 10, 1.05, 9.00,
              "2023-09-11T17:00:00+00:00"),
        _game("2024_01_A_B", 2024, 1, "A", "B", 20, 10, 1.75, 2.30,
              "2024-09-11T17:00:00+00:00"),
        _game("2024_01_C_D", 2024, 1, "C", "D", 13, 27, 2.60, 1.60,
              "2024-09-11T20:00:00+00:00"),
    ])
    kickoff.clear_cache()
    monkeypatch.setattr(kickoff.snapshots, "read_processed", lambda name: sched)
    monkeypatch.setattr(ke.snapshots, "read_processed", lambda name: sched)
    try:
        res = ke.measure_agreement("nfl", root=snapshot_root)
    finally:
        kickoff.clear_cache()

    assert res["n"] == 2, "two events on the board -> at most two comparisons"
    matched = set(res["detail"]["game_id"])
    assert matched == {"2024_01_A_B", "2024_01_C_D"}
    # The 2022 and 2023 repeats carry deliberately absurd prices; if either had
    # joined, the disagreement would be enormous.
    assert res["mean_abs_diff"] < 0.05


def test_agreement_is_two_way_only():
    with pytest.raises(ValueError):
        ke.measure_agreement("soccer")


def test_agreement_with_no_snapshots_reports_zero(tmp_path):
    assert ke.measure_agreement("nfl", root=str(tmp_path))["n"] == 0


# -- 3. the venue's cost shape -------------------------------------------------


def test_buy_price_is_ask_plus_fee():
    p = ke.KalshiPricer(half_spread=0.005, fee_rate=0.07)
    ask = 0.5 + 0.005
    assert p.buy_price(0.5) == pytest.approx(ask + 0.07 * ask * (1 - ask))
    assert p.decimal_odds(0.5, 1.91) == pytest.approx(1 / p.buy_price(0.5))


def test_zero_fee_is_just_the_spread():
    p = ke.KalshiPricer(half_spread=0.005, fee_rate=0.0)
    assert p.buy_price(0.4) == pytest.approx(0.405)


def test_untradeable_prices_return_none():
    p = ke.KalshiPricer(half_spread=0.005)
    assert p.buy_price(0.999) is None       # ask lands at or above $1
    assert p.buy_price(-0.01) is None
    assert p.decimal_odds(0.999, 2.0) is None


def test_fee_is_regressive_in_stake():
    """Flat in notional, but the fraction of YOUR money it takes rises as the
    price falls. This is the mechanism behind the whole venue result."""
    rate = 0.07
    tolls = {}
    for fair in (0.10, 0.25, 0.50, 0.75, 0.90):
        ask = fair + 0.005
        tolls[fair] = (rate * ask * (1 - ask)) / ask      # == rate * (1 - ask)
    prices = sorted(tolls)
    fractions = [tolls[p] for p in prices]
    assert fractions == sorted(fractions, reverse=True), "fee/stake must fall as price rises"
    assert fractions[0] > 3 * fractions[-1], "a 10c longshot pays several times a 90c favourite"


def test_exchange_is_dearer_than_the_book_on_longshots():
    """A proportional vig is flat across prices; a quadratic fee is not.

    At a typical favourite price the two venues are close. On the longshots
    this project's bet rule actually takes, the exchange costs multiples more.
    """
    book_overround = 0.043            # measured, 2026-09-12 NFL board
    p = ke.KalshiPricer(half_spread=0.005, fee_rate=0.07)

    def book_toll(fair):
        return (fair * (1 + book_overround) - fair) / fair

    def kalshi_toll(fair):
        return (p.buy_price(fair) - fair) / fair

    assert kalshi_toll(0.70) < 2 * book_toll(0.70)
    assert kalshi_toll(0.15) > 2 * book_toll(0.15)


def test_breakeven_edge_is_widest_at_the_middle_in_points():
    """In probability points the toll peaks near 50c (the quadratic's vertex),
    even though as a fraction of stake it is worst on longshots. Both framings
    are true and they point opposite ways, which is exactly why the module
    reports the toll in both."""
    pts = {p: ke.breakeven_edge(p, 0.005, 0.07) for p in (0.10, 0.50, 0.90)}
    assert pts[0.50] > pts[0.10]
    assert pts[0.50] > pts[0.90]


def test_half_spread_measured_from_snapshots(snapshot_root):
    m = ke.measure_half_spread("nfl", root=snapshot_root)
    assert m["n"] == 4
    assert m["median"] == pytest.approx(0.005)
    assert m["by_price_bucket"]


def test_half_spread_falls_back_without_snapshots(tmp_path):
    m = ke.measure_half_spread("nfl", root=str(tmp_path))
    assert m["median"] == ke.DEFAULT_HALF_SPREAD
    assert "note" in m


def test_venue_from_snapshots_uses_the_measured_spread(snapshot_root):
    v = ke.venue_from_snapshots("nfl", root=snapshot_root)
    assert v.half_spread == pytest.approx(0.005)


# -- the unverified constant ---------------------------------------------------


def test_fee_rate_is_flagged_unverified():
    """The fee's shape is confirmed from the Kalshi API; its coefficient is not.

    If a future run verifies the rate, flip the flag -- but until then nothing
    may present a fee-dependent number as settled, and `fee_sensitivity` exists
    so conclusions can be checked at fee=0.
    """
    assert ke.FEE_RATE_IS_VERIFIED is False


def test_fee_sensitivity_spans_zero(games):
    df = ke.fee_sensitivity(lambda g, **kw: backtest_nfl(g, NflEloModel(), **kw),
                            games, sport="nfl", fee_rates=(0.0, 0.07),
                            root="/nonexistent", edge_threshold=0.03)
    assert list(df["fee_rate"]) == [0.0, 0.07]
    # A higher fee can never make a bet cheaper, so ROI must not improve.
    if df["roi_pct"].notna().all():
        assert df["roi_pct"].iloc[1] <= df["roi_pct"].iloc[0] + 1e-9


def test_compare_venues_reports_both_and_the_delta(games):
    res = ke.compare_venues(lambda g, **kw: backtest_nfl(g, NflEloModel(), **kw),
                            games, sport="nfl", root="/nonexistent", edge_threshold=0.03)
    assert res["simulated_at_venue"] is True, "must never read as an observed return"
    assert res["fee_rate_verified"] is False
    assert res["sportsbook"]["n_bets"] >= 0 and res["kalshi_simulated"]["n_bets"] >= 0
