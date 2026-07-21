"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
Assemble a paper's neighborhood graph from a single, user-chosen provider.

Given a seed paper, build a Connected-Papers-style graph: the seed plus its
references (papers it cites — its intellectual ancestors) and its citations
(papers that cite it — its descendants, split into all-time landmark citers and
the recent-years frontier). Every relation is drawn from **one** academic-data
provider, chosen per graph:

* **Semantic Scholar** (``provider="s2"``) — seed, references, and citations all
  via S2. Its live citation endpoint is newest-first with no citation sort, so
  landmark citers are recency-biased for a heavily-cited seed (the interim cost,
  lifted later by the offline S2 citations corpus).
* **OpenAlex** (``provider="openalex"``) — seed, references, and citations all
  via OpenAlex, whose server-sorted ``cites:`` / ``cited_by:`` queries return the
  most-cited citers and references directly. The tradeoff is seed resolution: a
  famous published paper resolves to its lower-cited arXiv-preprint record.

This replaced the v4.x **hybrid** (S2 seed/references/similar + OpenAlex
citations, merged with a ``max`` count and cross-source id dedup). A single
provider per graph means one citation-count scale (node sizes are finally
comparable across relations) and no cross-source identity glue. The *Similar*
relation is retired from the graph build entirely (the recommendations client
lives on for the researcher's ``expand_node``). Node identity still dedups
within a provider — a paper reached through two relations, or an OpenAlex
duplicate work, merges into one node via its arXiv id.

Edges are tagged ``reference | citation | latest`` so the frontend can colour and
route them. The whole snapshot is cached (see ``storage/cache.py``), keyed by
**provider *and* seed** so an OpenAlex graph is never served for an S2 selection.

The graph is a typed **Pydantic** ``Graph`` (not a bare dict — the models live
in ``model.py``), so producers and consumers agree on its shape and it validates
on the way in and out of the cache. Callers that need JSON (the routes) serialize
with ``graph.model_dump()`` / ``graph.model_dump_json()``. The cost is a
validate/deserialize on every cache hit — a deliberate trade for a schema that
can't silently drift.

This module is the domain core of the app — ``routes/graph.py``'s ``/api/graph``
is a thin wrapper over ``build_graph`` — so it's commented heavily; the
edge-direction rules in particular are load-bearing (they encode which way a
citation points) and easy to get subtly wrong.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

import datetime
import logging
from typing import Callable, Literal

from ...config import config
from ...integrations import arxiv, openalex
from ...integrations import semantic_scholar as s2
from ...storage import cache
from .model import Counts, Edge, Graph, Node, Seed
from .shape import BuildShape

log = logging.getLogger(__name__)

#: The academic-data providers a graph can be built from — one per graph, chosen
#: by the caller (the header dropdown), defaulting to ``config.providers.default_provider``.
Provider = Literal["s2", "openalex"]


def resolve_provider(raw: str | None) -> Provider:
    """Validate a requested provider name, falling back to the configured default.

    The single place request-supplied provider strings are validated — shared by
    every route that keys off the provider (the graph build and the provider-
    scoped local cache search), so they can't drift on what counts as valid.
    Anything unrecognized (missing, blank, stale, or forged) degrades to
    ``config.providers.default_provider`` rather than erroring.

    Args:
        raw: The provider string as received (e.g. a request query arg), or None.

    Returns:
        ``"s2"`` or ``"openalex"``.
    """
    normalized = (raw or "").strip().lower()
    if normalized == "s2":
        return "s2"
    if normalized == "openalex":
        return "openalex"
    return config.providers.default_provider


#: Where an s2 graph's citer relations came from — mirrors ``Graph.citation_source``.
CitationSource = Literal["corpus", "live"]

#: A traversal's payload: ``(seed_node, references, landmark_citers, latest_citers,
#: citation_source)``. Each relation list is ``[{"node", "influential"}]`` — the
#: shape graph assembly consumes, identical across providers. ``citation_source``
#: records where the citers came from (``"corpus"``/``"live"`` for s2, None for
#: OpenAlex), surfaced on the ``Graph`` so the UI can label the Field Landmarks.
#: The whole payload is None when the seed can't be resolved.
_Traversal = tuple[dict, list[dict], list[dict], list[dict], CitationSource | None]


def _traverse_s2(
    seed_ref: str, report: Callable[[int, str], None], shape: BuildShape
) -> _Traversal | None:
    """Resolve the seed and its relations through Semantic Scholar.

    Args:
        seed_ref: An arXiv id or a raw S2 paperId.
        report: The build-stage progress callback (``step`` 1-indexed, ``label``).
        shape: The per-request build shape, supplying the sizing rules and band
            dimensions this traversal injects (see :mod:`.shape`).

    Returns:
        The traversal payload (see :data:`_Traversal`), or None when S2 has no
        paper for ``seed_ref``.

    Raises:
        s2.S2Error: When a Semantic Scholar request fails after retries.
    """
    # An arXiv id has to be handed to S2 as ``ARXIV:<id>`` (its external-id
    # syntax); a raw paperId is passed through untouched.
    lookup = f"ARXIV:{seed_ref}" if arxiv.looks_arxiv(seed_ref) else seed_ref
    seed_paper = s2.get_paper(lookup)
    if not seed_paper:  # S2 knows no paper for this reference — a dead link.
        return None
    seed_id = seed_paper["id"]
    report(2, "Fetching references…")
    refs = s2.references(seed_id)
    report(3, "Fetching citations…")
    # Prefer the offline citations corpus: it holds every citation edge with the
    # citers' own counts, so landmark citers come back citation-sorted across all
    # history — the ranking S2's live endpoint can't give (newest-first, ~10k
    # offset ceiling). It returns None when unavailable (no corpus configured/
    # ingested) or when it can't resolve the seed locally, and we fall back to the
    # live path (recency-biased past the offset ceiling — the accepted interim).
    #
    # No path consults the trained model any more — since v5.13.0 every provider
    # COMPUTES its landmark budget from the pool it actually holds
    # (``budget.computed_cite_limit``, the STOP rule): the corpus over its narrow
    # ranking, OpenAlex over its one-page probe, a complete live pool in memory.
    # Only a truncated live pool differs — a recency sliver has no all-time
    # ranking to prefix, so it takes the banded SKIP selector instead (a prefix
    # there strands the recent years: DQN's top 29 are all 2019–2023, an 18-month
    # hole before the Latest frontier). See ``budget.py``'s module docstring and
    # ``docs/predict-vs-compute.md``'s epilogue.
    today = datetime.date.today()
    relations = s2.corpus.citation_relations(
        seed_paper,
        seed_ref,
        # Both providers split on the same boundary — passed in rather than
        # imported so ``integrations``' two providers stay independent of each
        # other, and computed here where the clock already lives.
        max_landmark_year=openalex.landmark_max_year(today),
        current_year=today.year,
        landmark_budget=shape.landmark_budget(),
        band_start=shape.band_start(),
        number_of_bands=shape.number_of_bands,
        nodes_per_band=shape.nodes_per_band,
    )
    citation_source: CitationSource
    if relations is not None:
        citation_source = "corpus"
        log.debug("s2 citations for %s: served from the offline citations corpus", seed_id)
    else:
        citation_source = "live"
        log.debug(
            "s2 citations for %s: corpus unavailable or seed unresolved there — "
            "using the recency-biased live S2 citation endpoint",
            seed_id,
        )
        # The live path holds two very different pools behind one call. A seed
        # whose citer list ends before the offset ceiling (most seeds) yields a
        # COMPLETE history — the STOP budget and tau band-start give it the
        # corpus shape. A truncated pool falls back to the SKIP selector and
        # rolling window (see ``s2.citation_relations``).
        relations = s2.citation_relations(
            seed_id,
            max_landmark_year=openalex.landmark_max_year(today),
            current_year=today.year,
            landmark_select=shape.landmark_select(),
            landmark_budget=shape.landmark_budget(),
            band_start=shape.band_start(),
            number_of_bands=shape.number_of_bands,
            nodes_per_band=shape.nodes_per_band,
        )
    landmark, latest = relations
    return seed_paper, refs, landmark, latest, citation_source


def _traverse_openalex(
    seed_ref: str, report: Callable[[int, str], None], shape: BuildShape
) -> _Traversal | None:
    """Resolve the seed and its relations through OpenAlex.

    Args:
        seed_ref: An arXiv id, or an S2-resolvable node id an OpenAlex graph
            carries (``DOI:…`` / ``ARXIV:…`` / ``W…``) when the user re-seeds.
        report: The build-stage progress callback (``step`` 1-indexed, ``label``).
        shape: The per-request build shape, supplying the sizing rules and band
            dimensions this traversal injects (see :mod:`.shape`).

    Returns:
        The traversal payload (see :data:`_Traversal`), or None when OpenAlex
        can't resolve ``seed_ref``.

    Raises:
        openalex.OpenAlexError: When an OpenAlex request fails after retries.
    """
    work = openalex.resolve_seed_work(seed_ref)
    if not work:
        return None
    seed_paper = openalex.node(work)
    work_id = openalex.bare_work_id(work)
    if not seed_paper or not work_id:  # a work with no usable id — unrenderable.
        return None
    report(2, "Fetching references…")
    # ``cited_by:`` — the seed's own bibliography, server-sorted by citations.
    refs = openalex.references(work_id)
    report(3, "Fetching citations…")
    # Server-sorted ``cites:`` queries return the most-cited landmark citers
    # directly (no recency bias); the STOP rule computes the band's length from
    # a one-page probe of that ranking (see ``openalex._budgeted_landmarks`` —
    # what retired the trained model from serving), and the per-seed band-start
    # rule sizes the latest frontier (see ``bands.earliest_band_year``).
    landmark, latest = openalex.citation_relations(
        work_id,
        band_start=shape.band_start(),
        landmark_budget=shape.landmark_budget(),
        number_of_bands=shape.number_of_bands,
        nodes_per_band=shape.nodes_per_band,
    )
    # OpenAlex's own server-sorted cites: queries already return true top-cited
    # landmarks, so the corpus/live distinction doesn't apply — None.
    return seed_paper, refs, landmark, latest, None


def _upgrade_node(existing: Node, sighting: dict) -> None:
    """Fold a later sighting's better data into an already-merged node.

    A paper can surface through more than one relation (e.g. it's both a
    reference the seed cites AND a citer of the seed — a mutual citation), or,
    for OpenAlex, as a duplicate work sharing the same arXiv id. The first
    sighting wins the node slot; a later one may still fill a gap. Field policy:
    ``citation_count`` takes the max (best-known count — it drives node size and
    figure-pool ranking; within one provider the sightings usually agree, so
    this mostly reconciles a missing count against a present one); identity/
    summary fields fill in only where the existing node has none. The first
    sighting's title and year stay — churning them for a tie is noise.

    Args:
        existing: The node already in the table (mutated in place).
        sighting: The later sighting's normalized node dict.
    """
    sighting_count = sighting.get("citation_count")
    if sighting_count is not None and sighting_count > (existing.citation_count or 0):
        existing.citation_count = sighting_count
    for field_name in ("arxiv_id", "abstract", "tldr", "pub_date", "month", "authors", "url"):
        if getattr(existing, field_name) is None and sighting.get(field_name) is not None:
            setattr(existing, field_name, sighting[field_name])


#: Progress callback: ``(steps_done, steps_total, label)``. The streaming
#: ``/api/graph/stream`` route bridges these into SSE ``progress`` frames so
#: the "Building graph…" overlay can show a real bar instead of a bare spinner.
#: Reported only on a cache miss — a cache hit returns before the first step.
ProgressFn = Callable[[int, int, str], None]

#: Coarse build stages, in order: the seed resolve + references + citations +
#: the final assemble — enough for a determinate bar without threading
#: sub-progress through each traversal.
_BUILD_STEPS = 4


def build_graph(
    seed_ref: str,
    *,
    provider: Provider | None = None,
    refresh: bool = False,
    shape: BuildShape | None = None,
    on_progress: ProgressFn | None = None,
) -> Graph | None:
    """Build (or load from cache) the neighborhood graph for a seed paper.

    Args:
        seed_ref: An **arXiv id** (e.g. ``"1706.03762"``) or a provider node id
            from a previous graph (an S2 paperId under ``provider="s2"``, a
            ``DOI:``/``ARXIV:``/``W…`` id under ``provider="openalex"``). The
            latter is what lets the user re-seed on *any* node — including a
            journal paper with no arXiv id — so visual traversal never
            dead-ends.
        provider: Which academic-data backend to build from (see
            :data:`Provider`). Defaults to ``config.providers.default_provider``.
        refresh: When True, bypass the cached snapshot and rebuild from the
            provider.
        shape: How much of the neighborhood to ship (see :mod:`.shape`). None
            (the default) means the adaptive shape — the app sizes itself, which
            is what every build did before the shape was a request parameter.
        on_progress: Optional coarse-stage progress callback (see
            :data:`ProgressFn`). Fired only along the rebuild path — a cache hit
            returns before any step, so the caller sees no frames.

    Returns:
        A ``Graph`` — the seed summary, deduped nodes (each carrying its
        ``rels`` and ``is_seed``), typed edges, and per-relation counts. None
        when ``seed_ref`` is blank or the provider has no paper for it.

    Raises:
        s2.S2Error: When a Semantic Scholar request fails after retries (the
            ``s2`` provider; surfaced by the route as a 502).
        openalex.OpenAlexError: When an OpenAlex request fails after retries (the
            ``openalex`` provider; surfaced by the route as a 502).
    """

    def report(step: int, label: str) -> None:
        # ``step`` is 1-indexed (the stage being entered), so the final stage
        # reports ``_BUILD_STEPS / _BUILD_STEPS`` = a full bar before the graph
        # replaces the overlay, rather than stalling short of 100%.
        if on_progress:
            on_progress(step, _BUILD_STEPS, label)

    seed_ref = (seed_ref or "").strip()
    if not seed_ref:
        return None
    provider = provider or config.providers.default_provider
    shape = shape or BuildShape()

    # --- Cache: the whole assembled snapshot, keyed by provider AND the raw seed
    # reference — an S2 graph and an OpenAlex graph for the same paper are
    # different snapshots and must not collide. Stored as JSON (model_dump), so a
    # hit costs a Graph.model_validate to rebuild the typed object.
    #
    # The shape joins the key too, or a non-adaptive build would be served the
    # adaptive snapshot it exists to replace. Its suffix is EMPTY when adaptive
    # (see ``BuildShape.cache_suffix``), so the default path keeps the pre-shape
    # key byte for byte and every snapshot cached before shapes existed still
    # hits; each distinct non-adaptive shape caches beside it, not over it.
    cache_key = f"graph:{provider}:{seed_ref}{shape.cache_suffix()}"
    if not refresh:
        cached = cache.get(cache_key, config.graph.cache_ttl)
        if cached:
            return Graph.model_validate(cached)

    # --- Resolve the seed and traverse its relations through the chosen
    # provider. One detail call + two traversals (references, citations); the
    # neighbors come back already hydrated with light display fields, so there's
    # no extra batch call to flesh them out.
    report(1, "Resolving seed paper…")
    traversal = (
        _traverse_openalex(seed_ref, report, shape)
        if provider == "openalex"
        else _traverse_s2(seed_ref, report, shape)
    )
    if traversal is None:  # the provider knows no paper for this reference.
        return None
    seed_paper, refs, landmark_cites, latest_cites, citation_source = traversal
    seed_id = seed_paper["id"]

    report(4, "Assembling graph…")

    # --- Dedupe neighbors into a single node table. The same paper can surface
    # through more than one relation (e.g. it's both a reference AND a citer — a
    # mutual citation) — and, under OpenAlex, as a DUPLICATE WORK for one paper.
    # Identity resolves through the **arXiv id** whenever a sighting has one, so
    # such a paper ends up ONE node carrying every relation tag, not two.
    nodes: dict[str, Node] = {}
    # arXiv id (lowercased) -> the node-table key that paper first resolved to.
    arxiv_index: dict[str, str] = {}

    def add_neighbor(node_data: dict, rel: str) -> str:
        """Merge a neighbor into ``nodes``, returning its canonical node id.

        First sighting builds the ``Node`` (and registers its arXiv id in the
        identity index); every later sighting of the same paper — same raw id,
        OR a different id sharing the arXiv id — appends its relation to the
        existing node's ``rels`` (deduped) and upgrades fields the later
        sighting knows better (see ``_upgrade_node``). Edges must point at the
        returned id, not at ``node_data["id"]`` — for a merged paper they
        differ.

        Args:
            node_data: The normalized node dict (from the active provider).
            rel: The relation that surfaced it (``reference | citation | latest``).

        Returns:
            The node-table key this paper resolved to (the surviving node's id).
        """
        arxiv_id = (node_data.get("arxiv_id") or "").lower()
        key = arxiv_index.get(arxiv_id, node_data["id"]) if arxiv_id else node_data["id"]
        existing = nodes.get(key)
        if existing is None:
            nodes[key] = Node(**node_data, rels=[rel], is_seed=False)
        else:
            # The seed keeps its own single tag; a neighbor accumulates.
            if rel not in existing.rels and not existing.is_seed:
                existing.rels.append(rel)
            _upgrade_node(existing, node_data)
        if arxiv_id:
            arxiv_index.setdefault(arxiv_id, key)
        return key

    # The seed goes in first, flagged so the frontend can render it distinctly —
    # and registered in the identity index, so a citer that IS the seed under
    # another id merges into it instead of duplicating it.
    seed_node = Node(**seed_paper, rels=["seed"], is_seed=True)
    nodes[seed_id] = seed_node
    if seed_node.arxiv_id:
        arxiv_index[seed_node.arxiv_id.lower()] = seed_id

    # --- Build the typed edges. The DIRECTION differs per relation and encodes
    # citation semantics — an edge always points from the citing paper to the
    # cited one:
    edges: list[Edge] = []
    # (source, target, type) triples already drawn — identity merging can make
    # two sightings collapse onto one endpoint (e.g. OpenAlex's duplicate works
    # both citing the seed), and one line is enough.
    seen_edges: set[tuple[str, str, str]] = set()

    def add_edge(source: str, target: str,
                 edge_type: Literal["reference", "citation", "latest"],
                 influential: bool | None, rank: int) -> bool:
        """Append one edge unless it's a self-loop or already drawn.

        Args:
            source: The citing end's canonical node id.
            target: The cited end's canonical node id.
            edge_type: The relation tag (``reference | citation | latest``).
            influential: S2's influential-citation flag (None where it doesn't
                apply).
            rank: The edge's reveal rank within its relation.

        Returns:
            True when the edge was drawn (so the caller advances its rank
            counter — ranks stay compact even when duplicates are skipped).
        """
        if source == target or (source, target, edge_type) in seen_edges:
            return False
        seen_edges.add((source, target, edge_type))
        edges.append(Edge(
            source=source, target=target, type=edge_type,
            influential=influential, rank=rank,
        ))
        return True

    # Each relation arrives already ranked (references/citations by citation
    # count, latest oldest-first so the reveal walks toward the present), so an
    # edge's emission index within its relation IS its `rank` — the order the
    # frontend's per-relation count slider reveals through. A skipped duplicate
    # doesn't burn a rank.

    # References: papers the SEED cites. The seed is the citer, so the arrow
    # runs seed -> ancestor. ``influential`` flags S2's "highly influential
    # citation" (the frontend can weight the edge; always None under OpenAlex).
    reference_rank = 0
    for reference in refs:
        node_id = add_neighbor(reference["node"], "reference")
        if add_edge(seed_id, node_id, "reference", reference["influential"], reference_rank):
            reference_rank += 1

    # Citations: papers that cite the SEED. Now the neighbor is the citer, so
    # the arrow runs descendant -> seed (the opposite direction from above).
    # Two disjoint relations from the same split: landmark citers ("citation")
    # and the recent frontier ("latest"), both citer -> seed.
    citation_rank = 0
    for citation in landmark_cites:
        node_id = add_neighbor(citation["node"], "citation")
        if add_edge(node_id, seed_id, "citation", citation["influential"], citation_rank):
            citation_rank += 1
    latest_rank = 0
    for latest in latest_cites:
        node_id = add_neighbor(latest["node"], "latest")
        if add_edge(node_id, seed_id, "latest", latest["influential"], latest_rank):
            latest_rank += 1

    graph = Graph(
        seed=Seed(arxiv_id=seed_node.arxiv_id, id=seed_id, title=seed_node.title),
        nodes=list(nodes.values()),
        edges=edges,
        # Post-dedupe edge counts per relation (what each slider can actually
        # reveal) plus the final node count. Note ``nodes`` < the relation sum
        # whenever a paper appeared in more than one relation and got merged.
        # ``similar`` is retired from the build (kept at 0 for schema stability).
        counts=Counts(
            references=reference_rank,
            citations=citation_rank,
            similar=0,
            latest=latest_rank,
            nodes=len(nodes),
        ),
        citation_source=citation_source,
    )
    cache.set(cache_key, graph.model_dump(mode="json"))
    return graph
