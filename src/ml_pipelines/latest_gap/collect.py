"""Pull each corpus seed's landmark-era citer-year distribution from OpenAlex.

The data-collection stage of the ``latest_gap`` pipeline (see this package's
README). The study asks: *where does a seed's landmark cluster tail off?* — so
what it needs, per seed, is the publication years of exactly the citers the
build would ship as Field Landmarks: the top citers by citation count, capped at
the landmark-era cutoff (``openalex.landmark_max_year``), trimmed to the served
adaptive budget (``budget.predicted_budget``).

Seeds are **reused from the ``cite_budget`` corpus** (same 64 stratified seeds
incl. the four anchors) rather than re-sampled: the two studies then describe
the same population, the notebook can cross-reference budgets, and collection
stays at one paged citer query per seed instead of re-running the stratum
sampler.

Run from the repo root (reuses the app's throttled OpenAlex client):

    uv run python -m ml_pipelines.latest_gap.collect

Writes ``src/ml_pipelines/latest_gap/corpus.csv`` (committed, so training is
reproducible without a re-pull). ``train.py`` calls :func:`collect` directly
when asked to refresh.
"""

from __future__ import annotations

import csv
import datetime
import logging
from pathlib import Path

from atlas.integrations import openalex
from atlas.services.graph import budget

from ..cite_budget import collect as cite_budget_collect

log = logging.getLogger("collect")

CORPUS_PATH = Path(__file__).with_name("corpus.csv")

FIELDS = ["work_id", "label", "year", "cited_by_count", "is_worked_example",
          "as_of_year", "landmark_max_year", "predicted_budget", "pool_size", "citer_years"]


def seed_row(source_row: dict, *, as_of: datetime.date) -> dict | None:
    """Assemble one corpus row: the seed's shipped-landmark year distribution.

    Args:
        source_row: A ``cite_budget`` corpus row (``work_id``, ``label``,
            ``year``, ``cited_by_count``, ``is_worked_example``).
        as_of: The collection date — fixes the landmark-era cutoff and the age
            the budget model sees, and is recorded in the row so training can
            reproduce the exact same trim later.

    Returns:
        The row dict (ranked citer years serialized space-separated), or None
        when the seed's budget can't be predicted or it has too few dated
        citers to describe a distribution.
    """
    year = int(source_row["year"])
    cited_by = int(source_row["cited_by_count"])
    landmark_cutoff = openalex.landmark_max_year(as_of)
    landmark_budget = budget.predicted_budget(year, cited_by, as_of_year=as_of.year)
    if landmark_budget is None:  # no trained cite_budget artifact — can't mirror a build
        return None
    years = cite_budget_collect.citer_years(source_row["work_id"], to_year=landmark_cutoff)
    trimmed = years[:landmark_budget]
    if len(trimmed) < 10:  # too few dated landmarks to call anything a distribution
        return None
    return {
        "work_id": source_row["work_id"],
        "label": source_row["label"],
        "year": year,
        "cited_by_count": cited_by,
        "is_worked_example": int(source_row["is_worked_example"]),
        "as_of_year": as_of.year,
        "landmark_max_year": landmark_cutoff,
        "predicted_budget": landmark_budget,
        "pool_size": len(trimmed),
        "citer_years": " ".join(str(citer_year) for citer_year in trimmed),
    }


def collect() -> list[dict]:
    """Collect the landmark-year distribution for every ``cite_budget`` seed.

    Returns:
        One row dict per seed, in the :data:`FIELDS` schema.

    Raises:
        FileNotFoundError: When the ``cite_budget`` corpus hasn't been collected.
    """
    as_of = datetime.date.today()
    with cite_budget_collect.CORPUS_PATH.open(newline="") as handle:
        source_rows = list(csv.DictReader(handle))
    rows: list[dict] = []
    for source_row in source_rows:
        row = seed_row(source_row, as_of=as_of)
        if row is None:
            log.info("  skipped %s (%s)", source_row["work_id"], source_row["label"])
            continue
        rows.append(row)
        log.info("  seed %s (%s, %s) -> predicted budget %d, %d landmark years",
                 row["work_id"], row["label"], row["year"],
                 row["predicted_budget"], row["pool_size"])
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
