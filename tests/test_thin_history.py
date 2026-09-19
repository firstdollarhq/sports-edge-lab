"""The promoted-team bias, and the counter that is all we kept of it.

Run 20 found that Elo's 1500 start makes newly-promoted EPL sides look better
than they are, measured the bias, tried to correct it, and rejected the
correction because it bought nothing out-of-sample. These tests pin both
halves: the counter behaves, and the measurement that motivated it is
reproducible from the committed table rather than living only in a journal.
"""
import pandas as pd
import pytest

from sportsedge.betting import history
from sportsedge.models.elo import SoccerEloModel
from sportsedge.models.calibration import SoccerOutcomeCalibrator
from sportsedge.betting.edge import devig_three_way


def _rec(home, away):
    return {"home_team": home, "away_team": away, "selection": "away"}


def _games(pairs):
    return pd.DataFrame([{"home_team": h, "away_team": a} for h, a in pairs])


def test_team_game_counts_counts_both_sides():
    g = _games([("A", "B"), ("B", "A"), ("A", "C")])
    assert history.team_game_counts(g) == {"A": 3, "B": 2, "C": 1}


def test_team_absent_from_the_table_counts_as_zero_not_missing():
    # The debutant case: Elo gives it default_rating, the table has never
    # heard of it, and that is exactly when the counter has to fire.
    g = _games([("A", "B")] * 40)
    r = history.thin_history([_rec("A", "Newcomer")], g)
    assert r["flagged"] == 1
    assert r["teams"]["Newcomer"] == 0


def test_a_fixture_is_thin_when_either_side_is_thin():
    # elo_diff is a difference, so a thin rating contaminates the price
    # whichever way the bet was struck.
    g = pd.concat([_games([("A", "B")] * 40), _games([("C", "A")] * 3)])
    assert history.thin_history([_rec("A", "C")], g)["flagged"] == 1
    assert history.thin_history([_rec("C", "A")], g)["flagged"] == 1


def test_established_fixtures_are_not_flagged():
    g = _games([("A", "B")] * 40)
    r = history.thin_history([_rec("A", "B")], g)
    assert r["flagged"] == 0 and r["teams"] == {} and r["flagged_pct"] == 0.0


def test_empty_recs_do_not_divide_by_zero():
    assert history.thin_history([], _games([("A", "B")]))["flagged_pct"] == 0.0


def test_the_counter_gates_nothing():
    """It reports. A flagged rec is still a rec, and nothing is mutated.

    The whole point of this module is that the correction was rejected; if it
    ever starts removing bets, that is a model change and belongs in a sweep
    with a holdout, not here.
    """
    g = _games([("A", "B")] * 40)
    recs = [_rec("A", "Newcomer"), _rec("A", "B")]
    before = [dict(r) for r in recs]
    out = history.thin_history(recs, g)
    assert out["flagged"] == 1
    # The caller's list and its contents come back untouched...
    assert len(recs) == 2 and recs == before
    # ...and the report carries counts, not a filtered board.
    assert set(out) == {"threshold_games", "flagged", "flagged_pct", "teams"}


# --- the measurement itself -------------------------------------------------

@pytest.fixture(scope="module")
def debut_rows():
    """Walk the committed EPL table forward and score every season after the
    first, recording the model's probability for each debutant side against
    the de-vigged market. This is the run 20 measurement, re-derived."""
    df = pd.read_csv("data/processed/epl_games.csv")
    df["season"] = df["season"].astype(str)
    df = df.sort_values(["season", "game_date"]).reset_index(drop=True)
    df = df.dropna(subset=["home_score", "away_score"])
    df = df[df.season != "2026-27"]                    # partial, not scorable
    seasons = sorted(df.season.unique())
    seen, seen_before = set(), {}
    for s in seasons:
        seen_before[s] = set(seen)
        seen |= set(df[df.season == s].home_team) | set(df[df.season == s].away_team)

    model, diffs, outs, rows = SoccerEloModel(), [], [], []
    for i, s in enumerate(seasons):
        cal = None
        if i >= 1:
            cal = SoccerOutcomeCalibrator()
            cal.fit(diffs, outs)
        for _, g in df[df.season == s].iterrows():
            diff = model.elo_diff(g.home_team, g.away_team)
            cols = ["home_odds_decimal", "draw_odds_decimal", "away_odds_decimal"]
            if cal is not None and all(pd.notna(g[c]) for c in cols):
                pr = cal.predict_proba(diff)
                fh, fd, fa = devig_three_way(1 / g.home_odds_decimal,
                                             1 / g.draw_odds_decimal,
                                             1 / g.away_odds_decimal)
                for team, side, fair in ((g.home_team, "H", fh), (g.away_team, "A", fa)):
                    rows.append({"season": s, "team": team,
                                 "debut": team not in seen_before[s],
                                 "p_model": pr.get(side, 0.0), "p_market": fair,
                                 "won": 1 if g.result == side else 0})
            diffs.append(diff)
            outs.append(g.result)
            model.update(g.home_team, g.away_team, g.home_score, g.away_score)
    r = pd.DataFrame(rows)
    r = r[r.season != "2019-20"]                       # everyone is a debutant there
    r["bias"] = r.p_model - r.p_market
    return r


def test_the_model_overrates_debutants_and_the_market_does_not(debut_rows):
    d = debut_rows[debut_rows.debut]
    e = debut_rows[~debut_rows.debut]
    # The market is close to right; the model is not. The gap is the model's.
    assert abs(d.p_market.mean() - d.won.mean()) < 0.01
    assert d.bias.mean() > 0.03
    # ...and it is specific to debutants, not the model's general optimism.
    assert d.bias.mean() > 4 * e.bias.mean()


def test_every_debutant_team_is_biased_the_same_way(debut_rows):
    """8 teams, 8 positive biases. A coin would not do this."""
    per = debut_rows[debut_rows.debut].groupby(["season", "team"]).bias.mean()
    assert len(per) >= 8
    assert (per > 0).all()


def test_the_bias_decays_as_the_book_learns_the_team(debut_rows):
    """The signature of a 1500 start: worst before any evidence, fading after.

    If this ever goes flat, the cause is no longer the initial rating and
    betting/history.py's explanation needs rewriting rather than patching.
    """
    d = debut_rows[debut_rows.debut].copy()
    d["gi"] = d.groupby(["season", "team"]).cumcount()
    early = d[d.gi <= 4].bias.mean()
    late = d[d.gi >= 19].bias.mean()
    assert early > late
    assert early > 0.07 and late < 0.05
