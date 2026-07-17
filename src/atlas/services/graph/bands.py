"""Serving the adaptive latest-band boundary — closing the landmark→latest gap.

Every term here — landmark, band, tail edge, ``tau``, ``max_span`` — is defined
once, with worked examples, in ``docs/landmark-vocabulary.md``; the sibling
``budget`` module sizes the landmark band, this one places the Latest boundary.

Field Landmarks are a seed's all-time most-cited citers (any year); Latest
Publications fills recent years evenly with one ``cited_by_count`` query *per
year*, up to the current year. Those bands used to start at a **fixed** lower
edge (``config.graph.latest_band_years``). For an *old* seed whose landmark
cluster tails off years before that fixed start, the timeline shows a dead
stretch between the last landmark and the first band — the gap this module
closes.

Fix: start the bands per-seed at the **recent edge of the landmark cluster** —
the year where the cluster's per-year *density* falls off. Concretely the
boundary is the most recent year whose landmark count is still at least ``tau``
of the peak year's count (:func:`tail_edge`) — a scale-free tail-onset detector.
It's capped for cost: the start never reaches back more than ``max_span`` years
before the landmark cutoff, so an ancient seed doesn't spawn dozens of throttled
per-year band queries.

A tail-density detector, **not** a quantile: the quantile is *mass*-based, so a
seed's large old bulk drags the boundary years before the cluster's visible edge
(Hawking's landmarks stay dense to ~2020 but the 0.85 quantile sits at 2013).
The density edge tracks where the cluster actually thins out, and it's robust to
OpenAlex's unreliable per-work years — a couple of misdated citers can't clear
the count threshold, where a min/max would jump straight to them. There's no
"only widen" clamp: a young seed whose landmarks already reach the present starts
its bands at that recent edge (a tight, current frontier), not at a fixed span.

``tau`` and ``max_span`` are **not** hand-tuned constants: they're fit/chosen on a
labelled OpenAlex corpus by ``src/ml_pipelines/latest_gap`` and shipped in the model
artifact (``src/ml_pipelines/latest_gap/model.joblib``). This module is the *serving*
half — it loads that artifact and applies the rule; the *tail-edge rule itself*
(:func:`tail_edge`) is imported by training too, so there's one contract and no
train/serve skew. A missing or unreadable artifact degrades gracefully to the
fixed ``latest_band_years`` span rather than failing a graph build.

Unlike the sibling ``budget`` model, the boundary is a property of each seed's
landmark *distribution*, not of its age/citations (a feature regression on those
was tried and fails — see ``research/latest_gap``), so the served input is the
fetched landmark-year list, not a seed feature vector.
"""

from __future__ import annotations

import logging
from collections import Counter
from functools import lru_cache
from typing import Any

import joblib

from ...config import PROJECT_ROOT, config

log = logging.getLogger(__name__)

#: The trained-model artifact, written by ``src/ml_pipelines/latest_gap/train.py``
#: beside it. A joblib bundle: ``{"rule": <RULE_NAME>, "tau", "max_span", ...}``.
MODEL_PATH = PROJECT_ROOT / "src" / "ml_pipelines" / "latest_gap" / "model.joblib"

#: The rule contract — the boundary logic the artifact's ``tau``/``max_span`` were
#: fit for. Training records the same string, so a served artifact whose rule
#: doesn't match this module's :func:`tail_edge` is rejected (like the ``budget``
#: model's ``FEATURE_NAMES`` guard).
RULE_NAME = "landmark-density-tail"

#: Below this many dated landmark years the density edge is too noisy to trust —
#: the seed falls back to the fixed span (a young seed with a handful of citers
#: has no gap to close anyway).
MIN_LANDMARK_YEARS = 10


def tail_edge(landmark_years: list[int], tau: float) -> int:
    """The recent edge of a landmark cluster: the last still-dense year.

    Count the landmarks per publication year, take ``tau`` of the **peak** year's
    count as a threshold, then scan back from the newest year and return the first
    year that still clears it — i.e. where the cluster stops being a cluster::

        landmarks counted by year        tau = 0.25
            2015:  10  <- peak          threshold = 0.25 * 10 = 2.5
            2016:   8
            2017:   3
            2018:   1
            2019:   1

        scan back from the newest year:
            2019:  1  <  2.5   too thin, keep scanning back
            2018:  1  <  2.5   too thin, keep scanning back
            2017:  3 >= 2.5   still dense -> this is the edge

        => 2017

    The rule is shared by serving (here) and training
    (``src/ml_pipelines/latest_gap``), so the two can't disagree on what the
    boundary means.

    Scale-free — the threshold is relative to this seed's *own* peak, so it works
    for a 30-landmark seed and a 160-landmark one alike — and robust to a handful
    of misdated citers: two outliers can't clear the count threshold, where a
    plain min/max would jump straight to them.

    Args:
        landmark_years: The shipped landmarks' publication years (unsorted OK).
        tau: The fraction of the peak year's count a year must reach to still
            count as part of the dense cluster (e.g. ``0.2``).

    Returns:
        The most recent still-dense year (the cluster's recent edge). Falls back
        to the earliest year when no year clears the threshold.
    """
    counts = Counter(landmark_years)
    threshold = max(tau * max(counts.values()), 1.0)
    for year in range(max(landmark_years), min(landmark_years) - 1, -1):
        if counts[year] >= threshold:
            return year
    return min(landmark_years)


