"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
Query the offline corpus for a seed's citers — the real Field-Landmarks fix.

This is the payoff of the whole pipeline: because the corpus holds *every*
citation edge with the citers' own citation counts, a seed's landmark citers can
finally be returned **citation-sorted across all history** — the ranking S2's
live endpoint never offered (newest-first, and reachable only to the newest 9,000,
so a hyper-cited seed's most-cited citers were simply unreachable).

The seam is :class:`CitationSource`: two methods, ``landmark_citers`` and
``latest_bands``, over an S2 ``corpusid``. The concrete
:class:`DuckDBCitationSource` runs them as DuckDB SQL over the local Parquet; the
long-term Athena-over-S3 implementation is the same SQL against the same schema,
so it drops in behind this Protocol untouched.

``citation_relations`` is the module-level entry point ``build.py`` calls — a
drop-in for the live ``s2.citation_relations`` that returns the same
``(landmark, latest)`` shape, or **None** when the corpus can't serve this seed
(unconfigured, no ingested release, or an unresolvable seed) so the caller falls
back to the live path.

**Since v5.11.0 this path is shaped like the OpenAlex one, not the live one** — a
citation-ranked landmark prefix up to ``landmark_max_year``, then per-year Latest
bands whose start the fitted tau rule places against those landmarks. It used to
mirror the live fallback's rolling 12-month window, on the reasoning that the s2
provider's split should mean the same thing whichever source answered. That
symmetry was the wrong one to keep: the live path is a **recency sliver** and bands
its landmarks because it has no all-history ranking to prefix; the corpus and
OpenAlex both hold whole histories and can place an honest frontier. Two of three
paths now agree, and the odd one out is the one that structurally cannot join them
(a truncated-pool validation study measured why: banded landmarks
flatten the year distribution the tau rule reads, pinning 56 of 58 seeds to a
one-year band). So switching a graph to the corpus changes *which* citers appear —
now the true top-cited across all history — and now also *where the frontier
starts*: per-seed, rather than a flat twelve months.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Sequence
from typing import Callable, Protocol

import duckdb

from ...caps import LATEST_NODES_PER_BAND, LATEST_NUMBER_OF_BANDS, UNBOUNDED_LANDMARK_CAP
from . import paths as corpus_paths
from .ingest import NBUCKETS
from .paths import ReleasePaths, read_current_release

log = logging.getLogger(__name__)

#: Injected landmark budget: ``(ranked citer years) -> how many to ship | None``.
#: ``services/graph`` passes ``budget.computed_cite_limit``, which runs the STOP
#: rule over the real pool; None falls back to the flat payload guard. It
#: takes years and returns a count because the rule only reasons about *when*
#: citers were published — the entries themselves stay here. A parameter, not an
#: import, so ``integrations`` stays below ``services`` in the dependency order —
#: the same shape as the live path's ``LandmarkSelectFn`` and OpenAlex's
#: ``BandStartFn``.
#:
#: A **count**, not a selection: this pool is a whole-history ranking, so the band
#: is its prefix — the giants. (The live path's truncated pool has no such ranking
#: to prefix, which is why it gets a selector instead. See
#: ``budget.computed_cite_limit``.)
LandmarkBudgetFn = Callable[[Sequence[int | None]], int | None]

#: Injected boundary chooser: ``(landmark_years, landmark_max_year) -> first band
#: year | None``. ``services/graph`` passes ``bands.earliest_band_year``; None keeps
#: the fixed ``number_of_bands`` span. Identical to OpenAlex's ``BandStartFn`` —
#: the same rule, reading the same kind of distribution, because this path now ships
#: the same kind of landmark band.
BandStartFn = Callable[[list[int], int], int | None]


class CitationSource(Protocol):
    """A source of a seed's citers, ranked — the interface ``build.py`` targets.

    Deliberately tiny and ``corpusid``-keyed: the offline DuckDB corpus and the
    future Athena-over-S3 corpus both implement exactly this, so the app never
    learns which one it's talking to. Seed resolution (arXiv id → corpus id) is a
    separate concern the concrete class also handles (see
    :meth:`DuckDBCitationSource.resolve_corpus_id`).
    """

    def landmark_citers(self, corpus_id: int, *,
                        max_landmark_year: int,
                        landmark_budget: LandmarkBudgetFn | None = None) -> list[dict]:
        """The seed's landmark-era citers, most-cited first (its Field Landmarks)."""
        ...

    def latest_bands(self, corpus_id: int, *, band_start: int, current_year: int,
                     per_year: int) -> list[dict]:
        """The seed's recent citers as per-year bands, newest-first."""
        ...


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
    """Turn one citer row (hydrated paper + edge flag) into a ``{"node", "influential"}`` entry.

    Since the two-phase split the row is assembled in Python (``_entries_for``):
    the paper columns come from the hydration query, the trailing
    ``isinfluential`` from the ranking phase's edge.

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


#: The wide display columns the **hydration phase** selects from ``papers`` —
#: everything :func:`_row_to_entry` unpacks except the edge's ``isinfluential``,
#: which rides in from the ranking phase and is appended in Python. Kept out of
#: the ranking deliberately: projecting these for all ~30k citers of a busy seed
#: is what used to cost 39s (``authors``, a JSON blob per paper, was +18.6s by
#: itself); hydrating them for only the ~63 winners against the clustered
#: ``papers`` is ~1s.
_HYDRATE_SELECT = (
    "corpusid, arxiv_id, doi, title, year, publicationdate, citationcount, authors"
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

    def _deduped_edges(self, corpus_id: int) -> str:
        """The SQL for a seed's distinct citing papers — the shared subquery.

        **The edge list arrives with duplicates, and they're upstream's, not
        ours.** S2 ships a release's ``citations`` dataset as more than one export
        batch, and the batches *overlap*: the 2026-07-07 release advertises 390
        shards — 240 stamped ``…_00151_3g69z_…`` and 150 stamped
        ``…_00016_bxc9g_…`` — carrying ~5.1B rows for ~2.7B distinct edges. Every
        edge lands about twice. So this **groups by the citing paper** before the
        join. Without it a ``limit`` counts *rows*, not papers, and silently halves
        the relation: DQN's landmark budget of 63 bought ~32 actual landmarks.
        (``build.py``'s ``add_edge`` dedupes endpoints, so the graph stayed
        *correct* — just half-empty, which is why this hid for so long.)

        Deduping here rather than at ingest is deliberate: a duplicate pair spans
        **two different shards**, so a per-shard ``SELECT DISTINCT`` would never
        see both copies. The grouping is bucket-local and runs on a few thousand
        rows, so it costs nothing measurable — the whole bucket scan is ~0.07s
        (measured 2026-07-17; what a citer query used to pay for was projecting
        the wide display columns through the join against an *unsorted* 200M-row
        papers table — fixed by clustering ``papers`` at ingest and fetching
        two-phase, see :meth:`landmark_citers`).

        ``isinfluential`` is OR'd across the copies: the flag is a claim that *some*
        edge record marks this citation influential, and the batches needn't agree.

        Args:
            corpus_id: The seed's ``corpusid``, which also picks the bucket.

        Returns:
            A parenthesised SQL subquery aliasable as ``c``, taking ``corpus_id``
            as its single bind parameter.
        """
        bucket = corpus_id % NBUCKETS
        citations_glob = f"{self._citations_root}/bucket={bucket}/*.parquet"
        return (
            "(SELECT citingcorpusid, bool_or(isinfluential) AS isinfluential "
            f"FROM read_parquet('{citations_glob}', hive_partitioning=false) "
            "WHERE citedcorpusid = ? GROUP BY citingcorpusid)"
        )

    def _run(self, query: str, params: list) -> list[tuple]:
        """Execute one citer query, treating an absent bucket as "no citers".

        Args:
            query: The SQL to run.
            params: Its bind parameters.

        Returns:
            The result rows, or ``[]`` when this seed's bucket holds no Parquet
            (a partial or sample ingest with no edges for it — not an error).
        """
        with self._lock:
            try:
                return self._connection.execute(query, params).fetchall()
            except duckdb.IOException:
                return []

    def _ranked_landmark_citers(self, corpus_id: int, limit: int | None, *,
                                max_landmark_year: int) -> list[tuple]:
        """The ranking phase: landmark-era citer ids, most-cited first, **narrow**.

        Projects only ``(corpusid, year, isinfluential)`` — the id to hydrate
        later, the year the budget rule reads, and the edge flag that has no
        paper row to come from. The ranking genuinely has to touch every citer
        of the seed, so what it *projects* is the whole cost: the narrow form is
        ~1s where ranking on the display columns was 20–39s.

        Args:
            corpus_id: The seed's ``corpusid``.
            limit: Max citers to rank, or None for all.
            max_landmark_year: The last landmark-era year (inclusive).

        Returns:
            ``(citing corpusid, year, isinfluential)`` rows, most-cited first.
        """
        query = (
            "SELECT p.corpusid, p.year, c.isinfluential "
            f"FROM {self._deduped_edges(corpus_id)} c "
            f"JOIN read_parquet('{self._papers_glob}') p ON p.corpusid = c.citingcorpusid "
            "WHERE (p.year IS NULL OR p.year <= ?) "
            "ORDER BY p.citationcount DESC NULLS LAST "
            + (f"LIMIT {int(limit)}" if limit is not None else "")
        )
        return self._run(query, [corpus_id, max_landmark_year])

    def _hydrate_citers(self, corpus_ids: Sequence[int]) -> dict[int, tuple]:
        """The hydration phase: the wide display columns for the chosen citers.

        Runs *after* the budget has trimmed the ranking, so it fetches tens of
        rows, not tens of thousands. Cheap only because ingest clusters
        ``papers`` by ``corpusid``: each row group owns a contiguous id slice,
        so the ``IN`` filter prunes on zone maps and reads a handful of row
        groups. (On the old arrival-ordered layout this exact lookup cost the
        same as fetching every citer — 33s for 63 ids — because every row group
        spanned the whole id range and nothing pruned.)

        Args:
            corpus_ids: The winners' ``corpusid``s, any order.

        Returns:
            ``corpusid → (corpusid, arxiv_id, doi, title, year, publicationdate,
            citationcount, authors)`` for every id found.
        """
        if not corpus_ids:
            return {}
        placeholders = ", ".join("?" for _ in corpus_ids)
        query = (
            f"SELECT {_HYDRATE_SELECT} FROM read_parquet('{self._papers_glob}') "
            f"WHERE corpusid IN ({placeholders})"
        )
        return {int(row[0]): row for row in self._run(query, list(corpus_ids))}

    def _entries_for(self, ranked: list[tuple[int, bool]]) -> list[dict]:
        """Hydrate ranked ``(corpusid, isinfluential)`` winners into entries.

        Args:
            ranked: The winners in presentation order, each with its edge flag.

        Returns:
            ``{"node", "influential"}`` entries in the same order. A winner
            missing from ``papers`` is skipped — it can't happen for ids that
            came out of the ranking join, which is the only caller.
        """
        hydrated = self._hydrate_citers([citer_id for citer_id, _influential in ranked])
        entries = []
        for citer_id, influential in ranked:
            paper_row = hydrated.get(int(citer_id))
            if paper_row is not None:
                entries.append(_row_to_entry((*paper_row, influential)))
        return entries

    def landmark_citers(self, corpus_id: int, *,
                        max_landmark_year: int,
                        landmark_budget: LandmarkBudgetFn | None = None) -> list[dict]:
        """The seed's landmark-era citers, most-cited first (its Field Landmarks).

        Everything published up to ``max_landmark_year``, ranked by the citers' own
        citation counts — the all-history ranking that is the whole point of the
        corpus, and the one S2's live endpoint can't serve.

        **Two phases** (see :meth:`_ranked_landmark_citers` and
        :meth:`_hydrate_citers`): rank every citer narrow, trim to the budget,
        hydrate only the winners wide. With a ``landmark_budget`` the ranking
        runs unlimited and the rule measures the full pool's years *before*
        hydration — so the rule still sees everything, but the display columns
        are fetched for the ~63 winners alone, never the ~30k pool.

        An **undated** citer competes here rather than in ``latest``: it can't be
        placed in a band, and dropping it entirely would lose a genuine giant to a
        missing field. (It can't *win* a landmark slot either — the budget rule
        drops undated citers when it counts. See ``budget.py``.)

        Args:
            corpus_id: The seed's ``corpusid``.
            max_landmark_year: The last year that still counts as landmark-era;
                anything newer belongs to the Latest bands.
            landmark_budget: Optional rule measuring how many of the ranked pool
                to ship, from its citer years (see :data:`LandmarkBudgetFn`).
                Its count wins over the ``UNBOUNDED_LANDMARK_CAP`` payload
                guard; a None answer (or no rule) falls back to it.

        Returns:
            ``{"node", "influential"}`` entries, most-cited first.
        """
        if landmark_budget is None:
            ranked = self._ranked_landmark_citers(corpus_id, UNBOUNDED_LANDMARK_CAP,
                                                  max_landmark_year=max_landmark_year)
        else:
            ranked = self._ranked_landmark_citers(corpus_id, None,
                                                  max_landmark_year=max_landmark_year)
            budget = landmark_budget([year for _citer_id, year, _influential in ranked])
            # A declining rule (None) falls back to the flat payload guard.
            ranked = ranked[:budget] if budget is not None else ranked[:UNBOUNDED_LANDMARK_CAP]
        return self._entries_for(
            [(citer_id, influential) for citer_id, _year, influential in ranked]
        )

    def latest_bands(self, corpus_id: int, *, band_start: int, current_year: int,
                     per_year: int) -> list[dict]:
        """The seed's recent citers as **per-year bands**, newest-first.

        One band per calendar year from ``band_start`` to ``current_year``, each
        holding that year's top ``per_year`` citers by citation count — so no single
        busy year drowns the frontier, and every recent year gets its own fair
        slice. The same shape ``openalex.citation_relations`` builds, except it
        needs one HTTP call per year and this needs **one query**: a window function
        ranks within each year in a single pass. Two-phase like the landmarks —
        the window function ranks narrow, then only the per-year winners are
        hydrated wide and sorted by date in Python (the same
        ``publicationdate DESC NULLS LAST`` order the one-phase query produced).

        Args:
            corpus_id: The seed's ``corpusid``.
            band_start: First year to band (from ``bands.earliest_band_year``).
            current_year: Last year to band, inclusive.
            per_year: Max citers per year band.

        Returns:
            ``{"node", "influential"}`` entries, newest-first — the caller excludes
            anything already shipped as a landmark, then reverses for the reveal
            order.
        """
        query = (
            "SELECT corpusid, isinfluential FROM ("
            "  SELECT p.corpusid AS corpusid, c.isinfluential AS isinfluential, "
            "  ROW_NUMBER() OVER ("
            "     PARTITION BY p.year ORDER BY p.citationcount DESC NULLS LAST"
            "  ) AS rank_in_year "
            f"  FROM {self._deduped_edges(corpus_id)} c "
            f"  JOIN read_parquet('{self._papers_glob}') p "
            "     ON p.corpusid = c.citingcorpusid "
            "  WHERE p.year >= ? AND p.year <= ?"
            ") WHERE rank_in_year <= ?"
        )
        winners = self._run(query, [corpus_id, band_start, current_year, per_year])
        entries = self._entries_for(
            [(citer_id, influential) for citer_id, influential in winners]
        )
        # None → "" sorts after every real date under reverse=True, matching the
        # SQL's NULLS LAST.
        entries.sort(key=lambda entry: entry["node"]["pub_date"] or "", reverse=True)
        return entries


def active_source() -> DuckDBCitationSource | None:
    """The corpus source for the active release, or None when unavailable.

    Reads ``storage.s2_corpus`` — ``CURRENT`` lives there beside the
    data it names, so serving needs nothing from the raw root (that drive can be
    absent, or its shards deleted after ingest).

    Returns None (so callers fall back to the live S2 path) whenever the corpus
    isn't ready: no parquet root configured, no ``CURRENT`` release marked, or its
    papers Parquet is missing. A fresh source per call keeps it honest when config
    is repointed (the tests do this) — construction is cheap.

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
    if not paths.parquet_dataset("papers").exists():
        return None
    return DuckDBCitationSource(paths)


def citation_relations(
    seed_paper: dict,
    seed_ref: str,
    *,
    max_landmark_year: int,
    current_year: int,
    landmark_budget: LandmarkBudgetFn | None = None,
    band_start: BandStartFn | None = None,
    number_of_bands: int | None = None,
    nodes_per_band: int | None = None,
) -> tuple[list[dict], list[dict]] | None:
    """Split a seed's corpus citers into (landmarks, latest) — or None to fall back.

    A drop-in for the live ``s2.citation_relations`` used by ``build.py`` when the
    offline corpus is available and can resolve the seed. Returns the same
    ``(landmark_entries, latest_entries)`` shape; returns **None** when the corpus
    is unavailable or can't resolve this seed, signalling the caller to use the
    live path.

    Since **v5.11.0 this path is shaped like the OpenAlex one**, which it always
    should have been: it is the only other provider holding a seed's whole citation
    history, and the only one besides OpenAlex that can honestly place a frontier.

    * **Landmarks** — the all-time giants up to ``max_landmark_year``, a
      citation-ranked **prefix** whose length is *computed* rather than predicted.
      With a ``landmark_budget`` rule the ranking runs unlimited and the rule
      measures the real pool; the trained ``cite_budget`` model isn't consulted.
      The unlimited rank is cheap because the query is **two-phase** (see
      :meth:`DuckDBCitationSource.landmark_citers`): the full pool is ranked on
      narrow columns, and the wide display columns are hydrated only for the
      winners the rule keeps.
    * **Latest** — **per-year bands** from ``band_start`` to ``current_year``,
      replacing the flat rolling window this path inherited from the live fallback.
      The band start comes from the fitted tau rule reading the *shipped landmarks'*
      year distribution, so an old seed's frontier widens back to meet its cluster
      instead of stranding a decade of empty timeline.

    **Why the tau rule works here and not on the live path** — it needs a real
    distribution to read, and it gets one precisely *because* landmarks are a
    prefix. The live fallback bands its landmarks (a truncated pool has no
    all-history ranking to prefix), which flattens every year to the cap, which
    collapses tau's ``tau × peak`` threshold and pins the boundary to the newest
    year on 56 of 58 seeds — measured across a 58-seed validation corpus, whose
    verdict this argument carries.

    Args:
        seed_paper: The normalized seed node (its ``arxiv_id`` drives resolution).
        seed_ref: The raw reference the graph was seeded on (a ``CorpusId:`` /
            arXiv id fallback for resolution).
        max_landmark_year: The last landmark-era year — anything newer is banded as
            latest. Passed in rather than computed so both providers split on the
            same boundary (``openalex.landmark_max_year``).
        current_year: The last year to band, inclusive.
        landmark_budget: Optional rule measuring how many of the *ranked* landmark
            pool to ship, from its citer years (see :data:`LandmarkBudgetFn`). Its
            count wins over the payload guard, and its presence makes the query
            unlimited.
        band_start: Optional per-seed band-start chooser (see :data:`BandStartFn`).
            None, or a None answer, keeps the fixed ``number_of_bands`` span.
        number_of_bands: That fixed span's length, in one-year bands below the
            landmark cutoff. None (the default) reads the shared
            :data:`~atlas.integrations.caps.LATEST_NUMBER_OF_BANDS` at call
            time; the settings modal's non-adaptive mode passes a number to
            override it per request.
        nodes_per_band: The top-N most-cited citers each one-year band keeps.
            None (the default) likewise reads the shared
            :data:`~atlas.integrations.caps.LATEST_NODES_PER_BAND`.

    Returns:
        ``(landmark_entries, latest_entries)``, or None to fall back to live S2.
    """
    source = active_source()
    if source is None:
        return None
    corpus_id = source.resolve_corpus_id(seed_paper.get("arxiv_id"), seed_ref)
    if corpus_id is None:
        return None

    # FIELD LANDMARKS. The budget rule travels into the source so the trim can
    # happen between its two phases: the rule measures the full *ranked* pool's
    # years, and only the winners it keeps are hydrated wide.
    landmark = source.landmark_citers(corpus_id,
                                      max_landmark_year=max_landmark_year,
                                      landmark_budget=landmark_budget)

    # LATEST PUBLICATIONS: per-year bands. The start defaults to the fixed span and
    # may widen per seed, read off the landmarks we just chose — which is why this
    # runs second.
    # Resolved here, not in the signature's default, so the module constants stay
    # the live source of truth (a default would freeze their import-time values).
    band_span = LATEST_NUMBER_OF_BANDS if number_of_bands is None else number_of_bands
    per_year = LATEST_NODES_PER_BAND if nodes_per_band is None else nodes_per_band

    earliest = max_landmark_year - band_span + 1
    if band_start is not None:
        adaptive = band_start(
            [year for year in (entry["node"].get("year") for entry in landmark) if year],
            max_landmark_year,
        )
        if adaptive is not None:
            earliest = adaptive
    recent = source.latest_bands(corpus_id, band_start=earliest,
                                 current_year=current_year,
                                 per_year=per_year)

    # The bands reach below max_landmark_year, so a giant can appear in both —
    # keep it a landmark rather than double-showing it (as the OpenAlex path does).
    shipped = {entry["node"]["id"] for entry in landmark}
    latest = [entry for entry in recent if entry["node"]["id"] not in shipped]
    # Newest-first already (the query orders by date); flip so rank 0 is the
    # OLDEST banded year and the reveal slider walks forward through time
    # toward the present.
    latest.reverse()
    return landmark, latest
