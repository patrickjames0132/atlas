"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
The per-request build shape: which rules each mode injects, and its cache key.

The behavioral claims worth pinning are that **adaptive mode is byte-identical
to the pre-shape app** (same rules, same cache key — so existing snapshots still
hit) and that **non-adaptive mode declines every adaptive rule**, which is how it
reaches the traversals' flat payload-guard fallback without any traversal
learning about shapes.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

from atlas.integrations.caps import LATEST_NODES_PER_BAND, LATEST_NUMBER_OF_BANDS
from atlas.services.graph import bands, budget
from atlas.services.graph.shape import BuildShape


def test_adaptive_is_the_default_and_injects_the_fitted_rules():
    shape = BuildShape()
    assert shape.adaptive is True
    # The app's own sizing: the STOP rule and the fitted tau rule, unchanged.
    assert shape.landmark_budget() is budget.computed_cite_limit
    assert shape.band_start() is bands.earliest_band_year
    assert shape.landmark_select() is budget.select_landmarks
    # Band dimensions default to the shared caps constants.
    assert shape.number_of_bands == LATEST_NUMBER_OF_BANDS
    assert shape.nodes_per_band == LATEST_NODES_PER_BAND


def test_non_adaptive_declines_every_sizing_rule():
    """Declining is what lands each traversal on its flat payload-guard path."""
    shape = BuildShape(adaptive=False)
    # The budget rule answers None for any pool, so the traversal ships the
    # ranked prefix trimmed to UNBOUNDED_LANDMARK_CAP — "all nodes, guard only".
    assert shape.landmark_budget()([2019, 2020, 2020, None]) is None
    assert shape.landmark_budget()([]) is None
    # The truncated-pool SKIP selector is dropped entirely rather than replaced.
    assert shape.landmark_select() is None


def test_non_adaptive_band_start_answers_the_users_year_for_every_seed():
    shape = BuildShape(adaptive=False, cluster_start=2015)
    rule = shape.band_start()
    assert rule is not None
    # Same answer whatever the seed's landmark distribution looks like — that's
    # the point of turning adaptive off.
    assert rule([2019, 2020, 2021], 2024) == 2015
    assert rule([], 1998) == 2015


def test_non_adaptive_without_a_cluster_start_keeps_the_fixed_span():
    """No start named -> no rule, so the traversal uses number_of_bands."""
    assert BuildShape(adaptive=False, cluster_start=None).band_start() is None


def test_adaptive_cache_suffix_is_empty_so_old_snapshots_still_hit():
    """The default path's key must be byte-identical to the pre-shape key."""
    assert BuildShape().cache_suffix() == ""
    # Even with band fields set: adaptive ignores them, so they must not leak
    # into the key and split the cache for builds that behave identically.
    assert BuildShape(cluster_start=2015, number_of_bands=9).cache_suffix() == ""


def test_distinct_non_adaptive_shapes_get_distinct_cache_keys():
    base = BuildShape(adaptive=False, cluster_start=2015, number_of_bands=5, nodes_per_band=50)
    assert base.cache_suffix() != ""
    assert base.cache_suffix() != BuildShape().cache_suffix()
    # Each field participates — otherwise flipping it would serve a stale graph.
    assert base.cache_suffix() != base.__class__(
        adaptive=False, cluster_start=2016, number_of_bands=5, nodes_per_band=50
    ).cache_suffix()
    assert base.cache_suffix() != BuildShape(
        adaptive=False, cluster_start=2015, number_of_bands=6, nodes_per_band=50
    ).cache_suffix()
    assert base.cache_suffix() != BuildShape(
        adaptive=False, cluster_start=2015, number_of_bands=5, nodes_per_band=80
    ).cache_suffix()
    # Stable across instances — the key can't depend on object identity.
    assert base.cache_suffix() == BuildShape(
        adaptive=False, cluster_start=2015, number_of_bands=5, nodes_per_band=50
    ).cache_suffix()


def test_an_absent_cluster_start_is_distinguishable_from_a_year():
    """"auto" must not collide with a real year's key."""
    auto = BuildShape(adaptive=False, cluster_start=None).cache_suffix()
    year = BuildShape(adaptive=False, cluster_start=2015).cache_suffix()
    assert auto != year