@lru_cache(maxsize=1)
def load_model() -> dict[str, Any] | None:
    """Load and memoize the trained-boundary bundle, or None when unavailable.

    A missing, unreadable, or wrong-rule artifact is logged and returns None so
    the caller falls back to the fixed ``latest_band_years`` span — a graph
    build must never fail just because this model hasn't been trained yet.

    Returns:
        The joblib bundle (``tau`` and ``max_span`` plus training metadata), or
        None when the artifact can't be loaded or its rule doesn't match.
    """
    if not MODEL_PATH.exists():
        log.warning("latest-gap model missing at %s; using fixed latest_band_years", MODEL_PATH)
        return None
    try:
        bundle: dict[str, Any] = joblib.load(MODEL_PATH)
    except Exception as error:  # a corrupt/incompatible artifact must not crash a build
        log.warning("latest-gap model failed to load (%s); using fixed latest_band_years", error)
        return None
    if bundle.get("rule") != RULE_NAME:
        log.warning("latest-gap model rule mismatch %s; using fixed latest_band_years",
                    bundle.get("rule"))
        return None
    return bundle


def _reset_model_cache() -> None:
    """Clear the memoized model (tests that swap the artifact call this).

    Tolerant of ``load_model`` having been monkeypatched to a plain function
    (which has no ``cache_clear``), so test teardown can call it unconditionally.
    """
    cache_clear = getattr(load_model, "cache_clear", None)
    if cache_clear is not None:
        cache_clear()


def earliest_band_year(landmark_years: list[int], landmark_max_year: int) -> int | None:
    """The first year the per-year Latest bands should cover, adapted per seed.

    Applies the tail-edge rule with the artifact's fitted ``tau``/``max_span``:
    start the bands where the landmark cluster's density falls off
    (:func:`tail_edge`), floored so the start reaches back at most ``max_span``
    years before the landmark cutoff (bounded query cost). No "only widen" clamp
    — a young seed whose cluster edge is recent starts its bands there.

    Falls back (returns None → the caller keeps the fixed span) when the feature
    is off, the artifact isn't loadable, or the seed has too few dated landmark
    years to place a trustworthy boundary.

    Args:
        landmark_years: Publication years of the seed's *shipped* landmark
            citers (the budget-trimmed pool the build already fetched).
        landmark_max_year: The last landmark-era year — the ``max_span`` floor is
            measured back from it.

    Returns:
        The adaptive first band year, or None to keep the fixed span.
    """
    if not config.graph.adaptive_latest_band:
        return None
    return band_start_rule(landmark_years, landmark_max_year)


def band_start_rule(landmark_years: list[int], landmark_max_year: int) -> int | None:
    """The fitted tail-edge rule itself, config-free — shared by serving and pipelines.

    :func:`earliest_band_year` gates this on ``config.graph.adaptive_latest_band``
    for the app; the rule is factored out (the ``budget.predicted_budget`` precedent)
    so the ``live_pool_validation`` study can place band starts over simulated
    pools without depending on the local ``config.json``. Still returns None when
    the artifact isn't loadable or the seed has too few dated landmark years.

    Args:
        landmark_years: Publication years of the seed's shipped landmark citers.
        landmark_max_year: The last landmark-era year — the ``max_span`` floor is
            measured back from it.

    Returns:
        The adaptive first band year, or None when no trustworthy boundary can
        be placed.
    """
    dated = [year for year in landmark_years if year]
    if len(dated) < MIN_LANDMARK_YEARS:
        return None
    bundle = load_model()
    if bundle is None:
        return None
    edge = tail_edge(dated, float(bundle["tau"]))
    floor = landmark_max_year - int(bundle["max_span"]) + 1
    band_start = max(edge, floor)  # cap query cost; the density edge is the primary pick
    log.info(
        "adaptive latest band starts %d (density edge %d, floor %d) from %d landmark years",
        band_start, edge, floor, len(dated),
    )
    return band_start
