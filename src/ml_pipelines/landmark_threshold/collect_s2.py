"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
Collect the S2 fitting corpus: sampled seeds + their citers' (age, citation-count) distributions.

The data stage of the landmark-threshold pipeline's **S2 curve**. For a
stratified sample of seeds drawn from the offline corpus, it records — per seed —
the seed's own ``(year, citation_count)`` and the full distribution of its citers
as ``(citer_year, citer_citation_count, count)`` rows. That distribution is
everything the fit needs: the predicate classifies each citer from its age
(``now − citer_year``) and its own citation count, so a per-``(year, count)``
histogram reproduces any candidate rule's landmark count exactly, with no re-query.

Why the corpus and not OpenAlex: **sample size**. The corpus holds every citation
edge with the citer's own citation count (``papers.citationcount``), so a couple of
DuckDB queries sample thousands of seeds and their *complete* citer sets — no rate
limits, no 9,000-citer paging ceiling. The OpenAlex curve is fit separately from a
throttled live run (a sibling collector, later); the two never share a scale.

Runs on the machine holding the ingested corpus (``config.storage.s2_corpus``).
Everything is local — no network at all. Run from the repo root:

    uv run python -m ml_pipelines.landmark_threshold.collect_s2

Writes ``corpus_s2.csv.gz`` beside this module (committed, so the fit is
reproducible without the corpus machine). The corpus shifts only when a new S2
release is ingested, so a re-run reproduces a near-identical sample.

**Why gzipped**, unlike its sibling pipelines' plain ``corpus.csv``: this study
needs a far denser sample (1,500 seeds against their handful), and a seed's citer
bins are dominated by the *wide* high-citation tail — thousands of distinct
``cited_by`` values, mostly one citer each. That is ~1.5M rows / 67 MB of genuinely
irreducible fit input; pruning harder barely dents it (at a floor of 50 it is still
37 MB). Gzip is exactly lossless and lands it at ~6 MB.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

import csv
import gzip
import logging
from pathlib import Path
from typing import Any, TextIO

import duckdb

from atlas.integrations.semantic_scholar.corpus import paths as corpus_paths
from atlas.integrations.semantic_scholar.corpus.ingest import NBUCKETS
from atlas.integrations.semantic_scholar.corpus.paths import read_current_release

log = logging.getLogger("collect")

# The sampling grid — the same shape ``cite_budget`` uses, so the two studies
# span the same spectrum. Citation bands cover three orders of magnitude; year
# bands cover the modern-CS era plus the older classics. Both are
# inclusive-exclusive.
YEAR_BANDS = [(1960, 1990), (1990, 2005), (2005, 2013), (2013, 2020), (2020, 2025)]
CITATION_BANDS = [(100, 500), (500, 2_000), (2_000, 10_000), (10_000, 400_000)]

#: How many seeds to sample from each (year × citation) stratum. The corpus is
#: local and unlimited, so this is far larger than ``cite_budget``'s 3 — the fit
#: has to hold *every* seed inside a tight 20–40 band across the whole spectrum,
#: which only a dense sample can reveal. Small strata (e.g. old + hyper-cited)
#: hold fewer papers than this and yield what they have.
SEEDS_PER_STRATUM = 75

#: Reservoir-sampling seed, so the committed corpus is reproducible.
SAMPLE_SEED = 20260721

#: Citers below this citation count are dropped from the committed rows: no
#: plausible ``FLOOR`` admits a 0- or 1-citation citer as a landmark, so they can
#: never change a landmark *count*. The fit constrains ``FLOOR >= PRUNE_FLOOR`` to
#: keep that pruning exactly lossless. Undated citers are dropped too (no age →
#: the predicate can't place them) — both are still counted in ``total_citers``.
PRUNE_FLOOR = 2

