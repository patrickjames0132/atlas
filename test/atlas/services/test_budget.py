"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
The adaptive landmark-budget serving paths (services/graph/budget.py).

The two ways to size a seed's landmark band, both pinned here (see
``docs/landmark-vocabulary.md`` for the vocabulary). Both are pure rules over a
ranked citer-year list, with no artifact involved:

* ``number_of_ranked_citers_before_a_single_year_overflows`` — the STOP rule, the
  serving rule for every whole-history pool via ``computed_cite_limit``.
* ``select_up_to_cap_per_year`` / ``select_landmarks`` — the SKIP rule, and the
  truncated-live-pool trim built on it.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

from collections import Counter

from atlas.integrations.caps import UNBOUNDED_LANDMARK_CAP
from atlas.services.graph import budget

# The STOP rule under its documented shorthand — the real name is deliberately
# long, and spelling it out at every assertion buries what is being asserted.
# STOP vs SKIP is the distinction docs/landmark-vocabulary.md is built around.
stop_rule = budget.number_of_ranked_citers_before_a_single_year_overflows


class TestStopRule:
    """The STOP rule — how deep into the ranking you get before a year overflows.

    The serving rule for every whole-history pool (via ``computed_cite_limit``,
    below), and formerly the retired regressor's **training label**. What a
    *truncated* live pool ships instead is the SKIP rule below.
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

    def test_payload_guard_clamps_the_count(self):
        # A spread pool that never overflows would ship whole — the payload
        # guard caps it (600 one-citer years measure 600, ship 500).
        never_overflowing = list(range(1000, 1600))
        assert budget.computed_cite_limit(never_overflowing) == UNBOUNDED_LANDMARK_CAP

    def test_spread_pool_ships_whole_under_the_guard(self):
        # Below the guard nothing clamps: the STOP count is the answer.
        assert budget.computed_cite_limit(list(range(1990, 2020))) == 30


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

    def test_payload_guard_caps_the_selection(self):
        """The guard is the cap, not infinity — as the model's clamp has always
        read it. Moot while this rule only saw the live path's truncated pool
        (the count is PER_YEAR_CAP x span, and a few years can't reach 500);
        load-bearing since the corpus path started computing over whole
        histories. Hawking's citers span 1954-2026, which would otherwise ship
        54 x 12 = 612 — the trim keeps the most-cited prefix.
        """
        hawking_span = [year for year in range(1954, 2027) for _ in range(50)]
        keep = budget.select_landmarks(hawking_span)
        assert len(keep) == UNBOUNDED_LANDMARK_CAP
        assert keep == sorted(keep)  # a prefix of the citation-ranked selection

    def test_empty_pool_ships_nothing(self):
        assert budget.select_landmarks([]) == []
