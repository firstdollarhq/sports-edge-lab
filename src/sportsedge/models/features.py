"""Does information Elo cannot see reorder games better than Elo alone?

Run 11 produced this project's first hard bound: over the canonical NFL window
the model's AUC is 0.678 against the market's 0.724, and AUC is invariant under
any strictly monotone transform of the predictions. So every change this
project had proposed -- threshold moves, shrinkage, Platt, isotonic, the
fee-inclusive edge -- was ruled out at once, because none of them reorder
anything. Run 11 closed by naming what would be left: "injuries, rest, travel,
weather, personnel -- things the closing line prices and a team-strength Elo
does not see."

This module is that test, and nothing more than that test. It does not replace
the rating engine; it takes the SAME walk-forward Elo diff the engine already
computes and asks whether a logistic fit on [elo_diff + context] ranks games
better than elo_diff alone -- and, the question that actually matters, whether
it closes any of the gap to the closing line.

## The control that makes the result readable

A logistic regression on elo_diff ALONE is a strictly monotone transform of
elo_diff, so its AUC must equal baseline Elo's *exactly*. That is not a
nice-to-have: it is the assertion that this file measures what it claims to.
If TIER_ELO_ONLY ever disagrees with the baseline AUC, the harness is leaking
something -- a refit boundary in the wrong place, a feature standardised on
the test set, a sort that is not chronological -- and every other tier's number
is void. `test_features.py` pins it.

## Provenance tiers, because the features are not equally honest

The tiers exist because two of these inputs are not knowable when this project
actually prices a game, and pooling them would let an optimistic number hide
inside a clean one:

  schedule  rest, short week, divisional, neutral site. SCHEDULE facts, known
            weeks ahead. No lookahead risk whatsoever. This is the only tier
            whose result could be deployed as-is.
  weather   adds roof/temp/wind. nflverse records the conditions the game was
            PLAYED in; a model pricing at T-8h has a forecast instead. Mildly
            optimistic -- an upper bound on what weather could contribute.
  qb        adds "did this team's starting QB change since its last game".
            nflverse names the QB who actually STARTED. Inactives post ~90
            minutes before kickoff, so this is nearly knowable, but it is not
            knowable when this project prices. Also optimistic.

Read the tiers apart. A gain that appears only in `weather` or `qb` is a gain
that may not survive contact with a real pricing clock.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

# Elo diffs run to several hundred rating points; the context features are
# 0/1 flags and small day counts. Dividing by a fixed, documented scale keeps
# the fit conditioned without standardising on statistics the test set is part
# of -- which would be exactly the leak the control above is meant to catch.
_ELO_SCALE = 100.0
_REST_SCALE = 7.0

TIER_ELO_ONLY = "elo_only"
TIER_SCHEDULE = "schedule"
TIER_WEATHER = "weather"
TIER_QB = "qb"

TIERS = (TIER_ELO_ONLY, TIER_SCHEDULE, TIER_WEATHER, TIER_QB)

_SCHEDULE_FEATURES = ("rest_diff", "home_short_week", "away_short_week",
                      "div_game", "neutral_site")
_WEATHER_FEATURES = ("is_outdoor", "wind_mph", "temp_dev")
_QB_FEATURES = ("home_qb_change", "away_qb_change")

_TIER_FEATURES = {
    TIER_ELO_ONLY: (),
    TIER_SCHEDULE: _SCHEDULE_FEATURES,
    TIER_WEATHER: _SCHEDULE_FEATURES + _WEATHER_FEATURES,
    TIER_QB: _SCHEDULE_FEATURES + _WEATHER_FEATURES + _QB_FEATURES,
}

# A short week is the Thursday game (and the Saturday-after-Thursday variants).
# nflverse reports rest in days since the team's previous game; a normal week
# is 7, a bye is 13-14.
_SHORT_WEEK_DAYS = 6


def _f(value, default=0.0) -> float:
    """nflverse ships pandas NA, numpy nan and None in these columns."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return default
    try:
        if pd.isna(value):
            return default
    except (TypeError, ValueError):
        pass
    return float(value)


def _is_outdoor(roof) -> bool:
    """`roof` is outdoors | open | closed | dome. Only the first two are
    exposed to weather; 'open' is a retractable roof that was open."""
    if roof is None:
        return False
    try:
        if pd.isna(roof):
            return False
    except (TypeError, ValueError):
        pass
    return str(roof).strip().lower() in ("outdoors", "open")


