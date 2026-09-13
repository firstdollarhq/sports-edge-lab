"""The scorecard's job is to make the model-vs-market comparison unfakeable."""
import numpy as np
import pandas as pd
import pytest

from sportsedge.betting import scorecard


def _df(rows):
    cols = ["status", "sport", "model_prob", "market_fair_prob",
            "market_odds_decimal", "market_ticker", "selection"]
    return pd.DataFrame(rows, columns=cols)


def test_poisson_binomial_is_exact_and_not_a_binomial_on_the_mean():
    """The cohort spans 0.14 to 0.63, so a binomial on the mean is the wrong
    null. Two coins at 0.5 and 0.1: P(0 wins) = 0.5*0.9 = 0.45."""
    pmf = scorecard._poisson_binomial_pmf(np.array([0.5, 0.1]))
    assert pmf.sum() == pytest.approx(1.0)
    assert pmf[0] == pytest.approx(0.45)
    assert pmf[2] == pytest.approx(0.05)


def test_a_low_win_rate_alone_is_not_evidence_against_the_model():
    """Seven longshots at 0.15 that win once is EXACTLY what the model said.
    The scorecard must not make that look like a failure."""
    rows = [("lost", "soccer", 0.15, 0.15, 6.6, f"T{i}", "home") for i in range(6)]
    rows.append(("won", "soccer", 0.15, 0.15, 6.6, "T6", "home"))
    s = scorecard.score(_df(rows))
    assert s["win_rate_pct"] == pytest.approx(100 / 7)
    assert s["model_expected_wins"] == pytest.approx(1.05)
    assert s["p_at_most_model"] > 0.5          # unremarkable, as it should be
    assert s["log_loss_gap_vs_market"] == pytest.approx(0.0)


def test_the_gap_is_positive_when_the_model_is_worse_than_the_closing_line():
    """Sign convention matters: positive = the model loses to the market on
    the bets it chose. That is the number the deployment gate is about."""
    rows = [("lost", "soccer", 0.60, 0.20, 5.0, f"T{i}", "home") for i in range(5)]
    s = scorecard.score(_df(rows))
    assert s["log_loss_gap_vs_market"] > 0
    assert s["model_overstatement_pp"] > s["market_overstatement_pp"]


def test_duplicate_wagers_are_counted_once_and_flagged():
    """A wager logged twice shares its twin's outcome, so fourteen such rows
    are seven trials. Reporting rows as n is how a CI ends up sqrt(2) narrow."""
    rows = [("lost", "soccer", 0.4, 0.3, 3.0, "T1", "home"),
            ("lost", "soccer", 0.4, 0.3, 3.1, "T1", "home"),
            ("won", "soccer", 0.4, 0.3, 3.0, "T2", "home")]
    s = scorecard.score(_df(rows))
    assert s["rows"] == 3
    assert s["effective_n"] == 2
    assert "warning" in s


def test_no_warning_once_the_ledger_is_clean():
    rows = [("lost", "soccer", 0.4, 0.3, 3.0, "T1", "home"),
            ("won", "soccer", 0.4, 0.3, 3.0, "T2", "home")]
    s = scorecard.score(_df(rows))
    assert s["effective_n"] == s["rows"] == 2
    assert "warning" not in s


def test_void_and_pending_rows_never_enter_the_score():
    rows = [("won", "soccer", 0.4, 0.3, 3.0, "T1", "home"),
            ("void", "soccer", 0.9, 0.1, 9.0, "T2", "home"),
            ("pending", "soccer", 0.9, 0.1, 9.0, "T3", "home")]
    s = scorecard.score(_df(rows))
    assert s["rows"] == 1 and s["wins"] == 1


def test_roi_is_computed_at_the_price_actually_recorded():
    rows = [("won", "nfl", 0.4, 0.36, 2.5, "T1", "away"),
            ("lost", "nfl", 0.4, 0.36, 2.5, "T2", "away")]
    s = scorecard.score(_df(rows))
    assert s["profit_units"] == pytest.approx(0.5)
    assert s["roi_pct"] == pytest.approx(25.0)


def test_empty_population_returns_zero_not_a_number():
    assert scorecard.score(_df([]))["n"] == 0
