"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
Serving the adaptive landmark budget — how many landmark citers a seed ships.

Every term used here — landmark, pool, reachable, truncated, label, age origin,
and the two rules below — is defined once, with this same worked example, in
``docs/landmark-vocabulary.md``. The *why* (when to predict, when to compute) is
``docs/predict-vs-compute.md``. This module is the rules as shipped.

The graph build ships up to ``UNBOUNDED_LANDMARK_CAP`` landmark citers per seed
(the shared payload guard — see ``integrations.caps``), but the right
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

Neither rule is a worse version of the other — **which one is honest depends on
the pool**. On a *truncated* pool (the live S2 fallback when the offset ceiling
cuts the list off), SKIP wins: STOP quits at 29 landmarks on truncated DQN with
2020 full and ships **nothing from 2024–2025**, an 18-month hole before the
Latest frontier, where SKIP ships 84 — twelve in each of 2019–2025 — and closes
it. On a *whole-history* pool (the corpus, OpenAlex, a complete live pool),
STOP's count is the honest answer: the prefix of an all-time ranking *is* the
landmark band, tau-banded Latest widens back to meet it, and SKIP-banding there
would admit the best of a thin year over the 13th-best of a blockbuster one.
STOP's scalar output is also what makes it the trained model's regression
**label** — the role it was originally kept for.

Which rule a path *can* use is dictated by what pool it holds, not by taste:

* **Compute a count** (:func:`computed_cite_limit`) — every path holding a
  **whole-history ranking**, which since v5.13.0 is all three:
  the **offline S2 corpus** (the rule runs between the query's two phases, over
  the narrow ranking, before the winners are hydrated wide); **OpenAlex** (the
  STOP rule is *prefix-local* — it never reads past the first year to overflow —
  so a single server-sorted page holds everything it reads: see
  ``openalex._budgeted_landmarks``, and the "Predict" bullet below for what this
  retired); and a **complete live S2 pool** (a seed whose citer list ends before
  the offset ceiling — most seeds — is a whole history too, and ships the corpus
  shape: see ``semantic_scholar.traversal._complete_pool_relations``). One rule,
  three pools, the same count-for-a-ranked-prefix answer.
* **Select from the pool** (:func:`select_landmarks`) — the live S2 fallback's
  **truncated** pools only. The deep pager already holds the whole reachable pool
  before the trim, but when the offset ceiling cut it off, that pool is a recency
  sliver with no all-history ranking to prefix: a prefix strands the recent years,
  so it bands (SKIP) instead.
A third option — **predicting** the count from the seed's age and citation count
with a trained regressor — was retired from serving in v5.13.0 and its code
removed since. It existed for OpenAlex, on the premise that computing there meant
dragging the whole pool across the network (~30k citers for DQN) just to size a
trim. STOP's prefix-locality broke that premise: the number is computable from the
one page the predicted path was already fetching, without the model's ~21-citer
per-seed error.

Why whole-history pools prefix where truncated ones band is the subtlest thing
here — :func:`computed_cite_limit` argues it. Short version: a prefix of a
*whole-history* ranking is exactly what "Field Landmark" means, and Latest widens
back to meet it; a prefix of a *truncated* one is just the recent past twice over.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Sequence

from ...integrations.caps import UNBOUNDED_LANDMARK_CAP

log = logging.getLogger(__name__)

#: The per-year density cap ``K``: how many same-year papers a landmark view
#: tolerates before that year reads as a pile-up. **Fitted**, not hand-picked — a
#: parameter sweep over a labelled corpus settled on 12. The rules below apply it
#: directly; refit rather than nudge it.
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

    Originally this was the retired regressor's training label — kept scalar
    because a regression label has to be. Since the compute paths took over
    (corpus v5.11.0; everywhere v5.13.0) it is the serving rule
    :func:`computed_cite_limit` executes over every whole-history pool. It stops
    rather than skipping full buckets and walking on (as
    :func:`select_up_to_cap_per_year` does) because a prefix is what a
    whole-history ranking honestly ships; on a *truncated* pool the stop is the
    wrong move — see this module's docstring for the 29-vs-84 measurement on DQN.

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


