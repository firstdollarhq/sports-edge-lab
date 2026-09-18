"""The edge-cap rejection, and the identity underneath the ledger's headline.

Run 18 tested the last untested lever in the bet rule: an upper CAP on claimed
edge, motivated by the project's most-cited replicating result -- the high half
of settled bets falls further below its claim than the low half, every time it
is measured.

Two things came out of it, and both are pinned here rather than left in a
journal entry:

* No cap beats the de-vigged closing line, in either phase, and the best
  eligible cap does not even beat the uncapped rule where it was chosen.
* Most of the headline separation is an ALGEBRAIC IDENTITY. Sorting bets by
  claimed edge sorts them by `claimed - market`, and `claim_gap - market_gap`
  IS `market - claimed`. The high half is guaranteed a larger claim gap
  whatever the outcomes do.

The second is the load-bearing one. A future run that re-derives "the bigger
the claim, the bigger the overstatement" and proposes capping should be
answered by `test_claim_gap_separation_is_mostly_an_identity` rather than by
another sweep.

~3s. Needs `data/processed/nfl_games.csv`, which is committed.
"""
import math

import pandas as pd
import pytest

from sportsedge.backtest import edge_band
from sportsedge.backtest.selection import nfl_sides
from sportsedge.storage import snapshots


@pytest.fixture(scope="module")
def sides():
    try:
        snapshots.read_processed("nfl_games")
    except FileNotFoundError:  # pragma: no cover - only without committed tables
        pytest.skip("nfl_games not present; run refresh-history")
    burn = edge_band.DEFAULT_BURN_IN
    sel_s = edge_band.DEFAULT_SELECTION_SEASONS
    hold_s = edge_band.DEFAULT_HOLDOUT_SEASONS
    sel = nfl_sides(seasons=burn + sel_s, test_seasons=sel_s, edge_threshold=0.0)
    hold = nfl_sides(seasons=burn + sel_s + hold_s, test_seasons=hold_s,
                     edge_threshold=0.0)
    return sel, hold


@pytest.fixture(scope="module")
def swept(sides):
    sel, hold = sides
    return edge_band.sweep_edge_cap(sel, hold)


def _frame(rows):
    return pd.DataFrame(rows)


# -- the gate ---------------------------------------------------------------

def test_no_cap_beats_the_closing_line_in_either_phase(swept):
    """The deployment gate, asked of all eleven bands twice."""
    assert swept["beats_market_selection"] == 0
    assert swept["beats_market_holdout"] == 0
    assert swept["adopt"] is False
    assert swept["reasons"]


def test_best_eligible_cap_loses_to_doing_nothing_where_it_was_chosen(swept):
    """The pick is not merely unconfirmed -- it never led in the first place."""
    pick, incumbent = swept["pick"], swept["incumbent"]["selection"]
    assert pick is not None
    assert pick["fair_roi_pct"] <= incumbent["fair_roi_pct"]
    assert "best eligible cap does not beat the uncapped rule in selection" \
        in swept["reasons"]


def test_the_incumbent_is_never_the_pick(swept):
    """`pick` means 'best ALTERNATIVE to the uncapped rule', always."""
    assert math.isfinite(swept["pick"]["cap"])


def test_the_eligibility_floor_is_what_rejects_the_tightest_cap(swept):
    """Without it, a 29-bet band with a 93-point interval would be adopted.

    The 5% band posts the best fair ROI of any finite cap in the selection
    window. It is also the smallest, by a factor of four. This asserts both
    halves of that, so the guard cannot be removed without a red test.
    """
    finite = [r for r in swept["selection"] if math.isfinite(r["cap"]) and r["n_bets"]]
    best_unguarded = max(finite, key=lambda r: r["fair_roi_pct"])
    assert best_unguarded["n_bets"] < swept["min_selection_bets"]
    assert best_unguarded["fair_roi_pct"] > swept["pick"]["fair_roi_pct"]
    assert swept["pick"]["n_bets"] >= swept["min_selection_bets"]
    # And it is a wide interval sitting on both sides of zero, not a result.
    lo, hi = best_unguarded["fair_ci95_pct"]
    assert lo < 0 < hi
    assert hi - lo > 50


# -- the identity -----------------------------------------------------------

