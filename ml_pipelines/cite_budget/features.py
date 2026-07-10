"""The training-only label: a seed's "density budget" n*.

The model's *features* (age, log-citations) are the app's contract — imported
from ``atlas.services.graph.budget`` so training and serving agree. The *label*
is training-only and lives here.

**What ``n*`` is.** Take the seed's citers ranked by citation count (most-cited
first — the exact order the app ships as landmarks). A *prefix* of that ranked
list is simply "the first N citers, from the top" — the N most-cited ones, in
order. ``n*`` is the length of the **longest prefix in which no single
publication year appears more than ``DENSITY_CAP`` times.** We walk down the
ranked list admitting citers one at a time, tallying their publication years,
and stop the instant some year would take its (``DENSITY_CAP`` + 1)-th slot;
``n*`` is how many we'd admitted just before that break (see
:func:`density_budget`).

**Worked example** (``cap=2`` for brevity). Ranked citer years
``[2018, 2019, 2018, 2020, 2018, …]``: 2018 appears at positions 0, 2, 4; its
*third* appearance (position 4) trips ``cap=2``, so ``n* = 4`` — we keep the
prefix ``[2018, 2019, 2018, 2020]`` and stop before admitting that third 2018.

**Why it's "clutter".** ``cap`` is how many same-year papers a landmark view
tolerates before that year reads as a pile-up. A young, hot paper's top citers
cram into one or two years, so a single year floods almost immediately and
``n*`` is small; an old classic's spread across decades, so no year floods until
deep into the list and ``n*`` is large. Same top-500 citers, very different
``n*`` — that gap is the temporal clutter the model learns to predict from age +
citations, with no hand-tuning.
"""

from __future__ import annotations

from collections import Counter

#: The per-year density cap K. A landmark view stays legible as long as no
#: single year floods it; the research notebook swept K and settled on 12.
DENSITY_CAP = 12

#: K-grid stored alongside the label so the notebook can show the response
#: curve without re-fetching — ``n_star_k{K}`` columns; k12 equals the label.
DENSITY_CAP_GRID = (4, 8, 12, 16, 20)


def density_budget(citer_years: list[int], cap: int) -> int:
    """Longest prefix of ``citer_years`` (its first N, from the top) whose densest single year holds ``≤ cap``.

    Walks the citation-ranked citer years from the top, accumulating a per-year
    count; the budget is the position just before some year's running count first
    exceeds ``cap`` (i.e. the length of the prefix admitted so far). A pool that
    never trips the cap yields its full length. See the module docstring for the
    "prefix"/clutter framing and a worked example.

    Args:
        citer_years: Citer publication years in citation rank (most-cited first).
        cap: The per-year density cap ``K``.

    Returns:
        The density-criterion landmark budget ``n*`` — e.g.
        ``density_budget([2018, 2019, 2018, 2020, 2018], cap=2) == 4`` (the third
        2018 trips ``cap=2`` at index 4).
    """
    per_year: Counter[int] = Counter()
    for index, year in enumerate(citer_years):
        per_year[year] += 1
        if per_year[year] > cap:
            return index
    return len(citer_years)
