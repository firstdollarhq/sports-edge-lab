from sportsedge.models.elo import EloBook, NflEloModel, expected_score


def test_expected_score_equal_ratings_is_half():
    assert abs(expected_score(1500, 1500) - 0.5) < 1e-9


def test_expected_score_higher_rating_favored():
    assert expected_score(1600, 1500) > 0.5


def test_elo_book_default_rating():
    book = EloBook(default_rating=1500)
    assert book.get("UNKNOWN_TEAM") == 1500


def test_elo_book_regress_to_mean():
    book = EloBook(default_rating=1500)
    book.set("A", 1700)
    book.regress_to_mean(0.5)
    assert book.get("A") == 1600


def test_nfl_elo_update_winner_gains_rating():
    model = NflEloModel(k=20, home_advantage=0)
    model.book.set("HOME", 1500)
    model.book.set("AWAY", 1500)
    model.update("HOME", "AWAY", home_score=24, away_score=17)
    assert model.book.get("HOME") > 1500
    assert model.book.get("AWAY") < 1500


def test_nfl_elo_zero_sum():
    model = NflEloModel(k=20, home_advantage=0)
    model.book.set("HOME", 1520)
    model.book.set("AWAY", 1480)
    before = model.book.get("HOME") + model.book.get("AWAY")
    model.update("HOME", "AWAY", home_score=10, away_score=20)
    after = model.book.get("HOME") + model.book.get("AWAY")
    assert abs(before - after) < 1e-9


def test_nfl_elo_home_advantage_raises_home_win_prob():
    model_no_adv = NflEloModel(home_advantage=0)
    model_adv = NflEloModel(home_advantage=65)
    model_no_adv.book.set("HOME", 1500)
    model_no_adv.book.set("AWAY", 1500)
    model_adv.book.set("HOME", 1500)
    model_adv.book.set("AWAY", 1500)
    assert model_adv.win_prob_home("HOME", "AWAY") > model_no_adv.win_prob_home("HOME", "AWAY")