def test_the_two_gaps_differ_by_exactly_the_market_model_spread(swept):
    """claim_gap - market_gap == market - claimed, exactly, in every band.

    This is the algebra the whole finding rests on, so it is asserted rather
    than argued.
    """
    for phase in ("selection", "holdout"):
        for r in swept[phase]:
            if not r["n_bets"]:
                continue
            lhs = r["claim_gap_pp"] - r["market_gap_pp"]
            rhs = (r["market"] - r["claimed"]) * 100
            assert lhs == pytest.approx(rhs, abs=1e-9)


def test_claim_gap_separation_is_mostly_an_identity(swept):
    """The ledger's headline split, run at 27x the sample and decomposed.

    Both phases reproduce the direction the ledger reports -- the high half
    falls further below its claim -- and in both, the identity term accounts
    for most or more than all of it.
    """
    for phase in ("selection", "holdout"):
        ms = swept["median_split"][phase]
        # Direction reproduces: the high half's claim gap is the worse one.
        assert ms["high"]["claim_gap_pp"] < ms["low"]["claim_gap_pp"]
        assert ms["separation_pp"] > 0
        assert ms["mechanical_share"] > 0.75
        assert ms["separation_pp"] == pytest.approx(
            ms["mechanical_pp"] + ms["empirical_pp"], abs=1e-9)


def test_the_empirical_remainder_does_not_replicate(swept):
    """What is left after the identity flips sign between the two windows.

    This is the reason the finding is a rejection and not a lever: the part of
    the split that carries information is not stable across two windows of the
    same league.
    """
    sel = swept["median_split"]["selection"]["empirical_pp"]
    hold = swept["median_split"]["holdout"]["empirical_pp"]
    assert sel * hold < 0


def test_error_against_the_market_does_not_order_with_claimed_edge(swept):
    """A cap can only pay if this slope is negative. Neither window says it is."""
    for phase in ("selection", "holdout"):
        t = swept["market_gap_trend"][phase]
        assert t["orders_with_edge"] is False
        lo, hi = t["ci95"]
        assert lo < 0 < hi


# -- the arithmetic, on frames whose answers are known by hand ---------------

def test_fair_roi_is_zero_when_outcomes_match_the_market():
    """A selection that knows exactly what the price knows returns nothing.

    Four sides at a fair 0.5, two winners: staked 4, returned 2 x 2.0 = 4.
    """
    sides = _frame([
        {"game_id": f"g{i}", "model_prob": 0.6, "decimal_odds": 1.9,
         "fair_market_prob": 0.5, "won": i < 2, "edge_frac": 0.14}
        for i in range(4)
    ])
    r = edge_band.band_stats(sides)
    assert r["fair_roi_pct"] == pytest.approx(0.0)
    assert r["market_gap_pp"] == pytest.approx(0.0)
    # Book ROI is NOT zero: the same bets at the vigged price lose the vig.
    assert r["book_roi_pct"] < 0


def test_beats_market_requires_the_interval_not_the_point_estimate():
    """One lucky winner at a long price is a positive ROI and not a result."""
    sides = _frame([
        {"game_id": f"g{i}", "model_prob": 0.3, "decimal_odds": 5.0,
         "fair_market_prob": 0.2, "won": i == 0, "edge_frac": 0.5}
        for i in range(4)
    ])
    r = edge_band.band_stats(sides)
    assert r["fair_roi_pct"] == pytest.approx(25.0)
    assert r["beats_market"] is False

    # Enough consistent evidence and the same gate does fire. It takes a lot:
    # at these prices a +25% fair ROI is still inside its own interval at
    # n = 200, which is the reason this project keeps reporting sample sizes
    # next to ROIs.
    many = _frame([
        {"game_id": f"g{i}", "model_prob": 0.3, "decimal_odds": 5.0,
         "fair_market_prob": 0.2, "won": i % 4 == 0, "edge_frac": 0.5}
        for i in range(1000)
    ])
    assert edge_band.band_stats(_frame(many[:200]))["beats_market"] is False
    assert edge_band.band_stats(many)["beats_market"] is True


