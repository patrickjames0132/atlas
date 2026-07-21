"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
The latest-gap training pipeline (src/ml_pipelines/latest_gap): rule fit + serialize.

Fully offline — no OpenAlex calls. The visible-gap metric and the robustness fit
run on a tiny synthetic corpus so the pipeline (score → misdate-robustness → tau
→ serializable bundle) is exercised without the committed data or the network.
The served rule's behavior is pinned separately in
``test/atlas/services/test_bands.py``.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

from atlas.services.graph.bands import RULE_NAME
from ml_pipelines.latest_gap import train


def _row(years: list[int]) -> dict:
    """A corpus row shaped like :func:`train.load_corpus` yields."""
    return {"years": years}


class TestVisibleGap:
    """The longest dead stretch between the landmark cluster and the bands."""

    def test_contiguous_cluster_to_bands_has_no_gap(self):
        years = list(range(2010, train.CURRENT_YEAR - 4))
        assert train._visible_gap(years, band_start=train.CURRENT_YEAR - 4) == 0

    def test_counts_the_empty_stretch_below_the_band_start(self):
        # Cluster ends 2012, bands start 5 years before now: the stretch between
        # is an empty gap.
        years = [2010, 2011, 2012]
        band_start = train.CURRENT_YEAR - 4
        assert train._visible_gap(years, band_start) == band_start - 1 - 2012


class TestMisdateMovement:
    """The robustness metric that drives the tau fit."""

    def test_low_tau_lets_a_misdate_move_the_edge(self):
        # A flat distribution (peak 1) has threshold 1, so two future citers form
        # a new dense-enough year and drag the edge — high movement.
        rows = [_row([2005 + offset for offset in range(12)]) for _ in range(4)]
        assert train._misdate_movement(rows, 0.10) > 0.5

    def test_high_tau_resists_the_misdate(self):
        # A peaked distribution (peak 7 -> threshold 2.1 at tau 0.30): two
        # outliers (count 2) can't clear it, so the edge holds.
        rows = [_row([2010]*7 + [2011]*7 + [2012, 2013]) for _ in range(4)]
        assert train._misdate_movement(rows, 0.30) == 0.0


class TestFit:
    """The offline fit picks the cheapest misdate-robust tau and a contract bundle."""

    @staticmethod
    def _corpus() -> list[dict]:
        # Peaked clusters (peak 7) so a misdate-robust threshold (0.30) exists.
        return [_row([2010]*7 + [2012]*7 + [2013, 2014]) for _ in range(8)]

    def test_bundle_is_serializable_and_contract_shaped(self):
        bundle = train.fit(self._corpus())
        assert bundle["rule"] == RULE_NAME
        assert bundle["tau"] in train.TAU_GRID
        assert bundle["max_span"] == train.MAX_SPAN
        assert bundle["max_bands"] == train.MAX_SPAN + 2
        assert bundle["n_seeds"] == 8

    def test_fit_prefers_a_misdate_robust_threshold(self):
        bundle = train.fit(self._corpus())
        assert bundle["misdate_movement"] <= train.ROBUST_TOLERANCE
