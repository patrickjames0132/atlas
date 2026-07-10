"""The adaptive landmark-budget serving path (services/graph/budget.py).

Exercises the *trained model* end-to-end: these tests load the committed
``ml/models/cite_budget.joblib`` and assert the seed → budget mapping, so a
retrain that moves the anchors will trip them. The reference year is pinned
(not ``today``) so the age-based pins stay stable as the clock advances.
"""

from __future__ import annotations

import math

import pytest

from atlas.config import config
from atlas.services.graph import budget

# Fix the age reference so pins don't drift with the wall clock; the anchors'
# real publication years are used against it.
AS_OF = 2026


@pytest.fixture(autouse=True)
def _adaptive_unbounded(monkeypatch):
    """Patrick's live shape: adaptive on, cite_limit null (unbounded ceiling)."""
    monkeypatch.setattr(config.graph, "adaptive_cite_limit", True)
    monkeypatch.setattr(config.graph, "cite_limit", None)
    budget._reset_model_cache()  # a prior test may have swapped load_model
    yield
    budget._reset_model_cache()


def limit(year: int, citation_count: int) -> int | None:
    """The model's budget for a seed published in ``year`` with ``citation_count``."""
    return budget.adaptive_cite_limit(
        {"year": year, "citation_count": citation_count}, as_of_year=AS_OF
    )


class TestComputeFeatures:
    """The shared feature contract (training and serving both call this)."""

    def test_feature_order_and_values(self):
        # [age, log10(cites + 1)] in FEATURE_NAMES order.
        features = budget.compute_features(2016, 999, as_of_year=AS_OF)
        assert budget.FEATURE_NAMES == ("age", "log_cites")
        assert features == [10.0, pytest.approx(math.log10(1000))]

    def test_future_dated_seed_floors_age_at_zero(self):
        # OpenAlex sometimes mis-dates a paper into the future — age can't go < 0.
        assert budget.compute_features(AS_OF + 3, 100, as_of_year=AS_OF)[0] == 0.0


class TestLoadModel:
    """The committed artifact loads and satisfies the serving contract."""

    def test_bundle_shape(self):
        bundle = budget.load_model()
        assert bundle is not None
        assert tuple(bundle["feature_names"]) == budget.FEATURE_NAMES
        assert isinstance(bundle["floor"], int)
        assert hasattr(bundle["model"], "predict")


class TestAdaptiveCiteLimit:
    """Seed → clamped budget, via the trained model."""

    def test_anchor_seeds_match_the_trained_model(self):
        # The four working anchors — the same predictions the notebook and the
        # metadata.json coefficients produce (AIAYN carries OpenAlex's 2025
        # mis-dating, which is exactly what the deployed model must handle).
        assert limit(1975, 12_959) == 160  # Hawking Radiation
        assert limit(2015, 30_115) == 60   # DQN
        assert limit(2018, 352) == 41      # QMIX
        assert limit(2025, 6_583) == 30    # Attention Is All You Need

    def test_older_seed_earns_a_larger_budget(self):
        # Age carries the signal (r≈0.84): hold citations fixed, older wins.
        assert limit(1986, 5_000) > limit(2021, 5_000)

    def test_budget_never_exceeds_the_ceiling(self, monkeypatch):
        monkeypatch.setattr(config.graph, "cite_limit", 40)
        # An old, well-cited seed predicts above the ceiling — clamps to it.
        assert limit(1975, 12_959) == 40

    def test_budget_never_drops_below_the_floor(self):
        floor = budget.load_model()["floor"]
        # A brand-new, uncited seed floors at the model's floor, not below.
        assert limit(AS_OF, 0) == floor

    def test_toggle_off_passes_cite_limit_through(self, monkeypatch):
        monkeypatch.setattr(config.graph, "adaptive_cite_limit", False)
        assert limit(1975, 5_000) is None
        monkeypatch.setattr(config.graph, "cite_limit", 150)
        assert limit(1975, 5_000) == 150

    def test_missing_year_passes_cite_limit_through(self, monkeypatch):
        monkeypatch.setattr(config.graph, "cite_limit", 150)
        assert budget.adaptive_cite_limit(
            {"year": None, "citation_count": 5_000}, as_of_year=AS_OF) == 150

    def test_unloadable_model_falls_back_to_cite_limit(self, monkeypatch):
        # A missing/broken artifact must degrade to the flat limit, not crash.
        monkeypatch.setattr(config.graph, "cite_limit", 150)
        monkeypatch.setattr(budget, "load_model", lambda: None)
        assert limit(1975, 5_000) == 150
