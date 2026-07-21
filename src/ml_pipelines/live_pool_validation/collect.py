"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
Collect the live-pool validation corpus: simulated truncated pools vs. the models.

The data-collection stage of the live-pool validation study (see this package's
README; ``docs/landmark-vocabulary.md`` defines every term below). For every seed
in the ``cite_budget`` corpus it simulates **the pool the live S2 fallback would
actually hold** — the newest :data:`REACHABLE_CITERS` citers, exactly the deep
pager's truncation — by querying the offline citations corpus, then records side
by side:

* ``citers_before_overflow_reachable`` — the **STOP rule run exactly** on that
  truncated pool. Computable at serve time, so it is the null hypothesis's
  champion: why predict what you can compute?
* ``selected_up_to_cap_per_year`` — the size of the **SKIP rule's** selection,
  i.e. what v5.5.0 actually ships.
* Both **age origins** for the model's prediction: measured from the oldest citer
  in the pool (``predicted_budget_age_from_oldest_citer`` — Patrick's proposal)
  and from the seed (``predicted_budget_age_from_seed`` — the pre-v5.5.0
  behavior, kept as the broken baseline).
* ``citers_before_overflow_full`` — the same STOP rule over the corpus's whole
  ranked pool (the corpus-models ticket's label re-collection).
* ``band_start`` — the latest-gap boundary the tau rule places on the truncated
  pool's shipped landmarks (``bands.earliest_band_year``).

Runs on the machine that holds the ingested corpus (the parquet root configured
in ``config.storage.s2_corpus``); everything but one OpenAlex id-mapping fetch
per seed is local. Run from the repo root:

    uv run python -m ml_pipelines.live_pool_validation.collect

Writes ``corpus.csv`` beside this module (committed after a run, so the analysis
notebook is reproducible without the corpus machine). ``research/
live_pool_validation/analyze.ipynb`` is the verdict.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

import csv
import datetime
import logging
from pathlib import Path
from typing import Any

import duckdb

from atlas.integrations.openalex import client as openalex_client
from atlas.integrations.openalex.nodes import arxiv_id_from_work
from atlas.integrations.semantic_scholar.corpus import paths as corpus_paths
from atlas.integrations.semantic_scholar.corpus.ingest import NBUCKETS
from atlas.integrations.semantic_scholar.corpus.paths import read_current_release
from atlas.integrations.semantic_scholar.traversal import REACHABLE_CITERS
from atlas.services.graph import bands, budget

from ..cite_budget import collect as cite_budget_collect

log = logging.getLogger("collect")

#: How deep the full-history ranking is labelled — matches ``cite_budget``'s
#: ``POOL_SIZE`` (and the app's unbounded landmark cap) so ``citers_before_overflow_full`` is
#: comparable with the committed OpenAlex labels.
RANK_POOL_SIZE = cite_budget_collect.POOL_SIZE

CORPUS_PATH = Path(__file__).with_name("corpus.csv")

FIELDS = [
    "work_id", "label", "is_worked_example", "arxiv_id", "doi", "corpus_id",
    "s2_year", "s2_citation_count",
    "citer_count", "pool_size", "truncated", "oldest_pool_year", "newest_pool_year",
    "citers_before_overflow_reachable", "selected_up_to_cap_per_year",
    "predicted_budget_age_from_seed", "predicted_budget_age_from_oldest_citer",
    "citers_before_overflow_full", "corpus_rank_pool",
    "band_start", "landmark_max_year",
]


class CorpusReader:
    """Read-only queries against the active ingested corpus, for this study.

    Mirrors ``corpus.source.DuckDBCitationSource``'s glob construction but asks
    different questions (a seed's *entire* deduped citer set, seed rows by DOI),
    so it holds its own connection rather than growing the app's serving seam
    with study-only methods.
    """

    def __init__(self) -> None:
        """Open the active release, or raise when this machine has no corpus.

        Raises:
            RuntimeError: When no ingested corpus release is active here — the
                collector must run on the corpus machine.
        """
        root = corpus_paths.corpus_root()
        release_id = read_current_release(root) if root and root.exists() else None
        if not release_id:
            raise RuntimeError(
                "no active corpus release — run this collector on the machine whose "
                "config.storage.s2_corpus holds the ingested corpus"
            )
        paths = corpus_paths.release_paths(release_id)
        self.release_id = release_id
        self._papers_glob = (paths.parquet_dataset("papers") / "*.parquet").as_posix()
        self._citations_root = paths.parquet_dataset("citations").as_posix()
        self._arxiv_index_glob = (paths.parquet / "arxiv_index" / "*.parquet").as_posix()
        self._connection = duckdb.connect(":memory:")

    def resolve_seeds(self, seeds: list[dict[str, Any]]) -> None:
        """Fill each seed's ``corpus_id`` (and S2-side features) in place.

        Resolution is fully local: the arXiv index first, then the papers
        table by DOI (both in one query per route, not one per seed — the DOI
        route scans the 200M-row papers Parquet). A seed matching neither keeps
        ``corpus_id=None`` and is skipped by :func:`collect` with a log line.

        Args:
            seeds: Seed dicts carrying ``arxiv_id`` / ``doi`` from the OpenAlex
                mapping step; mutated to add ``corpus_id`` / ``s2_year`` /
                ``s2_citation_count``.
        """
        by_arxiv = {seed["arxiv_id"]: seed for seed in seeds if seed.get("arxiv_id")}
        if by_arxiv:
            rows = self._connection.execute(
                f"SELECT arxiv_id, corpusid FROM read_parquet('{self._arxiv_index_glob}') "
                "WHERE arxiv_id IN (SELECT unnest(?))",
                [list(by_arxiv)],
            ).fetchall()
            for arxiv_id, corpus_id in rows:
                by_arxiv[arxiv_id]["corpus_id"] = int(corpus_id)
        by_doi = {seed["doi"].lower(): seed for seed in seeds
                  if seed.get("doi") and not seed.get("corpus_id")}
        if by_doi:
            rows = self._connection.execute(
                f"SELECT lower(doi), corpusid FROM read_parquet('{self._papers_glob}') "
                "WHERE lower(doi) IN (SELECT unnest(?))",
                [list(by_doi)],
            ).fetchall()
            for doi, corpus_id in rows:
                by_doi[doi]["corpus_id"] = int(corpus_id)
        resolved = [seed for seed in seeds if seed.get("corpus_id")]
        if resolved:
            features = self._connection.execute(
                f"SELECT corpusid, year, citationcount FROM read_parquet('{self._papers_glob}') "
                "WHERE corpusid IN (SELECT unnest(?))",
                [[seed["corpus_id"] for seed in resolved]],
            ).fetchall()
            by_id = {seed["corpus_id"]: seed for seed in resolved}
            for corpus_id, year, citation_count in features:
                by_id[int(corpus_id)]["s2_year"] = year
                by_id[int(corpus_id)]["s2_citation_count"] = citation_count

    def citers(self, corpus_id: int) -> list[dict[str, Any]]:
        """Every distinct citer of a seed, with the fields the study ranks on.

        Groups by the citing paper before the join — S2 ships every edge about
        twice across overlapping export batches (see the Upstream entry in
        ``docs/bugs.md``), and a study of pool *sizes* would be off by 2x
        without the dedupe.

        Args:
            corpus_id: The seed's S2 ``corpusid``.

        Returns:
            One ``{"year", "citation_count", "pub_date"}`` dict per citing
            paper, unordered (the metrics function does its own sorting).
        """
        bucket = corpus_id % NBUCKETS
        citations_glob = f"{self._citations_root}/bucket={bucket}/*.parquet"
        rows = self._connection.execute(
            "WITH edges AS ("
            f"  SELECT DISTINCT citingcorpusid FROM read_parquet('{citations_glob}', "
            "   hive_partitioning=false) WHERE citedcorpusid = ?)"
            "SELECT p.year, p.citationcount, p.publicationdate "
            f"FROM edges JOIN read_parquet('{self._papers_glob}') p "
            "ON p.corpusid = edges.citingcorpusid",
            [corpus_id],
        ).fetchall()
        return [{"year": year, "citation_count": citation_count, "pub_date": pub_date}
                for year, citation_count, pub_date in rows]


def pool_metrics(citers: list[dict[str, Any]], *, seed_year: int | None,
                 seed_citation_count: int, as_of_year: int,
                 reachable: int = REACHABLE_CITERS) -> dict[str, Any]:
    """Every per-seed measurement of the study, from one citer set.

    Simulates the live pool (newest ``reachable`` citers by publication date —
    the deep pager's order; undated citers sort last, a known approximation of
    S2's opaque ordering for them), then runs the exact rules and both model
    anchorings over it, and the full-history label over the whole ranked set.

    Args:
        citers: The seed's distinct citers (``year`` / ``citation_count`` /
            ``pub_date`` each), unordered.
        seed_year: The seed's own publication year (S2's record), None when the
            corpus has none — the seed-anchored prediction is skipped then.
        seed_citation_count: The seed's total citation count (S2's record).
        as_of_year: The year age features are measured from (today's, at
            collection time).
        reachable: The live pager's truncation — parameterized so the offline
            tests can exercise truncation with a tiny synthetic corpus.

    Returns:
        The measurement columns of one corpus row (everything in
        :data:`FIELDS` from ``citer_count`` on).
    """
    newest_first = sorted(citers, key=lambda citer: citer["pub_date"] or "", reverse=True)
    pool = newest_first[:reachable]
    truncated = len(citers) > reachable

    def ranked_years(entries: list[dict[str, Any]]) -> list[int | None]:
        """Publication years of ``entries`` ranked most-cited first (the serve ranking)."""
        in_rank = sorted(entries, key=lambda citer: citer["citation_count"] or 0, reverse=True)
        return [citer["year"] for citer in in_rank]

    pool_years = ranked_years(pool)
    selection = budget.select_up_to_cap_per_year(pool_years)
    selected_years = [pool_years[index] for index in selection]
    dated_selected = [year for year in selected_years if year]
    landmark_max_year = max(dated_selected) if dated_selected else None
    dated_pool = [citer["year"] for citer in pool if citer["year"] is not None]
    oldest_pool_year = min(dated_pool) if dated_pool else None

    full_years = ranked_years(citers)[:RANK_POOL_SIZE]
    # Bound once — the app's own STOP rule, run over the two pools this study
    # compares (see docs/landmark-vocabulary.md for STOP vs SKIP).
    citers_before_overflow = budget.number_of_ranked_citers_before_a_single_year_overflows
    return {
        "citer_count": len(citers),
        "pool_size": len(pool),
        "truncated": int(truncated),
        "oldest_pool_year": oldest_pool_year,
        "newest_pool_year": max(dated_pool) if dated_pool else None,
        "citers_before_overflow_reachable": citers_before_overflow(
            pool_years, budget.PER_YEAR_CAP),
        "selected_up_to_cap_per_year": len(selection),
        "predicted_budget_age_from_seed": (
            budget.predicted_budget(seed_year, seed_citation_count, as_of_year=as_of_year)
            if seed_year else None),
        "predicted_budget_age_from_oldest_citer": (
            budget.predicted_budget(oldest_pool_year, seed_citation_count, as_of_year=as_of_year)
            if oldest_pool_year else None),
        "citers_before_overflow_full": citers_before_overflow(
            full_years, budget.PER_YEAR_CAP),
        "corpus_rank_pool": len(full_years),
        "band_start": (bands.earliest_band_year(dated_selected, landmark_max_year)
                       if landmark_max_year else None),
        "landmark_max_year": landmark_max_year,
    }


def seed_identifiers(work_id: str) -> dict[str, Any]:
    """Map one OpenAlex work to the ids the corpus can resolve (arXiv id, DOI).

    The one live call per seed — the ``cite_budget`` corpus stores only work
    ids, and the offline corpus resolves by arXiv id or DOI. Uses the app's
    throttled OpenAlex client and its own arXiv-id extraction so the mapping
    matches what a build would see.

    Args:
        work_id: The seed's bare OpenAlex work id (``W…``).

    Returns:
        ``{"arxiv_id", "doi"}`` — either may be None.
    """
    work = openalex_client.request(openalex_client.entity_url(work_id, {}))
    doi_url = work.get("doi") or ""
    return {
        "arxiv_id": arxiv_id_from_work(work),
        "doi": doi_url.removeprefix("https://doi.org/") or None,
    }


def collect() -> list[dict[str, Any]]:
    """Run the whole study collection over the ``cite_budget`` seed corpus.

    Returns:
        One row dict per resolvable seed, in the :data:`FIELDS` schema.

    Raises:
        RuntimeError: When no ingested corpus release is active on this machine.
    """
    reader = CorpusReader()
    log.info("corpus release %s", reader.release_id)
    as_of_year = datetime.date.today().year

    with cite_budget_collect.CORPUS_PATH.open(newline="") as handle:
        seeds = [
            {"work_id": row["work_id"], "label": row["label"],
             "is_worked_example": int(row["is_worked_example"])}
            for row in csv.DictReader(handle)
        ]
    log.info("mapping %d cite_budget seeds to arXiv/DOI ids via OpenAlex…", len(seeds))
    for seed in seeds:
        seed.update(seed_identifiers(seed["work_id"]))
    reader.resolve_seeds(seeds)

    rows: list[dict[str, Any]] = []
    for seed in seeds:
        if not seed.get("corpus_id"):
            log.info("  %s (%s): unresolvable in the corpus — skipped",
                     seed["label"], seed["work_id"])
            continue
        citers = reader.citers(seed["corpus_id"])
        if not citers:
            log.info("  %s: no edges in the corpus — skipped", seed["label"])
            continue
        metrics = pool_metrics(
            citers, seed_year=seed.get("s2_year"),
            seed_citation_count=seed.get("s2_citation_count") or 0,
            as_of_year=as_of_year)
        row = {field: seed.get(field) for field in FIELDS if field not in metrics}
        row.update(metrics)
        rows.append(row)
        log.info(
            "  %s: %d citers (pool %d%s, oldest %s) stop/reachable=%d skip=%d "
            "predicted from seed/oldest=%s/%s stop/full=%d band_start=%s",
            seed["label"], metrics["citer_count"], metrics["pool_size"],
            " TRUNCATED" if metrics["truncated"] else "", metrics["oldest_pool_year"],
            metrics["citers_before_overflow_reachable"],
            metrics["selected_up_to_cap_per_year"],
            metrics["predicted_budget_age_from_seed"],
            metrics["predicted_budget_age_from_oldest_citer"],
            metrics["citers_before_overflow_full"], metrics["band_start"],
        )
    return rows


def write_corpus(rows: list[dict[str, Any]], path: Path = CORPUS_PATH) -> None:
    """Write the study rows to ``path`` as CSV in the :data:`FIELDS` schema.

    Args:
        rows: Study rows from :func:`collect`.
        path: Destination CSV path.
    """
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    log.info("Wrote %d seeds to %s", len(rows), path)


def main() -> None:
    """Collect the study corpus and write ``corpus.csv``."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    write_corpus(collect())


if __name__ == "__main__":
    main()
