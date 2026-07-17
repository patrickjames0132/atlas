"""The live-pool-validation collector (src/ml_pipelines/live_pool_validation): offline checks.

Fully offline — the corpus queries run against the synthetic ingested release
(``conftest.synthetic_corpus``), and the pure ``pool_metrics`` is driven
directly. The OpenAlex id-mapping step is NOT exercised here (it's one throttled
live call per seed); its output shape is what ``resolve_seeds`` consumes, so the
resolution tests feed that shape by hand.
"""

from __future__ import annotations

from atlas.services.graph import budget as app_budget
from ml_pipelines.live_pool_validation import collect


class TestCorpusReader:
    """The study's corpus queries: resolution routes and the upstream dedupe."""

    def test_resolves_by_arxiv_id_and_by_doi(self, synthetic_corpus):
        seeds = [
            {"work_id": "W1", "label": "Synthetic DQN", "arxiv_id": "1312.5602", "doi": None},
            {"work_id": "W2", "label": "Journal-only", "arxiv_id": None,
             "doi": "10.5555/JOURNAL-ONLY"},  # wrong case on purpose — DOIs match folded
            {"work_id": "W3", "label": "Unknown", "arxiv_id": None, "doi": "10.1/nope"},
        ]
        reader = collect.CorpusReader()
        reader.resolve_seeds(seeds)
        assert seeds[0]["corpus_id"] == 1
        assert seeds[0]["s2_year"] == 2013
        assert seeds[0]["s2_citation_count"] == 900
        assert seeds[1]["corpus_id"] == 10
        assert "corpus_id" not in seeds[2]

    def test_citers_collapse_the_overlapping_batches(self, synthetic_corpus):
        # 6 distinct citers arrive as 9 edge rows across two shards; a reader
        # that counts rows (not papers) would report the study's pools ~1.5x big.
        citers = collect.CorpusReader().citers(1)
        assert len(citers) == 6
        assert sorted(citer["citation_count"] for citer in citers) == [50, 100, 250, 300, 400, 500]


class TestPoolMetrics:
    """The per-seed measurements, over the synthetic corpus's citer set."""

    def test_untruncated_pool_uses_the_whole_history(self, synthetic_corpus):
        citers = collect.CorpusReader().citers(1)
        metrics = collect.pool_metrics(
            citers, seed_year=2013, seed_citation_count=900, as_of_year=2026)
        assert metrics["truncated"] == 0
        assert metrics["pool_size"] == 6
        assert metrics["oldest_pool_year"] == 2019
        # One citer per dated year, cap 12 -> nothing floods: the label is the
        # whole pool and the banded selection keeps every dated citer.
        assert metrics["citers_before_overflow_reachable"] == 6
        # The undated citer is dropped by SKIP, not given a bucket of its own.
        assert metrics["selected_up_to_cap_per_year"] == 5
        assert (metrics["citers_before_overflow_reachable"]
                == metrics["citers_before_overflow_full"])

    def test_truncation_moves_the_age_origin_not_the_seed(self, synthetic_corpus):
        citers = collect.CorpusReader().citers(1)
        metrics = collect.pool_metrics(
            citers, seed_year=2013, seed_citation_count=900, as_of_year=2026,
            reachable=2)
        # Newest-first truncation to 2: the undated citer sorts last, so the
        # pool is the 2024 + 2023 citers — the oldest reachable year is 2023,
        # nowhere near the 2013 seed. That gap is the study's whole subject.
        assert metrics["truncated"] == 1
        assert metrics["pool_size"] == 2
        assert metrics["oldest_pool_year"] == 2023
        # The full-history label still sees all six citers.
        assert metrics["citers_before_overflow_full"] == 6
        # The two age origins: one reads age from the pool (2026-2023), the
        # other from the seed (2026-2013) — both through the real committed
        # model artifact, so they must differ for this old seed.
        assert (metrics["predicted_budget_age_from_oldest_citer"]
                != metrics["predicted_budget_age_from_seed"])

    def test_band_start_needs_enough_dated_landmarks(self, synthetic_corpus):
        # MIN_LANDMARK_YEARS (10) dated landmark years don't exist here, so the
        # tau rule declines to place a boundary rather than guessing from noise.
        citers = collect.CorpusReader().citers(1)
        metrics = collect.pool_metrics(
            citers, seed_year=2013, seed_citation_count=900, as_of_year=2026)
        assert metrics["band_start"] is None


class TestRuleContracts:
    """The study runs the app's rules, not private copies that could drift."""

    def test_measures_use_the_apps_functions(self):
        assert (collect.budget.number_of_ranked_citers_before_a_single_year_overflows
                is app_budget.number_of_ranked_citers_before_a_single_year_overflows)
        assert collect.budget.select_up_to_cap_per_year is app_budget.select_up_to_cap_per_year

    def test_truncation_is_the_pagers_own_constant(self):
        from atlas.integrations.semantic_scholar import traversal

        assert collect.REACHABLE_CITERS == traversal.REACHABLE_CITERS == 9000
