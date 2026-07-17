"""The adaptive landmark-budget serving paths (services/graph/budget.py).

The ways to size a seed's landmark band, all pinned here (see
``docs/landmark-vocabulary.md`` for the vocabulary):

* **Computed** — the two pure rules, no artifact involved:
  ``number_of_ranked_citers_before_a_single_year_overflows`` (the STOP rule —
  the serving rule for every whole-history pool via ``computed_cite_limit``,
  and the retired model's training label) and ``select_up_to_cap_per_year`` /
  ``select_landmarks`` (the SKIP rule and the truncated-live-pool trim built
  on it).
* **Predicted** (``predicted_budget``) — the *trained model*, retired from
  serving in v5.13.0 but still the ``latest_gap`` collector's dependency and
  the label's derivation record: these load the committed
  ``src/ml_pipelines/cite_budget/model.joblib`` and assert the seed → budget
  mapping, so a retrain that moves the worked-example seeds trips them. The
  reference year is pinned (not ``today``) so the age-based pins stay stable
  as the clock advances.
"""

from __future__ import annotations

import math
from collections import Counter

import pytest

from atlas.config import config
from atlas.integrations import openalex
from atlas.services.graph import budget

# Fix the age reference so pins don't drift with the wall clock; the
# worked-example seeds' real publication years are used against it.
AS_OF = 2026

# The STOP rule under its documented shorthand — the real name is deliberately
# long, and spelling it out at every assertion buries what is being asserted.
# STOP vs SKIP is the distinction docs/landmark-vocabulary.md is built around.
stop_rule = budget.number_of_ranked_citers_before_a_single_year_overflows


@pytest.fixture(autouse=True)
def _adaptive_unbounded(monkeypatch):
    """Patrick's live shape: adaptive on, cite_limit null (unbounded ceiling)."""
    monkeypatch.setattr(config.graph, "adaptive_cite_limit", True)
    monkeypatch.setattr(config.graph, "cite_limit", None)
    budget._reset_model_cache()  # a prior test may have swapped load_model
    yield
    budget._reset_model_cache()


def limit(year: int, citation_count: int, ceiling: int | None = None) -> int | None:
    """The model's budget for a seed published in ``year`` with ``citation_count``."""
    return budget.predicted_budget(year, citation_count, as_of_year=AS_OF, ceiling=ceiling)


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


class TestPredictedBudget:
    """Seed → clamped budget, via the trained model (retired from serving; the
    ``latest_gap`` collector still depends on these exact mappings)."""

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

    def test_budget_never_exceeds_the_ceiling(self):
        # An old, well-cited seed predicts above the ceiling — clamps to it.
        assert limit(1975, 12_959, ceiling=40) == 40

    def test_budget_never_drops_below_the_floor(self):
        floor = budget.load_model()["floor"]
        # A brand-new, uncited seed floors at the model's floor, not below.
        assert limit(AS_OF, 0) == floor

    def test_unloadable_model_predicts_nothing(self, monkeypatch):
        # A missing/broken artifact must degrade to None, not crash the caller.
        monkeypatch.setattr(budget, "load_model", lambda: None)
        assert limit(1975, 5_000) is None


class TestStopRule:
    """The STOP rule — how deep into the ranking you get before a year overflows.

    The serving rule for every whole-history pool (via ``computed_cite_limit``,
    below) AND the retired model's **training label**
    (``test/ml_pipelines/cite_budget/test_train.py`` pins that training and the
    app share this one function). What a *truncated* live pool ships instead is
    the SKIP rule below.
    """

    def test_stops_when_a_year_exceeds_the_cap(self):
        # Cap 2: the third 2020 (index 4) is the first to break it → stops at 4.
        years = [2020, 2019, 2020, 2018, 2020, 2017]
        assert stop_rule(years, cap=2) == 4

    def test_returns_full_length_when_never_capped(self):
        assert stop_rule([2020, 2019, 2018, 2017], cap=5) == 4

    def test_empty_pool_is_zero(self):
        assert stop_rule([], cap=3) == 0

    def test_a_single_flooded_year_yields_exactly_the_cap(self):
        # The recency-capped fallback's shape: every citer in one year.
        assert stop_rule([2025] * 500, cap=12) == 12

    def test_undated_citers_take_a_slot_but_crowd_no_year(self):
        # An undated citer can't pile into a year, so it never trips the cap —
        # but it still occupies a place in the count.
        assert stop_rule([2020, None, 2020, None, 2020], cap=2) == 4
        assert stop_rule([None] * 50, cap=2) == 50


