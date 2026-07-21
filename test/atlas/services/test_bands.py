"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
The adaptive latest-band serving path (services/graph/bands.py).

Exercises the tail-edge rule: the pure density detector (:func:`bands.tail_edge`)
and the served :func:`bands.earliest_band_year`. Behavior tests monkeypatch a
controlled bundle so they don't drift when the model is retrained; one test loads
the committed artifact to pin its contract shape.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

import pytest

from atlas.services.graph import bands

# A landmark-era max year for the served-rule tests.
LANDMARK_MAX = 2024


@pytest.fixture(autouse=True)
def _fresh_model_cache():
    """Reset the memoized model around each test (one may swap load_model)."""
    bands._reset_model_cache()
    yield
    bands._reset_model_cache()


def _use_bundle(monkeypatch, tau, max_span):
    """Pin a controlled model bundle so a retrain can't shift these assertions."""
    monkeypatch.setattr(bands, "load_model",
                        lambda: {"rule": bands.RULE_NAME, "tau": tau, "max_span": max_span})


def start(years):
    """The model's band start for a landmark-year distribution."""
    return bands.earliest_band_year(years, LANDMARK_MAX)


class TestTailEdge:
    """The shared density rule (training and serving both call this)."""

    def test_returns_the_most_recent_still_dense_year(self):
        # counts: 2010=5, 2011=5, 2020=3; peak 5, tau 0.5 -> threshold 2.5.
        # 2020 (count 3) clears it, so the recent dense year is the edge.
        years = [2010]*5 + [2011]*5 + [2020]*3
        assert bands.tail_edge(years, 0.5) == 2020

    def test_ignores_sparse_recent_stragglers(self):
        # Same bulk but only ONE 2020 citer (below the 2.5 threshold): the edge
        # falls back to the dense bulk, not the lone recent straggler.
        years = [2010]*5 + [2011]*5 + [2020]
        assert bands.tail_edge(years, 0.5) == 2011

    def test_threshold_is_relative_to_this_seeds_peak(self):
        # A low tau admits thinner years as "dense" — pushing the edge later.
        years = [2010]*5 + [2011]*5 + [2020]*2
        assert bands.tail_edge(years, 0.2) == 2020   # threshold 1.0
        assert bands.tail_edge(years, 0.5) == 2011    # threshold 2.5


class TestLoadModel:
    """The committed artifact loads and satisfies the serving contract."""

    def test_bundle_shape(self):
        bundle = bands.load_model()
        assert bundle is not None
        assert bundle["rule"] == bands.RULE_NAME
        assert 0.0 < float(bundle["tau"]) < 1.0
        assert int(bundle["max_span"]) >= 1


class TestEarliestBandYear:
    """Landmark distribution → adaptive band start, via the tail-edge rule."""

    def test_old_cluster_is_capped_at_max_span(self, monkeypatch):
        _use_bundle(monkeypatch, tau=0.5, max_span=5)  # floor = 2024-5+1 = 2020
        old_cluster = [2008]*4 + [2010]*4 + [2012]*4 + [2013, 2014]  # edge ~2012
        assert start(old_cluster) == 2020  # density edge is older than the floor -> capped

    def test_young_cluster_starts_recent_with_no_only_widen(self, monkeypatch):
        _use_bundle(monkeypatch, tau=0.5, max_span=5)  # floor 2020
        young_cluster = [2022]*4 + [2023]*4 + [2024]*4 + [2020, 2021]
        # The edge (2024) sits AFTER the old fixed start (2020); with no only-widen
        # clamp the bands start there — a tight recent frontier, three bands.
        assert start(young_cluster) == 2024

    def test_misdated_outlier_does_not_move_the_boundary(self, monkeypatch):
        _use_bundle(monkeypatch, tau=0.5, max_span=9)  # floor 2016
        clean = [2008]*5 + [2010]*5 + [2012]*5 + [2013, 2014]  # peak 5 -> threshold 2.5
        poisoned = clean + [2026, 2026]  # two misdated-future citers, count 2 < 2.5
        assert start(clean) == start(poisoned)

    def test_too_few_dated_years_returns_none(self, monkeypatch):
        _use_bundle(monkeypatch, tau=0.5, max_span=7)
        assert start([2010, 2011, 2012]) is None

    def test_undated_years_are_dropped_before_the_count(self, monkeypatch):
        _use_bundle(monkeypatch, tau=0.5, max_span=7)
        assert start([0, 0, 2010, 2011, 2012]) is None  # only 3 dated -> below the min

    def test_unloadable_model_returns_none(self, monkeypatch):
        monkeypatch.setattr(bands, "load_model", lambda: None)
        assert start([2010]*5 + [2011]*5 + [2012]*5) is None
