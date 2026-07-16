"""Query the offline corpus for a seed's citers — the real Field-Landmarks fix.

This is the payoff of the whole pipeline: because the corpus holds *every*
citation edge with the citers' own citation counts, a seed's landmark citers can
finally be returned **citation-sorted across all history** — the ranking S2's
live endpoint never offered (newest-first, capped at a ~10k offset, so a
hyper-cited seed's most-cited citers were simply unreachable).

The seam is :class:`CitationSource`: two methods, ``landmark_citers`` and
``latest_citers``, over an S2 ``corpusid``. The concrete
:class:`DuckDBCitationSource` runs them as DuckDB SQL over the local Parquet; the
long-term Athena-over-S3 implementation is the same SQL against the same schema,
so it drops in behind this Protocol untouched.

``citation_relations`` is the module-level entry point ``build.py`` calls — a
drop-in for the live ``s2.citation_relations`` that returns the same
``(landmark, latest)`` shape, or **None** when the corpus can't serve this seed
(unconfigured, no ingested release, or an unresolvable seed) so the caller falls
back to the live path. The landmark/latest split mirrors the live path's rolling
12-month window, so switching a graph to the corpus changes *which* citers appear
(now the true top-cited), not the relations' meaning.
"""

from __future__ import annotations

import datetime
import json
import logging
import threading
from typing import Protocol

import duckdb

from . import paths as corpus_paths
from .ingest import NBUCKETS
from .paths import ReleasePaths, read_current_release

log = logging.getLogger(__name__)

#: The recent-frontier window, in months — a citer published within this many
#: months of today is ``latest`` (its own relation), everything older competes as
#: a historic ``landmark``. Mirrors ``traversal._LATEST_WINDOW_MONTHS`` so the s2
#: provider's split means the same thing whether it's served live or from the
#: corpus; kept a local constant rather than importing a private name.
_LATEST_WINDOW_MONTHS = 12


class CitationSource(Protocol):
    """A source of a seed's citers, ranked — the interface ``build.py`` targets.

    Deliberately tiny and ``corpusid``-keyed: the offline DuckDB corpus and the
    future Athena-over-S3 corpus both implement exactly this, so the app never
    learns which one it's talking to. Seed resolution (arXiv id → corpus id) is a
    separate concern the concrete class also handles (see
    :meth:`DuckDBCitationSource.resolve_corpus_id`).
    """

    def landmark_citers(self, corpus_id: int, limit: int | None) -> list[dict]:
        """The seed's historic citers, most-cited first (its Field Landmarks)."""
        ...

    def latest_citers(self, corpus_id: int, limit: int | None) -> list[dict]:
        """The seed's recent-frontier citers, oldest-first within the window."""
        ...


def _latest_cutoff() -> str:
    """Today minus :data:`_LATEST_WINDOW_MONTHS`, as an ISO ``YYYY-MM-DD`` string.

    A string bound because S2 publication dates are ``YYYY-MM-DD`` text compared
    lexicographically (ISO text sorts chronologically), which also sidesteps
    month-arithmetic edge cases. Mirrors ``traversal._latest_cutoff``.

    Returns:
        The cutoff date as ``YYYY-MM-DD``.
    """
    today = datetime.date.today()
    months = today.year * 12 + (today.month - 1) - _LATEST_WINDOW_MONTHS
    return f"{months // 12:04d}-{months % 12 + 1:02d}-{today.day:02d}"


def _format_authors(authors_json: str | None) -> str | None:
    """Join a papers-dataset ``authors`` JSON array into a display string.

    Done lazily here (only for the handful of citers actually shown) rather than
    during ingest over all 200M papers.

    Args:
        authors_json: The raw ``authors`` value from the Parquet — a JSON array
            of ``{"authorId", "name"}`` objects, or None.

    Returns:
        ``"Name One, Name Two"``, or None when there are no named authors.
    """
    if not authors_json:
        return None
    try:
        authors = json.loads(authors_json)
    except (json.JSONDecodeError, TypeError):
        return None
    names = [entry.get("name", "") for entry in authors if isinstance(entry, dict) and entry.get("name")]
    return ", ".join(names) or None


def _month_of(pub_date: str | None) -> int | None:
    """The 1–12 month parsed from a ``YYYY-MM-DD`` publication date, or None.

    Mirrors ``nodes.node``'s month parsing so timeline placement is identical
    whether a node came from the live API or the corpus.
    """
    if isinstance(pub_date, str) and len(pub_date) >= 7:
        try:
            month = int(pub_date[5:7])
        except ValueError:
            return None
        return month if 1 <= month <= 12 else None
    return None