class TestComputedCiteLimit:
    """The computed budget — the STOP rule as served to whole-history pools
    (the corpus, OpenAlex's probe, a complete live S2 pool)."""

    def test_returns_the_stop_count(self):
        # 500 same-year citers overflow immediately: the count is the cap.
        assert budget.computed_cite_limit([2025] * 500) == budget.PER_YEAR_CAP

    def test_ceiling_clamps_the_count(self, monkeypatch):
        monkeypatch.setattr(config.graph, "cite_limit", 5)
        # A spread pool that never overflows would ship whole — the ceiling caps it.
        assert budget.computed_cite_limit(list(range(1990, 2020))) == 5

    def test_toggle_off_declines_so_the_flat_limit_applies(self, monkeypatch):
        monkeypatch.setattr(config.graph, "adaptive_cite_limit", False)
        assert budget.computed_cite_limit([2025] * 500) is None

    def test_needs_no_model_artifact(self, monkeypatch):
        # Computing must not depend on the trained bundle at all.
        monkeypatch.setattr(budget, "load_model", lambda: None)
        assert budget.computed_cite_limit([2025] * 500) == budget.PER_YEAR_CAP


class TestSkipRule:
    """The SKIP rule — up to the cap per year, walking on past full years.

    What the live S2 fallback's truncated pools are handed, via
    ``select_landmarks``.
    """

    def test_caps_each_year_without_ending_the_walk(self):
        # THE bug the STOP rule has: 2020 floods, and STOP would quit dead there
        # — losing every later year. SKIP steps over and carries on.
        years = [2020] * 30 + [2024] * 5
        keep = budget.select_landmarks(years)
        picked = [years[index] for index in keep]
        assert picked == [2020] * budget.PER_YEAR_CAP + [2024] * 5
        # ...where the STOP rule quits at exactly the cap, stranding 2024.
        assert stop_rule(years, budget.PER_YEAR_CAP) == budget.PER_YEAR_CAP

    def test_bands_every_year_evenly(self):
        # DQN's real shape: a deep pool spanning several years, each over-full.
        years = [year for year in range(2019, 2026) for _ in range(500)]
        keep = budget.select_landmarks(years)
        per_year = Counter(years[index] for index in keep)
        assert set(per_year) == set(range(2019, 2026))
        assert set(per_year.values()) == {budget.PER_YEAR_CAP}

    def test_indices_are_ascending_so_the_band_stays_citation_ranked(self):
        # The reveal slider walks by rank, so the shipped order must not be
        # reshuffled into year order.
        years = [2020, 2024, 2020, 2025, 2024]
        assert budget.select_landmarks(years) == [0, 1, 2, 3, 4]

    def test_a_sparse_pool_ships_whole(self):
        years = [2020, 2021, 2022]
        assert budget.select_landmarks(years) == [0, 1, 2]

    def test_undated_citers_are_dropped_not_banded(self):
        # A landmark is "top-cited citer OF YEAR Y" — an undated citer can't make
        # that claim, and can't be drawn on a time axis. Bucketing them shipped a
        # guaranteed PER_YEAR_CAP of junk onto a single x (a bar through the seed).
        assert budget.select_landmarks([None] * 50) == []

    def test_undated_citers_dont_consume_a_dated_years_slots(self):
        years = [None, 2020, None, 2021, None]
        assert budget.select_landmarks(years) == [1, 3]

    def test_ceiling_keeps_the_most_cited(self, monkeypatch):
        monkeypatch.setattr(config.graph, "cite_limit", 5)
        years = [year for year in range(2019, 2026) for _ in range(500)]
        keep = budget.select_landmarks(years)
        assert keep == [0, 1, 2, 3, 4]  # a prefix of the citation-ranked selection

    def test_unset_cite_limit_still_means_the_unbounded_cap(self, monkeypatch):
        """An unset limit is the unbounded cap, not infinity — as the model's clamp
        has always read it. Moot while this rule only saw the live path's truncated
        pool (the count is PER_YEAR_CAP x span, and a few years can't reach 500);
        load-bearing since the corpus path started computing over whole histories.
        Hawking's citers span 1954-2026, which would otherwise ship 54 x 12 = 612.
        """
        monkeypatch.setattr(config.graph, "cite_limit", None)
        hawking_span = [year for year in range(1954, 2027) for _ in range(50)]
        keep = budget.select_landmarks(hawking_span)
        assert len(keep) == openalex.UNBOUNDED_LANDMARK_CAP
        # ...and the two sizings agree on what "unset" means.
        assert budget.predicted_budget(1975, 10_825, as_of_year=2026) <= (
            openalex.UNBOUNDED_LANDMARK_CAP)

    def test_toggle_off_declines_so_the_flat_limit_applies(self, monkeypatch):
        monkeypatch.setattr(config.graph, "adaptive_cite_limit", False)
        assert budget.select_landmarks([2025] * 400) is None

    def test_needs_no_model_artifact(self, monkeypatch):
        # The selection path must not depend on the trained bundle at all.
        monkeypatch.setattr(budget, "load_model", lambda: None)
        assert len(budget.select_landmarks([2025] * 400)) == budget.PER_YEAR_CAP

    def test_empty_pool_ships_nothing(self):
        assert budget.select_landmarks([]) == []
