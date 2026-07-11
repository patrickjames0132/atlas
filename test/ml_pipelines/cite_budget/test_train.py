"""The cite-budget training pipeline (src/ml_pipelines/cite_budget): label logic + offline fit.

Fully offline — no OpenAlex calls. The density-label function is pure; the fit
runs on a tiny synthetic corpus so the pipeline (feature matrix → LinearRegression
→ serializable bundle) is exercised without the committed data or the network.
"""

from __future__ import annotations

import math

import numpy as np

from atlas.services.graph.budget import FEATURE_NAMES
from ml_pipelines.cite_budget import train
from ml_pipelines.cite_budget.features import DENSITY_CAP, DENSITY_CAP_GRID, density_budget


class TestDensityBudget:
    """``n*`` — the longest citation-ranked prefix before a year floods."""

    def test_stops_when_a_year_exceeds_the_cap(self):
        # Cap 2: the third 2020 (index 4) is the first to break it → prefix 4.
        years = [2020, 2019, 2020, 2018, 2020, 2017]
        assert density_budget(years, cap=2) == 4

    def test_returns_full_length_when_never_capped(self):
        assert density_budget([2020, 2019, 2018, 2017], cap=5) == 4

    def test_empty_pool_is_zero(self):
        assert density_budget([], cap=3) == 0

    def test_grid_includes_the_default_cap(self):
        assert DENSITY_CAP in DENSITY_CAP_GRID


class TestTrain:
    """The offline fit assembles a serializable, contract-shaped bundle."""

    @staticmethod
    def _corpus():
        # A monotone toy corpus (budget grows with age) — enough rows that
        # 5-fold CV keeps ≥2 samples per test fold, so R² is well-defined.
        ages_cites_budget = [
            (1, 100, 15), (4, 300, 30), (7, 500, 45), (11, 800, 60),
            (16, 1_500, 80), (21, 3_000, 100), (26, 5_000, 130), (31, 7_000, 150),
            (36, 9_000, 175), (41, 12_000, 200), (46, 15_000, 220), (51, 18_000, 240),
        ]
        return [
            {"year": 2026 - age, "cited_by_count": cites, "n_star": budget}
            for age, cites, budget in ages_cites_budget
        ]

    def test_build_matrix_uses_the_app_feature_contract(self):
        features, labels = train.build_matrix(self._corpus(), as_of_year=2026)
        assert features.shape == (12, len(FEATURE_NAMES))
        # First column is age (2026 - year); youngest seed first.
        assert features[0, 0] == 1.0 and features[-1, 0] == 51.0
        assert list(labels)[:2] == [15, 30]

    def test_bundle_is_serializable_and_contract_shaped(self):
        bundle = train.train(self._corpus(), as_of_year=2026)
        assert tuple(bundle["feature_names"]) == FEATURE_NAMES
        assert bundle["floor"] == 15  # min n_star
        assert bundle["n_seeds"] == 12
        assert math.isfinite(bundle["cv_r2"])  # a real score (folds ≥2 samples)
        # The estimator predicts, and age lifts the budget (positive age coef).
        prediction = bundle["model"].predict(np.array([[41.0, 4.0]]))
        assert prediction.shape == (1,)
        assert bundle["model"].coef_[0] > 0
