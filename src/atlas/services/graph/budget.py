"""Serving the adaptive landmark-budget model — feature construction + prediction.

The graph build ships up to ``cite_limit`` landmark citers per seed, but the
right number depends on the seed: an old classic's landmarks span decades and
read as a map of the field, while a young hot paper's top citers pile into one
or two years — same count, far more clutter. So the budget is *predicted* from
two cheap fields already on the seed node (publication age + citation count) by
a scikit-learn model **trained offline**, not hand-tuned constants.

This module is the *serving* half: it loads the trained model
(``ml_pipelines/models/cite_budget.joblib``) and turns a seed into a landmark budget. The
*training* half lives in ``ml_pipelines/cite_budget`` — it fits the model on a labelled
OpenAlex corpus and writes the artifact. Both sides build the feature vector
through :func:`compute_features` here, so there's a single feature contract and
no train/serve skew. See ``ml_pipelines/cite_budget/README.md`` for the derivation.

The model artifact is loaded once and memoized (:func:`load_model`); a missing
or unreadable artifact degrades gracefully to the flat ``cite_limit`` rather
than failing a graph build.
"""

from __future__ import annotations

import logging
import math
from functools import lru_cache
from typing import Any

import joblib

from ...config import PROJECT_ROOT, config
from ...integrations import openalex

log = logging.getLogger(__name__)

#: The trained-model artifact, written by ``ml_pipelines/cite_budget/train.py``. A joblib
#: bundle: ``{"model": <sklearn estimator>, "feature_names", "floor", ...}``.
MODEL_PATH = PROJECT_ROOT / "ml_pipelines" / "models" / "cite_budget.joblib"

#: The feature contract — the order the estimator was trained on. Training reads
#: this same constant, so the serving vector can't drift from the fitted one.
FEATURE_NAMES = ("age", "log_cites")


def compute_features(year: int, citation_count: int, *, as_of_year: int) -> list[float]:
    """Build the model's feature vector for one seed, in :data:`FEATURE_NAMES` order.

    Shared by training (over the corpus) and serving (per graph build) so the
    two never disagree on what a feature means.

    Args:
        year: The seed's publication year.
        citation_count: The seed's total citation count.
        as_of_year: The reference year age is measured from (today's year at
            serving time; the collection year during training).

    Returns:
        ``[age, log10(citation_count + 1)]`` — ``age`` floored at 0 (guards a
        seed OpenAlex mis-dates into the future).
    """
    age = max(as_of_year - year, 0)
    log_cites = math.log10(citation_count + 1)
    return [float(age), log_cites]


@lru_cache(maxsize=1)
def load_model() -> dict[str, Any] | None:
    """Load and memoize the trained-model bundle, or None when unavailable.

    A missing or unreadable artifact is logged and returns None so the caller
    falls back to the flat ``cite_limit`` — a graph build must never fail just
    because the model hasn't been trained yet.

    Returns:
        The joblib bundle (``model`` estimator plus ``feature_names``, ``floor``,
        and training metadata), or None when the artifact can't be loaded.
    """
    if not MODEL_PATH.exists():
        log.warning("cite-budget model missing at %s; using flat cite_limit", MODEL_PATH)
        return None
    try:
        bundle: dict[str, Any] = joblib.load(MODEL_PATH)
    except Exception as error:  # a corrupt/incompatible artifact must not crash a build
        log.warning("cite-budget model failed to load (%s); using flat cite_limit", error)
        return None
    if tuple(bundle.get("feature_names", ())) != FEATURE_NAMES:
        log.warning("cite-budget model feature mismatch %s; using flat cite_limit",
                    bundle.get("feature_names"))
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


def adaptive_cite_limit(seed_paper: dict, *, as_of_year: int) -> int | None:
    """The seed-adapted landmark ship count, from the trained model.

    Runs the model's ``predict`` on the seed's features and clamps the result to
    ``[floor, ceiling]`` — the ceiling is the configured ``cite_limit`` (its
    ``null`` unbounded cap when unset), the floor the smallest budget seen in
    training. The budget only ever shrinks the ceiling; it never ships more than
    the flat config would.

    Falls back to the flat ``cite_limit`` (passed through unchanged) when the
    feature is off, the seed has no publication year, or the model isn't loadable.

    Args:
        seed_paper: The normalized S2 seed node (``year`` and ``citation_count``
            drive the model).
        as_of_year: The year to measure the seed's age from (today's year).

    Returns:
        The landmark limit to ship — a concrete count from the model, otherwise
        the configured ``cite_limit`` (which may be None, the traversals'
        unbounded cap).
    """
    ceiling = config.graph.cite_limit
    if not config.graph.adaptive_cite_limit:
        return ceiling
    seed_year = seed_paper.get("year")
    if not isinstance(seed_year, int):
        return ceiling  # no publication year — the model has no age to run on
    bundle = load_model()
    if bundle is None:
        return ceiling
    if ceiling is None:
        ceiling = openalex.UNBOUNDED_LANDMARK_CAP
    citation_count = seed_paper.get("citation_count") or 0
    features = compute_features(seed_year, citation_count, as_of_year=as_of_year)
    predicted = float(bundle["model"].predict([features])[0])
    budget = min(max(round(predicted), int(bundle["floor"])), ceiling)
    log.info(
        "adaptive landmark budget %d for seed year=%d citations=%d (ceiling %d)",
        budget, seed_year, citation_count, ceiling,
    )
    return budget