def test_bands_are_cumulative_and_half_open():
    """[floor, cap): a side exactly at the cap belongs to the next band up."""
    sides = _frame([
        {"game_id": "a", "model_prob": 0.5, "decimal_odds": 2.0,
         "fair_market_prob": 0.5, "won": True, "edge_frac": 0.05},
        {"game_id": "b", "model_prob": 0.5, "decimal_odds": 2.0,
         "fair_market_prob": 0.5, "won": False, "edge_frac": 0.10},
        {"game_id": "c", "model_prob": 0.5, "decimal_odds": 2.0,
         "fair_market_prob": 0.5, "won": True, "edge_frac": 0.02},
    ])
    assert edge_band.band_stats(sides, cap=0.10)["n_bets"] == 1   # only 0.05
    assert edge_band.band_stats(sides, cap=0.15)["n_bets"] == 2   # 0.05 and 0.10
    # 0.02 is below the 3% floor and is in no band at all.
    assert edge_band.band_stats(sides, cap=math.inf)["n_bets"] == 2


def test_the_uncapped_band_is_the_rule_the_rest_of_the_repo_backtests(swept):
    """A cross-check, not a new number.

    The uncapped band on the 2024 holdout is by construction the same wager
    set `sweep_season_regression` scores at the incumbent `season_regression`,
    reached through a different module. Run 17 reported -12.67292964478684%
    with CI [-29.75, +4.40] on 285 games; this must reproduce it digit for
    digit, or the band machinery is quietly betting a different universe and
    every number above it is about something else.
    """
    hold = swept["incumbent"]["holdout"]
    assert hold["n_bets"] == 228
    assert hold["book_roi_pct"] == pytest.approx(-12.67292964478684, abs=1e-9)
    lo, hi = hold["book_ci95_pct"]
    assert (lo, hi) == pytest.approx((-29.75047908858088, 4.4046197990072065), abs=1e-9)


def test_ledger_adapter_keeps_only_settled_rows_and_converts_units():
    """PERCENT in the ledger, FRACTION everywhere in here. See betting/edge.py."""
    led = _frame([
        {"bet_id": "aaa", "status": "won", "model_prob": 0.5,
         "market_fair_prob": 0.4, "market_odds_decimal": 2.4, "edge_pct": 20.0},
        {"bet_id": "bbb", "status": "lost", "model_prob": 0.3,
         "market_fair_prob": 0.25, "market_odds_decimal": 3.8, "edge_pct": 14.0},
        {"bet_id": "ccc", "status": "pending", "model_prob": 0.6,
         "market_fair_prob": 0.5, "market_odds_decimal": 1.9, "edge_pct": 14.0},
        {"bet_id": "ddd", "status": "void", "model_prob": 0.6,
         "market_fair_prob": 0.5, "market_odds_decimal": 1.9, "edge_pct": 99.0},
    ])
    out = edge_band.sides_from_ledger(led)
    assert list(out["game_id"]) == ["aaa", "bbb"]
    assert list(out["won"]) == [True, False]
    assert out["edge_frac"].tolist() == pytest.approx([0.20, 0.14])


def test_the_identity_holds_on_the_real_ledger_too():
    """The decomposition is arithmetic, so it cannot fail on real rows either.

    This is what lets the journal put the ledger's split and the backtest's
    side by side: same function, same algebra, different sample.
    """
    from sportsedge.betting import ledger as ledger_mod
    sides = edge_band.sides_from_ledger(ledger_mod._load())
    if len(sides) < 4:  # pragma: no cover - only very early in the project
        pytest.skip("not enough settled rows to split")
    ms = edge_band.median_split(sides)
    assert ms["separation_pp"] == pytest.approx(
        ms["mechanical_pp"] + ms["empirical_pp"], abs=1e-9)
    for half in ("low", "high"):
        h = ms[half]
        assert h["claim_gap_pp"] - h["market_gap_pp"] == pytest.approx(
            h["identity_pp"], abs=1e-9)


def test_holdout_seasons_are_absent_from_the_selection_frame(sides):
    """The confirmation window must not be visible while the cap is chosen."""
    sel, hold = sides
    sel_seasons = set(sel["season"].astype(str))
    hold_seasons = set(hold["season"].astype(str))
    assert sel_seasons == {str(s) for s in edge_band.DEFAULT_SELECTION_SEASONS}
    assert hold_seasons == {str(s) for s in edge_band.DEFAULT_HOLDOUT_SEASONS}
    assert not (sel_seasons & hold_seasons)
