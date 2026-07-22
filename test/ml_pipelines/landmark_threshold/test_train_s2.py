"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
The S2 threshold trainer (src/ml_pipelines/landmark_threshold): the vectorized fit.

Fully offline and corpus-free — the fit math runs on hand-built :class:`Seed`
records, so the predicate, the band penalty, and the coarse-to-fine search are
exercised without the committed corpus or the DuckDB corpus.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

import numpy as np

from ml_pipelines.landmark_threshold import train_s2


def _seed(corpus_id: int, cited_by: int, citers: list[tuple[int, int, int]],
          *, is_worked_example: bool = False, total: int | None = None) -> train_s2.Seed:
    """Build one :class:`Seed` from ``(age, citer_cited_by, count)`` triples."""
    ages = np.array([age for age, _cited, _count in citers], dtype=np.float64)
    cited = np.array([cited for _age, cited, _count in citers], dtype=np.float64)
    counts = np.array([count for _age, _cited, count in citers], dtype=np.float64)
    return train_s2.Seed(
        corpus_id=corpus_id, label=f"seed{corpus_id}", is_worked_example=is_worked_example,
        year=2026, cited_by=cited_by, total_citers=total or int(counts.sum()),
        citer_ages=ages, citer_cited_by=cited, citer_counts=counts,
    )


class TestPredicate:
    """The vectorized landmark-count predicate matches the rule by hand."""

    def test_bar_combines_floor_age_and_seed_scale(self):
        # One median seed (ratio 1, so seed scale 1) with citers all at age 0:
        # bar = max(floor, a*1^p*1) = max(2, 3) = 3. Citers >= 3 pass.
        seed = _seed(1, cited_by=100, citers=[(0, 10, 1), (0, 5, 1), (0, 2, 4)])
        inputs = train_s2.build_inputs([seed])
        counts = train_s2.landmark_counts(inputs, scale=3.0, exponent=1.0, beta=0.0, floor=2.0)
        assert counts[0] == 2  # the 10 and the 5 clear 3; the four 2s don't

    def test_age_raises_the_bar(self):
        # Same seed, citers at age 0 and age 3. With a=2, p=1 the bars are 2 and
        # 2*(4)=8: a cited_by-6 citer is a landmark when young, not when old.
        seed = _seed(1, cited_by=100, citers=[(0, 6, 1), (3, 6, 1)])
        inputs = train_s2.build_inputs([seed])
        counts = train_s2.landmark_counts(inputs, scale=2.0, exponent=1.0, beta=0.0, floor=2.0)
        assert counts[0] == 1

    def test_seed_scale_pins_the_median_to_one(self):
        # Three seeds; the median cited_by is 100, so its ratio is 1 exactly.
        seeds = [_seed(1, 10, [(0, 5, 1)]), _seed(2, 100, [(0, 5, 1)]),
                 _seed(3, 1_000, [(0, 5, 1)])]
        inputs = train_s2.build_inputs(seeds)
        assert inputs.median_seed == 100.0
        assert inputs.seed_ratio[1] == 1.0


class TestBandPenalty:
    """The objective is zero in band, positive outside, and forgives scarcity."""

    def test_zero_inside_the_band(self):
        counts = np.array([20.0, 30.0, 40.0])
        max_possible = np.array([100.0, 100.0, 100.0])
        assert train_s2.band_penalty(counts, max_possible) == 0.0

    def test_overflow_and_shortfall_both_cost(self):
        over = train_s2.band_penalty(np.array([200.0]), np.array([500.0]))
        under = train_s2.band_penalty(np.array([3.0]), np.array([500.0]))
        assert over > 0 and under > 0

    def test_shortfall_forgiven_when_seed_is_too_small(self):
        # A seed with only 8 eligible citers can't reach 20 — shipping 8 is not
        # the rule's fault, so it costs nothing.
        penalized = train_s2.band_penalty(np.array([8.0]), np.array([500.0]))
        forgiven = train_s2.band_penalty(np.array([8.0]), np.array([8.0]))
        assert penalized > 0
        assert forgiven == 0.0


class TestFit:
    """Coarse-to-fine search lands a solvable corpus in the target band."""

    @staticmethod
    def _solvable_corpus() -> list[train_s2.Seed]:
        # Every seed has ~30 high-cited citers (landmarks) plus a tail of
        # low-cited ones (Latest), so a rule exists that lands each near 30.
        rng = np.random.default_rng(0)
        seeds = []
        for corpus_id, seed_cites in enumerate([200, 2_000, 20_000, 200_000], start=1):
            citers = []
            for _landmark in range(30):
                citers.append((int(rng.integers(0, 10)), int(seed_cites // 5), 1))
            for _latest in range(200):
                citers.append((int(rng.integers(0, 3)), int(rng.integers(2, 8)), 1))
            seeds.append(_seed(corpus_id, seed_cites, citers))
        return seeds

    def test_fit_puts_seeds_in_band(self):
        seeds = self._solvable_corpus()
        inputs = train_s2.build_inputs(seeds)
        params = train_s2.fit(inputs)
        counts = train_s2.landmark_counts(inputs, *params)
        # Every seed lands inside 20–40 after the fit.
        assert np.all(counts >= train_s2.TARGET_LOW)
        assert np.all(counts <= train_s2.TARGET_HIGH)

    def test_floor_never_drops_below_the_prune_floor(self):
        inputs = train_s2.build_inputs(self._solvable_corpus())
        params = train_s2.fit(inputs)
        assert params[3] >= train_s2.FLOOR_MIN


class TestBundle:
    """The artifact bundle is contract-shaped and carries the spread report."""

    def test_bundle_has_constants_and_spread(self):
        seeds = TestFit._solvable_corpus()
        seeds[0] = train_s2.Seed(**{**seeds[0].__dict__, "is_worked_example": True,
                                    "label": "DQN"})
        inputs = train_s2.build_inputs(seeds)
        params = train_s2.fit(inputs)
        bundle = train_s2.build_bundle(inputs, params, seeds, as_of_year=2026)
        assert bundle["provider"] == "s2"
        assert {"a", "p", "beta", "floor", "median_seed", "age_max"} <= set(bundle)
        assert bundle["floor"] >= train_s2.FLOOR_MIN
        assert "DQN" in bundle["achieved_spread"]["worked_examples"]
        assert 0.0 <= bundle["achieved_spread"]["in_band_frac"] <= 1.0
