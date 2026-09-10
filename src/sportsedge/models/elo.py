"""Elo rating models.

NflEloModel: standard 2-outcome Elo for NFL moneyline win probability.
SoccerEloModel: Elo rating engine for team strength + a logistic regression
calibration layer (fit on prior-season data) that maps elo_diff -> P(home/draw/away).
This avoids hard-coding an unverified draw-probability formula; instead the
draw/win/loss split is learned from real historical outcomes, which is the
standard approach when you don't have a trusted closed-form model.
"""
from __future__ import annotations

from dataclasses import dataclass, field


def expected_score(rating_a: float, rating_b: float) -> float:
    """Standard Elo expected score for A vs B (no home adjustment applied here)."""
    return 1 / (1 + 10 ** (-(rating_a - rating_b) / 400))


@dataclass
class EloBook:
    """Tracks current Elo ratings per team, with a configurable default."""
    default_rating: float = 1500.0
    ratings: dict[str, float] = field(default_factory=dict)

    def get(self, team: str) -> float:
        return self.ratings.get(team, self.default_rating)

    def set(self, team: str, rating: float) -> None:
        self.ratings[team] = rating

    def regress_to_mean(self, factor: float) -> None:
        """Pull all ratings toward default_rating by `factor` (0..1) between seasons."""
        for team in list(self.ratings.keys()):
            r = self.ratings[team]
            self.ratings[team] = r + (self.default_rating - r) * factor


@dataclass
class NflEloModel:
    """Standard Elo with home-field advantage and optional margin-of-victory K scaling."""
    k: float = 20.0
    home_advantage: float = 55.0
    use_mov_multiplier: bool = False
    book: EloBook = field(default_factory=EloBook)

    def win_prob_home(self, home_team: str, away_team: str) -> float:
        home_r = self.book.get(home_team) + self.home_advantage
        away_r = self.book.get(away_team)
        return expected_score(home_r, away_r)

    def update(self, home_team: str, away_team: str, home_score: int, away_score: int) -> None:
        home_r = self.book.get(home_team)
        away_r = self.book.get(away_team)
        p_home = expected_score(home_r + self.home_advantage, away_r)

        if home_score > away_score:
            actual_home = 1.0
        elif home_score < away_score:
            actual_home = 0.0
        else:
            actual_home = 0.5

        k = self.k
        if self.use_mov_multiplier:
            margin = abs(home_score - away_score)
            elo_diff_winner = (home_r - away_r) if home_score >= away_score else (away_r - home_r)
            import math
            k *= math.log(margin + 1) * (2.2 / (elo_diff_winner * 0.001 + 2.2))

        delta = k * (actual_home - p_home)
        self.book.set(home_team, home_r + delta)
        self.book.set(away_team, away_r - delta)


@dataclass
class SoccerEloModel:
    """Elo strength engine for soccer. 3-way probabilities come from an external
    calibrator (see backtest.calibration) fit on (elo_diff, home_adv) -> outcome."""
    k: float = 20.0
    home_advantage: float = 60.0
    goal_diff_k_scaling: bool = True
    book: EloBook = field(default_factory=EloBook)

    def elo_diff(self, home_team: str, away_team: str) -> float:
        return (self.book.get(home_team) + self.home_advantage) - self.book.get(away_team)

    def update(self, home_team: str, away_team: str, home_score: int, away_score: int) -> None:
        home_r = self.book.get(home_team)
        away_r = self.book.get(away_team)
        p_home = expected_score(home_r + self.home_advantage, away_r)

        if home_score > away_score:
            actual_home = 1.0
        elif home_score < away_score:
            actual_home = 0.0
        else:
            actual_home = 0.5

        k = self.k
        if self.goal_diff_k_scaling:
            gd = abs(home_score - away_score)
            k *= (1.0 if gd <= 1 else (1.5 if gd == 2 else 1.75 + (gd - 3) / 8))

        delta = k * (actual_home - p_home)
        self.book.set(home_team, home_r + delta)
        self.book.set(away_team, away_r - delta)