def _row_to_entry(row: tuple) -> dict:
    """Turn one query row into a ``{"node", "influential"}`` entry.

    The node dict matches ``semantic_scholar.nodes.node()`` exactly (the
    ``Graph`` model forbids extra keys), so a corpus citer is indistinguishable
    from a live-API one downstream. A corpus citer has no abstract/tldr/fields
    (those live in other datasets, hydrated lazily when the node is opened), so
    they're None/empty here.

    Args:
        row: ``(corpusid, arxiv_id, doi, title, year, publicationdate,
            citationcount, authors_json, isinfluential)``.

    Returns:
        A ``{"node": <node dict>, "influential": bool}`` entry.
    """
    (corpus_id, arxiv_id, _doi, title, year, pub_date, citation_count, authors_json, influential) = row
    url = (
        f"https://arxiv.org/abs/{arxiv_id}"
        if arxiv_id
        else f"https://www.semanticscholar.org/paper/CorpusID:{corpus_id}"
    )
    node = {
        "id": f"CorpusId:{corpus_id}",
        "arxiv_id": arxiv_id,
        "title": title or "(untitled)",
        "abstract": None,
        "tldr": None,
        "year": year,
        "month": _month_of(pub_date),
        "pub_date": pub_date if isinstance(pub_date, str) and pub_date else None,
        "citation_count": citation_count,
        "authors": _format_authors(authors_json),
        "url": url,
        "fields_of_study": [],
    }
    return {"node": node, "influential": bool(influential)}


#: The citer columns every query selects, in the order :func:`_row_to_entry`
#: unpacks — the join of a citer's edge (``isinfluential``) to its paper row.
_CITER_SELECT = (
    "p.corpusid, p.arxiv_id, p.doi, p.title, p.year, p.publicationdate, "
    "p.citationcount, p.authors, c.isinfluential"
)


class DuckDBCitationSource:
    """A :class:`CitationSource` backed by the local DuckDB-over-Parquet corpus.

    Holds one read-only connection guarded by a lock (DuckDB connections aren't
    safe for concurrent queries, and Flask serves graph builds on threads). The
    Parquet globs are resolved from the active release's paths once, at
    construction.
    """

    def __init__(self, paths: ReleasePaths):
        """Open the corpus for one ingested release.

        Args:
            paths: The active release's paths — its ``parquet/`` tree is queried.
        """
        self._paths = paths
        self._papers_glob = (paths.parquet_dataset("papers") / "*.parquet").as_posix()
        self._citations_root = paths.parquet_dataset("citations").as_posix()
        self._arxiv_index_glob = (paths.parquet / "arxiv_index" / "*.parquet").as_posix()
        self._lock = threading.Lock()
        self._connection = duckdb.connect(":memory:")

    def resolve_corpus_id(self, arxiv_id: str | None, seed_ref: str) -> int | None:
        """Resolve a seed to its S2 ``corpusid``, or None when unresolvable.

        Tries the arXiv index first (the common case — a seed is nearly always an
        arXiv paper), then a ``CorpusId:<n>`` / bare-integer ``seed_ref`` (a
        re-seed on a corpus node). A raw S2 paperId hash can't be resolved here
        (it isn't in the corpus), so those fall back to the live path.

        Args:
            arxiv_id: The seed's arXiv id, if it has one.
            seed_ref: The raw reference the graph was seeded on.

        Returns:
            The seed's ``corpusid``, or None when it can't be resolved locally.
        """
        if arxiv_id:
            with self._lock:
                found = self._connection.execute(
                    f"SELECT corpusid FROM read_parquet('{self._arxiv_index_glob}') "
                    "WHERE arxiv_id = ? LIMIT 1",
                    [arxiv_id],
                ).fetchone()
            if found:
                return int(found[0])
        ref = seed_ref.strip()
        prefix = "corpusid:"
        if ref.lower().startswith(prefix):
            ref = ref[len(prefix) :]
        if ref.isdigit():
            return int(ref)
        return None

    def _citers(self, corpus_id: int, *, recent: bool, limit: int | None) -> list[dict]:
        """Query one side of the citer split (landmark or latest), deduped.

        **The edge list arrives with duplicates, and they're upstream's, not
        ours.** S2 ships a release's ``citations`` dataset as more than one export
        batch, and the batches *overlap*: the 2026-07-07 release advertises 390
        shards — 240 stamped ``…_00151_3g69z_…`` and 150 stamped
        ``…_00016_bxc9g_…`` — carrying ~5.1B rows for ~2.7B distinct edges. Every
        edge lands about twice. So this **groups by the citing paper** before
        joining. Without it a ``limit`` counts *rows*, not papers, and silently
        halves the relation: DQN's landmark budget of 63 bought ~32 actual
        landmarks. (``build.py``'s ``add_edge`` dedupes endpoints, so the graph
        stayed *correct* — just half-empty, which is why this hid for so long.)

        Deduping here rather than at ingest is deliberate: a duplicate pair spans
        **two different shards**, so a per-shard ``SELECT DISTINCT`` would never
        see both copies. The grouping is bucket-local and runs on a few thousand
        rows, so it costs nothing measurable.

        ``isinfluential`` is OR'd across the copies: the flag is a claim that *some*
        edge record marks this citation influential, and the batches needn't agree.

        Args:
            corpus_id: The seed's ``corpusid``.
            recent: True for the latest window (``publicationdate >= cutoff``,
                oldest-first), False for historic landmarks (older, most-cited
                first).
            limit: Max citers to return, or None for all. Counts distinct citing
                papers.

        Returns:
            ``{"node", "influential"}`` entries in the relation's reveal order,
            one per citing paper.
        """
        bucket = corpus_id % NBUCKETS
        citations_glob = f"{self._citations_root}/bucket={bucket}/*.parquet"
        cutoff = _latest_cutoff()
        if recent:
            date_clause = "p.publicationdate >= ?"
            # Newest-first for the LIMIT (keep the most recent), reversed to
            # oldest-first below so the reveal slider walks toward the present.
            order = "p.publicationdate DESC"
        else:
            # A citer with no date can't be placed in the window, so it competes
            # as a historic landmark (matches the live path's _is_latest).
            date_clause = "(p.publicationdate IS NULL OR p.publicationdate < ?)"
            order = "p.citationcount DESC NULLS LAST"
        limit_clause = f"LIMIT {int(limit)}" if limit is not None else ""
        # One row per citing paper, BEFORE the join and the limit — see above.
        deduped_edges = (
            "(SELECT citingcorpusid, bool_or(isinfluential) AS isinfluential "
            f"FROM read_parquet('{citations_glob}', hive_partitioning=false) "
            "WHERE citedcorpusid = ? GROUP BY citingcorpusid)"
        )
        query = (
            f"SELECT {_CITER_SELECT} "
            f"FROM {deduped_edges} c "
            f"JOIN read_parquet('{self._papers_glob}') p ON p.corpusid = c.citingcorpusid "
            f"WHERE {date_clause} "
            f"ORDER BY {order} {limit_clause}"
        )
        with self._lock:
            try:
                rows = self._connection.execute(query, [corpus_id, cutoff]).fetchall()
            except duckdb.IOException:
                # No parquet in this bucket dir (e.g. a partial/sample ingest with
                # no edges for this seed) — treat as no citers, not an error.
                return []
        entries = [_row_to_entry(row) for row in rows]
        if recent:
            entries.reverse()  # newest-first LIMIT -> oldest-first reveal
        return entries

    def landmark_citers(self, corpus_id: int, limit: int | None) -> list[dict]:
        """The seed's historic citers, most-cited first (its Field Landmarks)."""
        return self._citers(corpus_id, recent=False, limit=limit)

    def latest_citers(self, corpus_id: int, limit: int | None) -> list[dict]:
        """The seed's recent-frontier citers, oldest-first within the window."""
        return self._citers(corpus_id, recent=True, limit=limit)


