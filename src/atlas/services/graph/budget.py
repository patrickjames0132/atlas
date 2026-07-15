"""Serving the adaptive landmark budget — how many landmark citers a seed ships.

The graph build ships up to ``cite_limit`` landmark citers per seed, but the
right number depends on the seed: an old classic's landmarks span decades and
read as a map of the field, while a young hot paper's top citers pile into one
or two years — same count, far more clutter. The criterion that makes "clutter"
concrete is the **density budget** ``n*`` (:func:`density_budget`): walking a
seed's citation-ranked citers from the top, the longest prefix in which no single
publication year holds more than :data:`DENSITY_CAP` of them.

How that criterion is applied splits on **whether the caller already holds the
citer pool** — and the two answers are shaped differently, a count versus a
selection:

* **Predict a count** (:func:`adaptive_cite_limit`) — a scikit-learn model
  **trained offline** infers ``n*`` from two cheap fields already on the seed node
  (publication age + citation count), so no pool has to be fetched to size the
  trim. This is what the *ranked* citer paths use: OpenAlex and the offline S2
  citations corpus both push a limit down into a citation-sorted query, so they
  must know the number *before* they have any citers to look at. A count is all a
  query can take.
* **Select from the pool** (:func:`density_selection`) — walk the ranked citers
  and admit up to :data:`DENSITY_CAP` **per year**, skipping years already full.
  This is what the **live S2 fallback** uses: its deep pager has the whole
  reachable pool in memory before the trim, so nothing has to be guessed.

The second isn't just a more accurate version of the first — it's a *better rule*,
and only possible with the pool in hand. Both enforce the same invariant (no year
over the cap), but :func:`density_budget` is a **prefix**: it stops the entire
walk the moment one year floods, so a single dense year truncates the band and
every sparser year after it is lost. Measured on DQN: the prefix stops at 29
landmarks with 2020 full and **nothing at all from 2024–2025**, leaving an 18-month
hole between the landmarks and the Latest frontier; the per-year quota ships 84,
twelve in each of 2019–2025, and closes it. The prefix rule survives because a
*label* has to be a scalar the model can regress on — not because it's the best way
to pick landmarks. It's the local equivalent of the per-year banding OpenAlex gets
from its query (``openalex.citation_relations``); S2's citations endpoint has no
year filter, so the banding has to happen over the ranking instead.

Predicting on the live path would be wrong for a second reason too: the model is
fit on landmark pools spanning a seed's whole citation history, while that path's
pool is **truncated** at S2's ~10k offset ceiling (DQN's reaches back to 2019, not
2013).

Serving and training share :func:`compute_features` and :data:`DENSITY_CAP`, and
the label :func:`density_budget` is defined here beside the model it belongs to —
so there's one definition of each and no train/serve skew. The *training* half
lives beside the artifact in ``src/ml_pipelines/cite_budget``, which imports them
from here; see its README for the derivation.

The model artifact is loaded once and memoized (:func:`load_model`); a missing or
unreadable artifact degrades gracefully to the flat ``cite_limit`` rather than
failing a graph build. The selection path has no such dependency.
"""

from __future__ import annotations

import logging
import math
from collections import Counter
from collections.abc import Sequence
from functools import lru_cache
from typing import Any

import joblib

from ...config import PROJECT_ROOT, config
from ...integrations import openalex

log = logging.getLogger(__name__)

#: The trained-model artifact, written by ``src/ml_pipelines/cite_budget/train.py``
#: beside it. A joblib bundle: ``{"model": <sklearn estimator>, "feature_names",
#: "floor", ...}``.
MODEL_PATH = PROJECT_ROOT / "src" / "ml_pipelines" / "cite_budget" / "model.joblib"

#: The feature contract — the order the estimator was trained on. Training reads
#: this same constant, so the serving vector can't drift from the fitted one.
FEATURE_NAMES = ("age", "log_cites")

#: The per-year density cap ``K``: how many same-year papers a landmark view
#: tolerates before that year reads as a pile-up. The research notebook swept K
#: and settled on 12. Training labels the corpus with it and records it in the
#: artifact's ``density_cap``; the live-fallback trim applies it directly — one
#: constant behind both, like :data:`FEATURE_NAMES`.
DENSITY_CAP = 12


def density_budget(citer_years: Sequence[int | None], cap: int) -> int:
    """Longest prefix of ``citer_years`` (its first N, from the top) whose densest single year holds ``≤ cap``.

    Walks the citation-ranked citer years from the top, accumulating a per-year
    count; the budget is the position just before some year's running count first
    exceeds ``cap`` (i.e. the length of the prefix admitted so far). A pool that
    never trips the cap yields its full length.

    *What it means.* ``cap`` is how many same-year papers a landmark view
    tolerates before that year reads as a pile-up. A young, hot paper's top citers
    cram into one or two years, so a single year floods almost immediately and the
    budget is small; an old classic's spread across decades, so no year floods
    until deep into the list and the budget is large. Same top citers, very
    different ``n*`` — that gap is the temporal clutter this quantifies.

    The model's training **label** — what ``.predict()`` is regressing on — so
    it's defined here beside the model rather than in the pipeline
    (``ml_pipelines.cite_budget`` imports it, as it does :func:`compute_features`).

    *Not* how landmarks get picked when the pool is in hand: being a prefix, one
    dense year ends the walk and costs every sparser year behind it. See
    :func:`density_selection`, which enforces the same cap per year instead. This
    stays a prefix because a regression label has to be a single number.

    An undated citer is admitted without contributing to any year's count — it
    can't crowd a year it isn't in. Training passes an all-dated list (its
    collector drops undated citers before labelling).

    Args:
        citer_years: Citer publication years in citation rank (most-cited first),
            ``None`` for a citer the provider gave no year.
        cap: The per-year density cap ``K`` (see :data:`DENSITY_CAP`).

    Returns:
        The density-criterion landmark budget ``n*`` — e.g.
        ``density_budget([2018, 2019, 2018, 2020, 2018], cap=2) == 4`` (the third
        2018 trips ``cap=2`` at index 4).
    """
    per_year: Counter[int] = Counter()
    for index, year in enumerate(citer_years):
        if year is None:
            continue  # undated: takes a slot, crowds no year
        per_year[year] += 1
        if per_year[year] > cap:
            return index
    return len(citer_years)


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