#: The four worked examples carried through every landmark study, so an absurd
#: fitted count is caught by eye before an aggregate hides it. Resolved locally by
#: arXiv id (the common case) or DOI (Hawking's 1974 Nature letter predates arXiv).
WORKED_EXAMPLES = [
    ("Hawking Radiation", {"doi": "10.1038/248030a0"}),
    ("DQN", {"arxiv_id": "1312.5602"}),
    ("QMIX", {"arxiv_id": "1803.11485"}),
    ("Attention Is All You Need", {"arxiv_id": "1706.03762"}),
]

CORPUS_PATH = Path(__file__).with_name("corpus_s2.csv.gz")

#: One row per distinct ``(citer_year, citer_cited_by)`` within a seed. The seed
#: columns repeat across its citer rows — the file groups by ``corpus_id`` at fit
#: time. ``total_citers`` / ``dated_citers`` are the un-pruned denominators (they
#: include the citers dropped from these rows), so the fit knows each seed's full
#: size even though only landmark-eligible citers are stored.
FIELDS = [
    "corpus_id", "label", "is_worked_example",
    "seed_year", "seed_cited_by", "total_citers", "dated_citers",
    "citer_year", "citer_cited_by", "n",
]


class CorpusReader:
    """Read-only queries against the active ingested corpus, for this study.

    Mirrors the glob construction of ``corpus.source.DuckDBCitationSource`` and
    ``live_pool_validation.CorpusReader`` but asks its own question — a seed's
    *entire* citer citation-count distribution — so it holds its own connection
    rather than growing the app's serving seam with study-only methods.
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

    def sample_stratum(self, year_band: tuple[int, int], cite_band: tuple[int, int],
                       count: int, sample_seed: int) -> list[dict[str, Any]]:
        """Draw a uniform, reproducible seed sample from one (year × citation) stratum.

        Sampled by **hash order**, not DuckDB's ``USING SAMPLE``: the latter's
        reservoir terminates on the first row group of the ``corpusid``-clustered
        scan, so it draws only the lowest ids (measured: max id ~1.2M of 288M).
        Ordering the whole filtered pool by ``hash(corpusid, seed)`` and taking the
        top ``count`` is a full-scan pseudo-random draw that spans the pool and
        reproduces exactly for a fixed seed.

        Args:
            year_band: ``(from_year, to_year)`` inclusive-exclusive publication window.
            cite_band: ``(from_cites, to_cites)`` citation-count window.
            count: How many seeds to draw (a thin stratum yields fewer).
            sample_seed: The hash seed for this stratum — a different value reorders
                the pool, so distinct strata don't correlate.

        Returns:
            Up to ``count`` seed dicts with ``corpus_id`` / ``seed_year`` /
            ``seed_cited_by`` / ``label``.
        """
        from_year, to_year = year_band
        from_cites, to_cites = cite_band
        rows = self._connection.execute(
            f"""
            SELECT corpusid, year, citationcount, title
            FROM read_parquet('{self._papers_glob}')
            WHERE year >= ? AND year < ? AND citationcount >= ? AND citationcount < ?
            ORDER BY hash(corpusid, ?) LIMIT ?
            """,
            [from_year, to_year, from_cites, to_cites, sample_seed, count],
        ).fetchall()
        return [
            {"corpus_id": int(corpus_id), "seed_year": int(year),
             "seed_cited_by": int(citation_count), "label": title or "?"}
            for corpus_id, year, citation_count, title in rows
        ]

    def resolve_worked_example(self, ids: dict[str, str]) -> dict[str, Any] | None:
        """Resolve a worked-example seed to its corpus row, by arXiv id or DOI.

        Args:
            ids: ``{"arxiv_id": ...}`` or ``{"doi": ...}`` — the identifier the
                seed is known by.

        Returns:
            A seed dict (``corpus_id`` / ``seed_year`` / ``seed_cited_by``), or
            None when the corpus can't resolve it.
        """
        arxiv_id = ids.get("arxiv_id")
        corpus_id: int | None = None
        if arxiv_id:
            found = self._connection.execute(
                f"SELECT corpusid FROM read_parquet('{self._arxiv_index_glob}') "
                "WHERE arxiv_id = ? LIMIT 1",
                [arxiv_id],
            ).fetchone()
            corpus_id = int(found[0]) if found else None
        doi = ids.get("doi")
        if corpus_id is None and doi:
            found = self._connection.execute(
                f"SELECT corpusid FROM read_parquet('{self._papers_glob}') "
                "WHERE lower(doi) = ? LIMIT 1",
                [doi.lower()],
            ).fetchone()
            corpus_id = int(found[0]) if found else None
        if corpus_id is None:
            return None
        features = self._connection.execute(
            f"SELECT year, citationcount FROM read_parquet('{self._papers_glob}') "
            "WHERE corpusid = ? LIMIT 1",
            [corpus_id],
        ).fetchone()
        if not features or features[0] is None or features[1] is None:
            return None
        return {"corpus_id": corpus_id, "seed_year": int(features[0]),
                "seed_cited_by": int(features[1])}

    def citer_distribution(self, corpus_id: int) -> list[tuple[int | None, int, int]]:
        """A seed's citers as ``(citer_year, citer_cited_by, count)`` rows.

        Groups by the citing paper before the join — S2 ships every edge about
        twice across overlapping export batches (see the Upstream entry in
        ``docs/bugs.md``), so a raw count would be ~2×. Returns the **whole**
        distribution (every citation count, undated citers included); the caller
        prunes for the committed file and keeps the totals.

        Args:
            corpus_id: The seed's S2 ``corpusid`` (also picks the edge bucket).

        Returns:
            One ``(citer_year, citer_cited_by, count)`` per distinct pair; the year
            is None for undated citers.
        """
        bucket = corpus_id % NBUCKETS
        citations_glob = f"{self._citations_root}/bucket={bucket}/*.parquet"
        rows = self._connection.execute(
            f"""
            WITH edges AS (
                SELECT DISTINCT citingcorpusid
                FROM read_parquet('{citations_glob}', hive_partitioning=false)
                WHERE citedcorpusid = ?
            )
            SELECT p.year, p.citationcount, count(*) AS n
            FROM edges JOIN read_parquet('{self._papers_glob}') p
                ON p.corpusid = edges.citingcorpusid
            GROUP BY p.year, p.citationcount
            """,
            [corpus_id],
        ).fetchall()
        return [
            (int(year) if year is not None else None,
             int(citation_count) if citation_count is not None else 0,
             int(count))
            for year, citation_count, count in rows
        ]


def seed_rows(seed: dict[str, Any], distribution: list[tuple[int | None, int, int]],
              *, is_worked_example: int) -> list[dict[str, Any]]:
    """Turn one seed + its citer distribution into committed CSV rows.

    Computes the un-pruned denominators (``total_citers`` / ``dated_citers``),
    then keeps only dated citers at or above :data:`PRUNE_FLOOR` — the
    landmark-eligible ones — as the per-citer rows.

    Args:
        seed: The seed dict (``corpus_id`` / ``seed_year`` / ``seed_cited_by`` /
            ``label``).
        distribution: The seed's ``(citer_year, citer_cited_by, count)`` rows.
        is_worked_example: 1 for a worked-example seed, 0 otherwise.

    Returns:
        One row dict per kept ``(citer_year, citer_cited_by)`` pair; empty when the
        seed has no landmark-eligible citer (it contributes nothing to the fit).
    """
    total_citers = sum(count for _year, _cited_by, count in distribution)
    dated_citers = sum(count for year, _cited_by, count in distribution if year is not None)
    # The title is kept only for the worked examples (the eyeball set); repeating
    # a sampled seed's title across its hundreds of citer rows would bloat the
    # committed file for no fit value.
    label = seed.get("label", "?") if is_worked_example else ""
    rows: list[dict[str, Any]] = []
    for citer_year, citer_cited_by, count in distribution:
        if citer_year is None or citer_cited_by < PRUNE_FLOOR:
            continue
        rows.append({
            "corpus_id": seed["corpus_id"],
            "label": label,
            "is_worked_example": is_worked_example,
            "seed_year": seed["seed_year"],
            "seed_cited_by": seed["seed_cited_by"],
            "total_citers": total_citers,
            "dated_citers": dated_citers,
            "citer_year": citer_year,
            "citer_cited_by": citer_cited_by,
            "n": count,
        })
    return rows


def collect() -> list[dict[str, Any]]:
    """Collect the whole S2 fitting corpus (worked examples + all strata).

    Returns:
        One row dict per kept citer pair, in the :data:`FIELDS` schema.

    Raises:
        RuntimeError: When no ingested corpus release is active on this machine.
    """
    reader = CorpusReader()
    log.info("corpus release %s", reader.release_id)
    rows: list[dict[str, Any]] = []
    seen: set[int] = set()

    log.info("Worked examples:")
    for label, ids in WORKED_EXAMPLES:
        seed = reader.resolve_worked_example(ids)
        if seed is None:
            log.info("  %s (%s): unresolvable in the corpus — skipped", label, ids)
            continue
        seed["label"] = label
        distribution = reader.citer_distribution(seed["corpus_id"])
        example_rows = seed_rows(seed, distribution, is_worked_example=1)
        rows.extend(example_rows)
        seen.add(seed["corpus_id"])
        log.info("  %s (%d, %d cites): %d landmark-eligible citer bins",
                 label, seed["seed_year"], seed["seed_cited_by"], len(example_rows))

    strata = [(year_band, cite_band) for year_band in YEAR_BANDS for cite_band in CITATION_BANDS]
    for stratum_index, (year_band, cite_band) in enumerate(strata):
        # A distinct, deterministic reservoir seed per stratum so the strata
        # don't correlate (and the corpus reproduces — no process-randomized hash).
        stratum_seed = SAMPLE_SEED + stratum_index
        seeds = reader.sample_stratum(year_band, cite_band, SEEDS_PER_STRATUM, stratum_seed)
        kept = 0
        for seed in seeds:
            if seed["corpus_id"] in seen:
                continue
            seen.add(seed["corpus_id"])
            distribution = reader.citer_distribution(seed["corpus_id"])
            seed_citer_rows = seed_rows(seed, distribution, is_worked_example=0)
            if seed_citer_rows:
                rows.extend(seed_citer_rows)
                kept += 1
        log.info("Stratum year %s x cites %s: %d seeds sampled, %d with citers",
                 year_band, cite_band, len(seeds), kept)
    return rows


def open_corpus(path: Path, mode: str) -> TextIO:
    """Open a corpus CSV for reading or writing, gzipped when the path says so.

    The single place that knows the committed corpus is compressed, so the
    collector and the trainer can never disagree about it. **Always UTF-8**,
    explicitly: seed titles carry non-cp1252 characters (a Unicode hyphen once
    sank an hour-long run at the write step) and Windows defaults to cp1252.

    Args:
        path: The corpus path; a ``.gz`` suffix selects gzip, anything else is
            plain text (tests write plain temp files).
        mode: ``"r"`` or ``"w"`` — the text mode to open in.

    Returns:
        An open text handle, newline-normalized for :mod:`csv`.
    """
    if path.suffix == ".gz":
        return gzip.open(path, mode + "t", newline="", encoding="utf-8")
    return path.open(mode, newline="", encoding="utf-8")


def write_corpus(rows: list[dict[str, Any]], path: Path = CORPUS_PATH) -> None:
    """Write the collected rows to ``path`` as CSV in the :data:`FIELDS` schema.

    Args:
        rows: Corpus rows from :func:`collect`.
        path: Destination CSV path (gzipped when it ends ``.gz``).
    """
    with open_corpus(path, "w") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    seeds = len({row["corpus_id"] for row in rows})
    log.info("Wrote %d citer bins across %d seeds to %s", len(rows), seeds, path)


def main() -> None:
    """Collect the S2 fitting corpus and write ``corpus_s2.csv``."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    write_corpus(collect())


if __name__ == "__main__":
    main()
