"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
Pull a stratified corpus of seed papers + their citer-year distributions.

The data-collection stage of the adaptive-``cite_limit`` pipeline (see this
package's README, and ``docs/landmark-vocabulary.md`` for every term below). For
each sampled seed it records the two *cheap* features the graph build already has
on a seed node — publication age and citation count — plus the model's **label**,
the ``citers_before_overflow`` column: how deep into the seed's citation-ranked
citer list you get before a single publication year overflows ``PER_YEAR_CAP``
(the STOP rule, ``features.number_of_ranked_citers_before_a_single_year_overflows``).
A model fit against that label learns how big the landmark window should be
*without any hand-tuned constants*.

Seeds are sampled across a grid of publication-year × citation-count strata so
the fit sees the whole spectrum, not just mega-papers. The four **worked-example**
seeds (Hawking / DQN / QMIX / AIAYN) are always included for eyeballing — the
``is_worked_example`` column.

Run from the repo root (reuses the app's throttled OpenAlex client):

    uv run python -m ml_pipelines.cite_budget.collect

Writes ``src/ml_pipelines/cite_budget/corpus.csv`` (committed, so training is reproducible
without a re-pull). ``train.py`` calls :func:`collect` directly when asked to
refresh. OpenAlex results shift slowly, so a re-run reproduces a similar corpus.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

import csv
import logging
import random
from collections import Counter
from pathlib import Path

from atlas.integrations.openalex import client

from .features import (
    PER_YEAR_CAP,
    PER_YEAR_CAP_GRID,
    number_of_ranked_citers_before_a_single_year_overflows,
)

log = logging.getLogger("collect")

# How many of a seed's top citers to inspect. Matches the app's payload guard
# (integrations.caps.UNBOUNDED_LANDMARK_CAP) — the pool the density rule
# would trim from at build time.
POOL_SIZE = 500
PAGE = 200  # OpenAlex per-page cap for the citer pages

# The sampling grid. Citation bands span three orders of magnitude; year bands
# span the modern-CS era plus the older classics. Physics/ML seeds both land
# here — the grid is field-agnostic on purpose.
CITATION_BANDS = [(100, 500), (500, 2_000), (2_000, 10_000), (10_000, 400_000)]
YEAR_BANDS = [(1960, 1990), (1990, 2005), (2005, 2013), (2013, 2020), (2020, 2024)]
SEEDS_PER_STRATUM = 3
SAMPLE_SEED = 20260710  # deterministic sampling for a reproducible corpus

# Always-included anchors (label, OpenAlex work id) — the four working examples
# the heuristic is meant to serve. Resolved live so their features stay current.
ANCHORS = [
    ("Hawking Radiation", "W2090386790"),
    ("DQN", "W2145339207"),
    ("QMIX", "W2794643322"),
    ("Attention Is All You Need", "W2626778328"),
]

CORPUS_PATH = Path(__file__).with_name("corpus.csv")

FIELDS = (["work_id", "label", "year", "cited_by_count", "pool_size",
           "densest_year_count", "citers_before_overflow"]
          + [f"citers_before_overflow_cap{cap}" for cap in PER_YEAR_CAP_GRID]
          + ["is_worked_example"])


def citer_years(work_id: str, *, to_year: int | None = None) -> list[int]:
    """Publication years of a seed's top-``POOL_SIZE`` citers, in citation rank.

    Pages the same ``cites:<id>`` / ``cited_by_count:desc`` query the app ships
    for landmarks, so the collected distribution is exactly what the build would
    trim. Citers with no ``publication_year`` are dropped (they can't inform a
    per-year density count).

    Args:
        work_id: The seed's bare OpenAlex work id (``W…``).
        to_year: When set, cap the query at ``to_publication_date:<to_year>-12-31``
            — the exact date bound the build's landmark query applies (the
            ``latest_gap`` collector passes the landmark-era cutoff; this
            pipeline's own label deliberately spans all years).

    Returns:
        Up to ``POOL_SIZE`` publication years, ordered by descending citer
        citation count.
    """
    filter_clause = f"cites:{work_id}"
    if to_year is not None:
        filter_clause += f",to_publication_date:{to_year}-12-31"
    years: list[int] = []
    cursor = "*"
    while len(years) < POOL_SIZE and cursor:
        payload = client.request(client.works_url({
            "filter": filter_clause,
            "sort": "cited_by_count:desc",
            "select": "publication_year",
            "per-page": str(PAGE),
            "cursor": cursor,
        }))
        results = payload.get("results") or []
        if not results:
            break
        years.extend(work["publication_year"] for work in results if work.get("publication_year"))
        cursor = (payload.get("meta") or {}).get("next_cursor")
    return years[:POOL_SIZE]


def seed_row(label: str, work: dict) -> dict | None:
    """Assemble one corpus row (features + label) for a resolved seed work.

    Args:
        label: A human label for the seed (for eyeballing the anchors).
        work: A raw OpenAlex work object carrying ``id``, ``publication_year``,
            ``cited_by_count``.

    Returns:
        The row dict, or None when the work lacks the fields the study needs or
        has too few citers to label.
    """
    work_id = (work.get("id") or "").rsplit("/", 1)[-1]
    year = work.get("publication_year")
    cited_by = work.get("cited_by_count")
    if not work_id or not year or not cited_by:
        return None
    years = citer_years(work_id)
    if len(years) < PER_YEAR_CAP:  # too few citers to form a meaningful label
        return None
    densest = max(Counter(years).values())
    row = {
        "work_id": work_id,
        "label": label,
        "year": year,
        "cited_by_count": cited_by,
        "pool_size": len(years),
        "densest_year_count": densest,
        "citers_before_overflow": number_of_ranked_citers_before_a_single_year_overflows(
            years, PER_YEAR_CAP),
    }
    # The K-grid, for the notebook's sweep — the cap12 column equals the label
    # column, since PER_YEAR_CAP is 12.
    for cap in PER_YEAR_CAP_GRID:
        row[f"citers_before_overflow_cap{cap}"] = (
            number_of_ranked_citers_before_a_single_year_overflows(years, cap))
    return row


def sample_stratum(year_band: tuple[int, int], cite_band: tuple[int, int],
                   rng: random.Random) -> list[dict]:
    """Sample seed works from one (year × citation) stratum.

    Pulls a page of works in the band sorted by citation count, then randomly
    picks ``SEEDS_PER_STRATUM`` of them so the corpus isn't all the single
    most-cited paper per cell.

    Args:
        year_band: ``(from_year, to_year)`` inclusive-exclusive publication window.
        cite_band: ``(from_cites, to_cites)`` citation-count window.
        rng: Seeded RNG for reproducible sampling.

    Returns:
        Up to ``SEEDS_PER_STRATUM`` corpus rows from this stratum.
    """
    from_year, to_year = year_band
    from_cites, to_cites = cite_band
    payload = client.request(client.works_url({
        "filter": (
            f"from_publication_date:{from_year}-01-01,"
            f"to_publication_date:{to_year}-01-01,"
            f"cited_by_count:{from_cites}-{to_cites},"
            "type:article,has_references:true"
        ),
        "sort": "cited_by_count:desc",
        "select": "id,display_name,publication_year,cited_by_count",
        "per-page": "50",
    }))
    candidates = payload.get("results") or []
    rng.shuffle(candidates)
    rows: list[dict] = []
    for work in candidates:
        if len(rows) >= SEEDS_PER_STRATUM:
            break
        row = seed_row(work.get("display_name") or "?", work)
        if row:
            rows.append(row)
            log.info("  seed %s (%d, %d cites) -> label=%d",
                     row["work_id"], row["year"], row["cited_by_count"],
                     row["citers_before_overflow"])
    return rows


def collect() -> list[dict]:
    """Collect the full corpus (anchors + all strata) and return its rows.

    Returns:
        One row dict per seed, in the :data:`FIELDS` schema.
    """
    rng = random.Random(SAMPLE_SEED)
    rows: list[dict] = []
    seen: set[str] = set()

    log.info("Anchors:")
    for label, work_id in ANCHORS:
        work = client.request(client.entity_url(
            work_id, {"select": "id,display_name,publication_year,cited_by_count"}))
        row = seed_row(label, work)
        if row and row["work_id"] not in seen:
            row["is_worked_example"] = 1
            rows.append(row)
            seen.add(row["work_id"])
            log.info("  %s (%d, %d cites) -> n*=%d",
                     label, row["year"], row["cited_by_count"], row["citers_before_overflow"])

    for year_band in YEAR_BANDS:
        for cite_band in CITATION_BANDS:
            log.info("Stratum year %s x cites %s:", year_band, cite_band)
            for row in sample_stratum(year_band, cite_band, rng):
                if row["work_id"] in seen:
                    continue
                row.setdefault("is_worked_example", 0)
                rows.append(row)
                seen.add(row["work_id"])
    return rows


def write_corpus(rows: list[dict], path: Path = CORPUS_PATH) -> None:
    """Write corpus rows to ``path`` as CSV in the :data:`FIELDS` schema.

    Args:
        rows: Corpus rows from :func:`collect`.
        path: Destination CSV path.
    """
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    log.info("Wrote %d seeds to %s", len(rows), path)


def main() -> None:
    """Collect the corpus and write ``corpus.csv``."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    write_corpus(collect())


if __name__ == "__main__":
    main()
