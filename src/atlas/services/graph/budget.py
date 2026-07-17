"""Serving the adaptive landmark budget — how many landmark citers a seed ships.

Every term used here — landmark, pool, reachable, truncated, label, age origin,
and the two rules below — is defined once, with this same worked example, in
``docs/landmark-vocabulary.md``. The *why* (when to predict, when to compute) is
``docs/predict-vs-compute.md``. This module is the rules as shipped.

The graph build ships up to ``cite_limit`` landmark citers per seed, but the right
number depends on the seed: an old classic's landmarks span decades and read as a
map of the field, while a young hot paper's top citers pile into one or two years
— same count, far more clutter. Both rules here make "clutter" concrete the same
way: rank a seed's citers most-cited first, drop each into a bucket named by its
publication year, and never let a bucket exceed :data:`PER_YEAR_CAP`.

They differ in **one word** — what happens when a citer lands on a full bucket::

    ranked citer years:  2020  2020  2020  2019  2018  2020  2017    (cap=2)

    STOP  number_of_ranked_citers_before_a_single_year_overflows -> 2
          The third 2020 overflows, so the walk ends there. Ranks 3-6 are
          never reached, though buckets 2019, 2018 and 2017 are empty.

    SKIP  select_up_to_cap_per_year -> [0, 1, 3, 4, 6]
          The third 2020 is skipped and the walk carries on. Five landmarks
          ship, spanning 2017-2020.

SKIP is not a more accurate STOP — it's a *better rule*, and only possible with the
pool in hand. STOP survives for exactly one reason: it returns a scalar, and a
regression **label** has to be a scalar. Measured on DQN, STOP quits at 29
landmarks with 2020 full and ships **nothing from 2024–2025**, leaving an 18-month
hole before the Latest frontier; SKIP ships 84 — twelve in each of 2019–2025 — and
closes it. SKIP is the local equivalent of the per-year banding OpenAlex gets from
its query (``openalex.citation_relations``); S2's citations endpoint has no year
filter, so the banding has to happen over the ranking instead.

Which rule a path *can* use is dictated by its provider's API, not by taste:

* **Predict a count** (:func:`adaptive_cite_limit`) — OpenAlex and the offline S2
  citations corpus push a limit down into a citation-sorted query, so they must
  know the number *before* they hold a single citer. A count is all a query can
  take, and a model trained offline supplies it from two cheap fields already on
  the seed node (age + citation count). No pool is fetched just to size the trim.
* **Select from the pool** (:func:`select_landmarks`) — the **live S2 fallback**
  gets no server-side sort, so its deep pager already holds the whole reachable
  pool before the trim. Nothing has to be guessed, so nothing is: it runs SKIP.

Predicting on the live path would be wrong twice over: you'd inherit the model's
error while saving nothing, *and* the model is fit on pools spanning a seed's whole
citation history while that path's pool is **truncated** to the newest
``REACHABLE_CITERS`` (9,000 — DQN's reaches back to 2019, not 2013).

Serving and training share :func:`compute_features` and :data:`PER_YEAR_CAP`, and
the label (:func:`number_of_ranked_citers_before_a_single_year_overflows`) is
defined here beside the model it belongs to — one definition each, no train/serve
skew. The *training* half lives beside the artifact in
``src/ml_pipelines/cite_budget``, which imports both from here; see its README for
the derivation.

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
#: artifact's ``per_year_cap``; the live-fallback trim applies it directly — one
#: constant behind both, like :data:`FEATURE_NAMES`.
PER_YEAR_CAP = 12


def number_of_ranked_citers_before_a_single_year_overflows(
    citer_years: Sequence[int | None], cap: int
) -> int:
    """How deep into the ranked citers you get before one publication year overflows ``cap``.

    **The STOP rule.** Walk the citation-ranked citer years from the top, dropping
    each into a bucket named by its year. The instant a bucket would exceed
    ``cap``, stop the whole walk and return how many were admitted before it. A
    pool that never trips the cap yields its full length::

        years = [2020, 2020, 2020, 2019, 2018, 2020, 2017]

        rank 0  2020  ->  bucket 2020 = 1   admit
        rank 1  2020  ->  bucket 2020 = 2   admit
        rank 2  2020  ->  bucket 2020 = 3   OVERFLOWS cap=2 -> STOP

        => 2

    Note what it cost: ranks 3-6 are never looked at, though buckets 2019, 2018
    and 2017 are empty. That loss is the rule's defining property, not a bug.

    *What it measures.* ``cap`` is how many same-year papers a landmark view
    tolerates before that year reads as a pile-up. A young, hot paper's top citers
    cram into one or two years, so a bucket floods almost immediately and the
    number is small; an old classic's spread across decades, so nothing floods
    until deep into the list and the number is large. Same top citers, very
    different answer — that gap is the temporal clutter this quantifies.

    **This is the model's training label and nothing else** — what ``.predict()``
    regresses on. No serving path calls it. It stops (rather than skipping full
    buckets and walking on, as :func:`select_up_to_cap_per_year` does) purely
    because a regression label has to be a single number and a selection is a list.
    Where the pool is in hand, use the SKIP rule; see this module's docstring for
    the 29-vs-84 measurement on DQN. Defined here beside the model it belongs to
    rather than in the pipeline (``ml_pipelines.cite_budget`` imports it, as it
    does :func:`compute_features`).

    An undated citer is admitted without contributing to any bucket — it can't
    crowd a year it isn't in. Training passes an all-dated list (its collector
    drops undated citers before labelling).

    Args:
        citer_years: Citer publication years in citation rank (most-cited first),
            ``None`` for a citer the provider gave no year.
        cap: The per-year cap ``K`` (see :data:`PER_YEAR_CAP`).

    Returns:
        How many ranked citers were admitted before a year first overflowed — e.g.
        ``([2018, 2019, 2018, 2020, 2018], cap=2)`` returns ``4``, the third 2018
        tripping the cap at index 4.
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