def computed_cite_limit(citer_years: Sequence[int | None]) -> int:
    """The landmark ship count, **computed** from the pool rather than predicted.

    The one serving rule for every path holding a whole-history ranked pool —
    the **offline S2 corpus**, **OpenAlex** (via the one-page probe), and a
    **complete live S2 pool**. It runs the STOP rule
    (:func:`number_of_ranked_citers_before_a_single_year_overflows`) over the real
    years instead of estimating it from two seed features. The retired regressor's
    training label *is* this number, so this is that model's own answer with the
    estimation error taken out: measured across a 58-seed validation corpus the two
    distributions were near-identical (predicted mean 76.5, computed mean 75.9),
    but the model was ~21 out on any given seed.

    **Why a count here and a selection (:func:`select_landmarks`) on truncated
    live pools** — different pools want different rules:

    * A **truncated** live pool is a recency sliver (the newest ~9k citers) with
      no all-history ranking to prefix, and its Latest window can't reach back
      past it. A prefix there strands the recent years — DQN's top 29 are
      2019–2023 with nothing from 2024–2025, an 18-month hole. So it bands: SKIP.
    * A **whole-history** pool (corpus, OpenAlex, or a live list that ended
      before the ceiling) has Latest as a separate relation that widens back to
      meet the cluster (``bands.earliest_band_year``). A prefix here is exactly
      what "Field Landmark" means — the giants — and banding would instead force
      ``PER_YEAR_CAP`` nodes out of *every* year, admitting the best of a thin
      1970 over the 13th-best of a blockbuster year. It would also flatten the
      year distribution that the tau rule needs to read, breaking the Latest
      bands on these paths.

    Trimmed to the :data:`~atlas.integrations.caps.UNBOUNDED_LANDMARK_CAP`
    payload guard, as everywhere else. No *floor*, unlike the predicted path: a
    floor exists to stop a model guessing absurdly low, and a measurement can't
    — if the rule says 5, 5 is the honest answer.

    Args:
        citer_years: The whole ranked landmark pool's publication years, most-cited
            first, ``None`` where the corpus has no year for a citer.

    Returns:
        The number of ranked citers to ship.
    """
    ceiling = UNBOUNDED_LANDMARK_CAP
    computed = number_of_ranked_citers_before_a_single_year_overflows(
        citer_years, PER_YEAR_CAP)
    budget = min(computed, ceiling)
    log.info(
        "computed landmark budget %d of %d ranked citers (cap %d/year, ceiling %d)",
        budget, len(citer_years), PER_YEAR_CAP, ceiling,
    )
    return budget


def select_landmarks(citer_years: Sequence[int | None]) -> list[int]:
    """The app-facing landmark selection: the SKIP rule as the build serves it.

    The rule for the one pool that can't honestly prefix: the live S2
    fallback's **truncated** pools (a complete live pool takes
    :func:`computed_cite_limit` instead). The walk itself — admit up to
    :data:`PER_YEAR_CAP` per publication year, skipping citers whose year is
    already full — is :func:`select_up_to_cap_per_year`, which has the worked
    example; this wrapper only adds the ceiling and the log line.

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

    Trimmed to the shared payload guard, which (being a prefix of a
    citation-ranked selection) keeps the most-cited. In practice the guard
    can't bite here: this rule ships ``PER_YEAR_CAP × span`` and the live pool
    is truncated to a couple of dozen years at most (Hawking's reaches 1998, so
    348). It's defensive, and it keeps every sizing rule agreeing on the same
    ceiling.

    Args:
        citer_years: The ranked landmark pool's publication years, most-cited
            first, ``None`` where the provider gave no year.

    Returns:
        The indices of ``citer_years`` to ship, ascending (so the shipped band
        stays most-cited-first).
    """
    keep = select_up_to_cap_per_year(citer_years)
    keep = keep[:UNBOUNDED_LANDMARK_CAP]
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

    Factored out of :func:`select_landmarks` so the exact serving rule can be run
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