def active_source() -> DuckDBCitationSource | None:
    """The corpus source for the active release, or None when unavailable.

    Returns None (so callers fall back to the live S2 path) whenever the corpus
    isn't ready: no ``s2_corpus_dir`` configured, no ``CURRENT`` release marked,
    or its papers Parquet is missing. A fresh source per call keeps it honest
    when config is repointed (the tests do this) — construction is cheap.

    Returns:
        A ready :class:`DuckDBCitationSource`, or None.
    """
    root = corpus_paths.corpus_root()
    if root is None or not root.exists():
        return None
    release_id = read_current_release(root)
    if not release_id:
        return None
    paths = corpus_paths.release_paths(release_id)
    if paths is None or not paths.parquet_dataset("papers").exists():
        return None
    return DuckDBCitationSource(paths)


def citation_relations(
    seed_paper: dict,
    seed_ref: str,
    *,
    landmark_limit: int | None,
    latest_limit: int | None,
) -> tuple[list[dict], list[dict]] | None:
    """Split a seed's corpus citers into (landmarks, latest) — or None to fall back.

    A drop-in for the live ``s2.citation_relations`` used by ``build.py`` when the
    offline corpus is available and can resolve the seed. Returns the same
    ``(landmark_entries, latest_entries)`` shape; returns **None** when the corpus
    is unavailable or can't resolve this seed, signalling the caller to use the
    live path.

    Args:
        seed_paper: The normalized seed node (its ``arxiv_id`` drives resolution).
        seed_ref: The raw reference the graph was seeded on (a ``CorpusId:`` /
            arXiv id fallback for resolution).
        landmark_limit: Max historic landmark citers, or None for all.
        latest_limit: Max recent-frontier citers, or None for all.

    Returns:
        ``(landmark_entries, latest_entries)``, or None to fall back to live S2.
    """
    source = active_source()
    if source is None:
        return None
    corpus_id = source.resolve_corpus_id(seed_paper.get("arxiv_id"), seed_ref)
    if corpus_id is None:
        return None
    landmark = source.landmark_citers(corpus_id, landmark_limit)
    latest = source.latest_citers(corpus_id, latest_limit)
    return landmark, latest
