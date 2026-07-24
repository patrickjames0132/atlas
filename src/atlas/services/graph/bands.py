"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
Serving the adaptive latest-band boundary — closing the landmark→latest gap.

Every term here — landmark, band, tail edge, ``tau``, ``max_span`` — is defined
once, with worked examples, in ``docs/landmark-vocabulary.md``; the sibling
``budget`` module sizes the landmark band, this one places the Latest boundary.

Field Landmarks are a seed's all-time most-cited citers (any year); Latest
Publications fills recent years evenly with one ``cited_by_count`` query *per
year*, up to the current year. Those bands used to start at a **fixed** lower
edge (``LATEST_NUMBER_OF_BANDS``). For an *old* seed whose landmark
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

``tau`` and ``max_span`` are **fitted, not hand-tuned**: chosen on a labelled
64-seed OpenAlex corpus (2026-07-11) and, until that offline pipeline was removed,
shipped in a model artifact this module loaded at build time. The fitted values are
now inlined below as :data:`TAU` and :data:`MAX_SPAN` — same numbers, same rule,
one less moving part. Treat them as measurements: refit if the boundary ever needs
revisiting rather than nudging them by hand.

The boundary is a property of each seed's landmark *distribution*, not of its
age/citations (a feature regression on those was tried and fails), so the input is
the fetched landmark-year list, not a seed feature vector.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

import logging
from collections import Counter

log = logging.getLogger(__name__)

#: The fraction of the peak year's landmark count a year must still reach to count
#: as part of the dense cluster. **Fitted** on a labelled 64-seed OpenAlex corpus
#: (2026-07-11), which measured 94 landmark→latest gap-years closed at a misdate
#: movement of 0.016.
TAU = 0.25

#: How far back before the landmark cutoff a band start may reach, at most — the
#: query-cost cap, fitted alongside :data:`TAU` (mean 6.45 bands per seed, max 9).
MAX_SPAN = 7

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


def earliest_band_year(landmark_years: list[int], landmark_max_year: int) -> int | None:
    """The first year the per-year Latest bands should cover, adapted per seed.

    Applies the tail-edge rule with the fitted :data:`TAU` and :data:`MAX_SPAN`:
    start the bands where the landmark cluster's density falls off
    (:func:`tail_edge`), floored so the start reaches back at most
    :data:`MAX_SPAN` years before the landmark cutoff (bounded query cost). No
    "only widen" clamp — a young seed whose cluster edge is recent starts its
    bands there. Always on (there is no toggle — banding is how the app sizes
    itself) and config-free.

    Falls back (returns None → the caller keeps the fixed ``number_of_bands``
    span) when the seed has too few dated landmark years to place a trustworthy
    boundary.

    Args:
        landmark_years: Publication years of the seed's *shipped* landmark
            citers (the budget-trimmed pool the build already fetched).
        landmark_max_year: The last landmark-era year — the ``max_span`` floor is
            measured back from it.

    Returns:
        The adaptive first band year, or None to keep the fixed span.
    """
    dated = [year for year in landmark_years if year]
    if len(dated) < MIN_LANDMARK_YEARS:
        return None
    edge = tail_edge(dated, TAU)
    floor = landmark_max_year - MAX_SPAN + 1
    band_start = max(edge, floor)  # cap query cost; the density edge is the primary pick
    log.info(
        "adaptive latest band starts %d (density edge %d, floor %d) from %d landmark years",
        band_start, edge, floor, len(dated),
    )
    return band_start