def model_budget(year: int, citation_count: int, *, as_of_year: int,
                 ceiling: int | None = None) -> int | None:
    """Predict and clamp one seed's landmark budget — the raw model call, config-free.

    The pure predict-and-clamp shared by serving (:func:`adaptive_cite_limit`,
    which layers the config flag/ceiling on top) and the ``latest_gap`` corpus
    collector (which must trim citer-year distributions exactly the way a build
    would, without depending on the local ``config.json``).

    Args:
        year: The seed's publication year.
        citation_count: The seed's total citation count.
        as_of_year: The year to measure the seed's age from.
        ceiling: The clamp ceiling; None uses the traversals' unbounded landmark
            cap.

    Returns:
        The clamped budget, or None when the model artifact isn't loadable.
    """
    bundle = load_model()
    if bundle is None:
        return None
    if ceiling is None:
        ceiling = openalex.UNBOUNDED_LANDMARK_CAP
    features = compute_features(year, citation_count, as_of_year=as_of_year)
    predicted = float(bundle["model"].predict([features])[0])
    return min(max(round(predicted), int(bundle["floor"])), ceiling)


def adaptive_cite_limit(seed_paper: dict, *, as_of_year: int) -> int | None:
    """The seed-adapted landmark ship count, from the trained model.

    Runs the model's ``predict`` on the seed's features (:func:`model_budget`)
    and clamps the result to ``[floor, ceiling]`` — the ceiling is the
    configured ``cite_limit`` (its ``null`` unbounded cap when unset), the floor
    the smallest budget seen in training. The budget only ever shrinks the
    ceiling; it never ships more than the flat config would.

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
    citation_count = seed_paper.get("citation_count") or 0
    budget = model_budget(seed_year, citation_count, as_of_year=as_of_year, ceiling=ceiling)
    if budget is None:
        return ceiling
    log.info(
        "adaptive landmark budget %d for seed year=%d citations=%d",
        budget, seed_year, citation_count,
    )
    return budget


def density_selection(citer_years: Sequence[int | None]) -> list[int] | None:
    """Which of a ranked citer pool to ship as landmarks: up to ``DENSITY_CAP`` per year.

    The counterpart to :func:`adaptive_cite_limit` for callers that already hold
    the pool (the live S2 fallback). Walks the citation-ranked citers from the top
    and admits each one whose publication year isn't yet full, **skipping** the
    ones whose year is — so a dense year is capped without costing the sparse years
    behind it, which is exactly what :func:`density_budget`'s prefix walk gets
    wrong (see this module's docstring, and the 18-month hole it left on DQN).

    Returns *indices* rather than entries because ``integrations`` owns the citer
    dicts and this layer only ever sees their years; ``build.py`` injects this into
    the live S2 traversal as a callable, keeping ``integrations`` below ``services``
    in the import order — the same shape as ``bands.earliest_band_year`` going into
    the OpenAlex traversal.

    **Undated citers are dropped, not banded.** A Field Landmark is the claim
    "one of the most-cited papers to cite this seed *in year Y*" — a citer with no
    year can't make it, and can't be drawn on a time axis either. Giving them a
    bucket of their own (an earlier cut of this did) ships a guaranteed
    ``DENSITY_CAP`` of them, and since they all land on one x, they surface as a
    bare vertical line through the seed's column. They're also the dregs in
    practice: S2 reports no year mostly for PDF-extraction stubs ("This paper is
    included in the Proceedings of…"), not for papers anyone would call landmarks.

    Gated by the same ``adaptive_cite_limit`` toggle as the predicted path — that
    flag means "size the landmark band to this seed", and this is how the live
    fallback honours it — and trimmed to the configured ``cite_limit`` ceiling,
    which (being a prefix of a citation-ranked selection) keeps the most-cited.

    Args:
        citer_years: The ranked landmark pool's publication years, most-cited
            first, ``None`` where the provider gave no year.

    Returns:
        The indices of ``citer_years`` to ship, ascending (so the shipped band
        stays most-cited-first). None when the adaptive toggle is off, telling the
        caller to fall back to the flat ``cite_limit``.
    """
    if not config.graph.adaptive_cite_limit:
        return None
    per_year: Counter[int] = Counter()
    keep: list[int] = []
    for index, year in enumerate(citer_years):
        if year is None:
            continue  # no year -> no band to belong to, and no place on a timeline
        if per_year[year] >= DENSITY_CAP:
            continue  # this year is already full — skip on, don't stop
        per_year[year] += 1
        keep.append(index)
    ceiling = config.graph.cite_limit
    if ceiling is not None:
        keep = keep[:ceiling]
    log.info(
        "landmark selection: %d of %d ranked citers, %d per year (cap %d)",
        len(keep), len(citer_years), len(per_year), DENSITY_CAP,
    )
    return keep