def predicted_budget(year: int, citation_count: int, *, as_of_year: int,
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

    Runs the model's ``predict`` on the seed's features (:func:`predicted_budget`)
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
    budget = predicted_budget(seed_year, citation_count, as_of_year=as_of_year, ceiling=ceiling)
    if budget is None:
        return ceiling
    log.info(
        "adaptive landmark budget %d for seed year=%d citations=%d",
        budget, seed_year, citation_count,
    )
    return budget


def select_landmarks(citer_years: Sequence[int | None]) -> list[int] | None:
    """The app-facing landmark selection: the SKIP rule, plus this build's config.

    The counterpart to :func:`adaptive_cite_limit` for callers that already hold
    the pool (the live S2 fallback). The walk itself — admit up to
    :data:`PER_YEAR_CAP` per publication year, skipping citers whose year is
    already full — is :func:`select_up_to_cap_per_year`, which has the worked
    example; this wrapper only adds the toggle, the ceiling, and the log line.

    Returns *indices* rather than entries because ``integrations`` owns the citer
    dicts and this layer only ever sees their years; ``build.py`` injects this into
    the live S2 traversal as a callable, keeping ``integrations`` below ``services``
    in the import order — the same shape as ``bands.earliest_band_year`` going into
    the OpenAlex traversal.

    **Undated citers are dropped, not banded.** A Field Landmark is the claim
    "one of the most-cited papers to cite this seed *in year Y*" — a citer with no
    year can't make it, and can't be drawn on a time axis either. Giving them a
    bucket of their own (an earlier cut of this did) ships a guaranteed
    ``PER_YEAR_CAP`` of them, and since they all land on one x, they surface as a
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
    keep = select_up_to_cap_per_year(citer_years)
    ceiling = config.graph.cite_limit
    if ceiling is not None:
        keep = keep[:ceiling]
    log.info(
        "landmark selection: %d of %d ranked citers (cap %d/year)",
        len(keep), len(citer_years), PER_YEAR_CAP,
    )
    return keep


def select_up_to_cap_per_year(citer_years: Sequence[int | None],
                              cap: int = PER_YEAR_CAP) -> list[int]:
    """Pick up to ``cap`` citers from each publication year, walking the ranking top-down.

    **The SKIP rule** — the pure, config-free walk, and the one the app actually
    serves. Same bucketing as
    :func:`number_of_ranked_citers_before_a_single_year_overflows`, but a full
    bucket means *skip this citer and keep going*, never *stop*::

        years = [2020, 2020, 2020, 2019, 2018, 2020, 2017]

        rank 0  2020  ->  bucket 2020 = 1   admit
        rank 1  2020  ->  bucket 2020 = 2   admit
        rank 2  2020  ->  bucket FULL       SKIP, keep walking
        rank 3  2019  ->  bucket 2019 = 1   admit
        rank 4  2018  ->  bucket 2018 = 1   admit
        rank 5  2020  ->  bucket FULL       SKIP, keep walking
        rank 6  2017  ->  bucket 2017 = 1   admit

        => [0, 1, 3, 4, 6]

    Five landmarks spanning 2017-2020, where the STOP rule got two, both crammed
    into 2020. A dense year is capped without costing the sparse years behind it.

    Because it walks to the end, it returns a **selection**, not a count — you
    cannot reproduce it by taking the top N of the ranking, since it steps over
    citers sitting in already-full years. That's the "a count can't express the
    answer" lesson (see this module's docstring, and the 18-month hole the STOP
    rule left on DQN).

    Factored out of :func:`select_landmarks` (the :func:`predicted_budget`
    precedent) so the ``live_pool_validation`` study can run the exact serving rule
    over simulated pools without depending on the local ``config.json``.

    Args:
        citer_years: The ranked landmark pool's publication years, most-cited
            first, ``None`` where the provider gave no year.
        cap: The per-year cap (see :data:`PER_YEAR_CAP`).

    Returns:
        The indices of ``citer_years`` to ship, ascending (most-cited-first
        within the shipped band).
    """
    per_year: Counter[int] = Counter()
    keep: list[int] = []
    for index, year in enumerate(citer_years):
        if year is None:
            continue  # no year -> no band to belong to, and no place on a timeline
        if per_year[year] >= cap:
            continue  # this year is already full — skip on, don't stop
        per_year[year] += 1
        keep.append(index)
    return keep
