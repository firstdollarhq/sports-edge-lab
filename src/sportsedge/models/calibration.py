"""Maps Elo rating difference -> 3-way outcome probabilities via multinomial
logistic regression, fit on realized (elo_diff -> H/D/A) pairs from a prior
season. This is a standard "Elo for strength, logistic regression for outcome
calibration" pattern — it avoids hard-coding an assumed draw-probability curve.
"""
from __future__ import annotations

import numpy as np
from sklearn.linear_model import LogisticRegression


class SoccerOutcomeCalibrator:
    def __init__(self) -> None:
        self._model: LogisticRegression | None = None

    def fit(self, elo_diffs: list[float], outcomes: list[str]) -> None:
        """outcomes: list of 'H' | 'D' | 'A' aligned with elo_diffs."""
        x = np.array(elo_diffs).reshape(-1, 1)
        y = np.array(outcomes)
        self._model = LogisticRegression(max_iter=1000)
        self._model.fit(x, y)

    def predict_proba(self, elo_diff: float) -> dict[str, float]:
        if self._model is None:
            raise RuntimeError("Calibrator not fit yet")
        probs = self._model.predict_proba(np.array([[elo_diff]]))[0]
        return dict(zip(self._model.classes_, probs))