class ContextFeatureModel:
    """Elo + pre-kickoff context, fit walk-forward and refit at season breaks.

    Usage is driven by `backtest.engine.backtest_nfl`, one game at a time and
    strictly in chronological order:

        p = model.predict(game_row, elo_diff)   # None until it has a fit
        model.observe(game_row, elo_diff, won)  # after the game is scored
        model.start_season()                    # refits on everything observed

    The fit only ever sees games it has already been asked to predict, so there
    is no lookahead by construction. Within a season the coefficients are
    frozen; they are refit at each season boundary on every completed season so
    far. `min_train_games` keeps the first seasons from being priced off a fit
    with no data behind it -- those games return None and are excluded from the
    comparison rather than being silently scored against a degenerate model.
    """

    def __init__(self, tier: str = TIER_SCHEDULE, min_train_games: int = 400,
                 C: float = 1.0):
        """`C` is the inverse L2 penalty. It exists so that "your fit was
        overfit" is a testable objection rather than an argument: as C -> 0 the
        context coefficients are crushed toward zero and the tier must converge
        on the elo_only control. A tier that never beats the control at ANY C
        has not been beaten by regularisation, it has no signal to find."""
        if tier not in _TIER_FEATURES:
            raise ValueError(f"unknown tier {tier!r}; expected one of {TIERS}")
        self.tier = tier
        self.feature_names = ("elo_diff",) + _TIER_FEATURES[tier]
        self.min_train_games = min_train_games
        self.C = C
        self._X: list[list[float]] = []
        self._y: list[int] = []
        self._clf: LogisticRegression | None = None
        # Last starting QB seen for each team, maintained in prediction order
        # so the "did the starter change" flag never consults a future game.
        self._last_qb: dict[str, str] = {}

    # -- features -------------------------------------------------------------

    def features(self, game: pd.Series, elo_diff: float) -> list[float]:
        home_rest = _f(game.get("home_rest"), 7.0)
        away_rest = _f(game.get("away_rest"), 7.0)
        outdoor = _is_outdoor(game.get("roof"))

        all_feats = {
            "elo_diff": elo_diff / _ELO_SCALE,
            "rest_diff": (home_rest - away_rest) / _REST_SCALE,
            "home_short_week": 1.0 if home_rest <= _SHORT_WEEK_DAYS else 0.0,
            "away_short_week": 1.0 if away_rest <= _SHORT_WEEK_DAYS else 0.0,
            "div_game": _f(game.get("div_game")),
            "neutral_site": _f(game.get("neutral_site")),
            "is_outdoor": 1.0 if outdoor else 0.0,
            # Indoor games have no wind and no meaningful temperature. Zero is
            # the honest encoding: `is_outdoor` carries the indoor/outdoor
            # distinction, so these two only ever vary among exposed games.
            "wind_mph": _f(game.get("wind")) / 10.0 if outdoor else 0.0,
            "temp_dev": abs(_f(game.get("temp"), 60.0) - 60.0) / 30.0 if outdoor else 0.0,
            "home_qb_change": self._qb_change(game, "home"),
            "away_qb_change": self._qb_change(game, "away"),
        }
        return [all_feats[name] for name in self.feature_names]

    def _qb_change(self, game: pd.Series, side: str) -> float:
        team = game.get(f"{side}_team")
        qb = game.get(f"{side}_qb_id")
        if qb is None or team is None:
            return 0.0
        try:
            if pd.isna(qb) or pd.isna(team):
                return 0.0
        except (TypeError, ValueError):
            pass
        previous = self._last_qb.get(str(team))
        # No previous start on record is not a change; it is an absence of
        # evidence, and encoding it as 1 would mark every team's first game of
        # the sample as a QB change.
        if previous is None:
            return 0.0
        return 1.0 if str(qb) != previous else 0.0

    # -- walk-forward lifecycle ----------------------------------------------

    def predict(self, game: pd.Series, elo_diff: float) -> float | None:
        if self._clf is None:
            return None
        x = np.asarray([self.features(game, elo_diff)], dtype=float)
        return float(self._clf.predict_proba(x)[0, 1])

    def observe(self, game: pd.Series, elo_diff: float, home_won: int) -> None:
        self._X.append(self.features(game, elo_diff))
        self._y.append(int(home_won))
        for side in ("home", "away"):
            team, qb = game.get(f"{side}_team"), game.get(f"{side}_qb_id")
            try:
                if team is not None and qb is not None and not pd.isna(qb):
                    self._last_qb[str(team)] = str(qb)
            except (TypeError, ValueError):
                pass

    def start_season(self) -> bool:
        """Refit on every game observed so far. True if a fit is now in place."""
        if len(self._y) < self.min_train_games or len(set(self._y)) < 2:
            return False
        clf = LogisticRegression(max_iter=1000, C=self.C)
        clf.fit(np.asarray(self._X, dtype=float), np.asarray(self._y, dtype=int))
        self._clf = clf
        return True

    @property
    def coefficients(self) -> dict[str, float] | None:
        if self._clf is None:
            return None
        return dict(zip(self.feature_names, (float(c) for c in self._clf.coef_[0])))

    @property
    def n_train(self) -> int:
        return len(self._y)
