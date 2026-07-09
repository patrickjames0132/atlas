"""Assemble a paper's neighborhood graph from a hybrid of OpenAlex + S2.

Given a seed paper, build a Connected-Papers-style graph: the seed plus its
references (papers it cites — its intellectual ancestors), its citations (papers
that cite it — its descendants), and recommendation neighbors (embedding-similar
papers S2 suggests). The seed, references, and similar come from Semantic
Scholar; the **citations** come from OpenAlex (``_citation_relations``), whose
server-sorted ``cites:`` queries surface the landmark citers directly — with an
S2 fallback. Cross-source nodes carry S2-resolvable ids so they dedupe, hydrate,
and re-seed uniformly. Edges are tagged
``reference | citation | similar`` so the frontend can colour and route them.
The whole snapshot is cached (see ``storage/cache.py``) so re-exploring a paper
doesn't re-hit the rate-limited S2 API.

The graph is a typed **Pydantic** ``Graph`` (not a bare dict — the models live
in ``model.py``), so producers and consumers agree on its shape and it validates
on the way in and out of the cache. Callers that need JSON (the routes) serialize
with ``graph.model_dump()``
/ ``graph.model_dump_json()``. The cost is a validate/deserialize on every cache
hit — a deliberate trade for a schema that can't silently drift.

This module is the domain core of the app — ``routes/graph.py``'s ``/api/graph``
is a thin wrapper over ``build_graph`` — so it's commented heavily; the
edge-direction rules in particular are load-bearing (they encode which way a
citation points) and easy to get subtly wrong.
"""

from __future__ import annotations

import logging
from typing import Callable

from ...config import config
from ...integrations import arxiv, openalex
from ...integrations import semantic_scholar as s2
from ...storage import cache
from .model import Counts, Edge, Graph, Node, Seed

log = logging.getLogger(__name__)


def _citation_relations(seed_paper: dict, seed_id: str) -> tuple[list[dict], list[dict]]:
    """The seed's landmark + latest citers — from OpenAlex, falling back to S2.

    The v4.0.0 hybrid: OpenAlex owns the citation relation because a server-
    sorted ``cites:`` query returns the most-cited citers directly, killing the
    landmark recency bias without S2's reference-list mining (see the OpenAlex
    spike in ``OnePager.md``). We resolve the S2-known seed to its OpenAlex work
    (by arXiv id / title+year), then split its citers into landmark (historic,
    most-cited) and latest (recent frontier).

    Falls back to S2's ``citation_relations`` whenever OpenAlex can't help — no
    work resolved, or the API errored — so the graph is never *worse* than the
    S2-only build, only better when OpenAlex succeeds. S2 keeps references, the
    *Similar* relation, and (via each citer's S2-resolvable id) TL;DR hydration.

    Args:
        seed_paper: The normalized S2 seed node (source of arXiv id / title for
            OpenAlex resolution).
        seed_id: The seed's S2 paperId (the S2 fallback's traversal target).

    Returns:
        ``(landmark_entries, latest_entries)`` — each ``[{"node", "influential"}]``.

    Raises:
        s2.S2Error: Only from the S2 fallback path (OpenAlex errors are caught
            and degrade to that fallback).
    """
    try:
        work = openalex.resolve_work(
            arxiv_id=seed_paper.get("arxiv_id"),
            title=seed_paper.get("title"),
        )
        work_id = openalex.bare_work_id(work) if work else None
        if work_id:
            landmark, latest = openalex.citation_relations(
                work_id,
                landmark_limit=config.graph.cite_limit,
                latest_limit=config.graph.latest_limit,
            )
            log.info("citations via OpenAlex for seed %s (work %s)", seed_id, work_id)
            return landmark, latest
        log.info("OpenAlex resolved no work for seed %s; using S2 citations", seed_id)
    except openalex.OpenAlexError as exc:
        log.warning("OpenAlex citations failed for %s (%s); using S2 citations", seed_id, exc)
    return s2.citation_relations(
        seed_id,
        landmark_limit=config.graph.cite_limit,
        latest_limit=config.graph.latest_limit,
    )

#: Progress callback: ``(steps_done, steps_total, label)``. The streaming
#: ``/api/graph/stream`` route bridges these into SSE ``progress`` frames so
#: the "Building graph…" overlay can show a real bar instead of a bare spinner.
#: Reported only on a cache miss — a cache hit returns before the first step.
ProgressFn = Callable[[int, int, str], None]

#: Coarse build stages, in order. The seed resolve + three traversals + the
#: final assemble — enough for a determinate bar without threading sub-progress
#: through each S2 traversal.
_BUILD_STEPS = 5


def build_graph(
    seed_ref: str,
    *,
    refresh: bool = False,
    on_progress: ProgressFn | None = None,
) -> Graph | None:
    """Build (or load from cache) the neighborhood graph for a seed paper.

    Args:
        seed_ref: An **arXiv id** (e.g. ``"1706.03762"``) or a raw **Semantic
            Scholar paperId** (a node's ``id`` from a previous graph). The
            latter is what lets the user re-seed on *any* node — including a
            journal paper with no arXiv id — so visual traversal never
            dead-ends.
        refresh: When True, bypass the cached snapshot and rebuild from S2.
        on_progress: Optional coarse-stage progress callback (see
            :data:`ProgressFn`). Fired only along the S2 rebuild path — a cache
            hit returns before any step, so the caller sees no frames.

    Returns:
        A ``Graph`` — the seed summary, deduped nodes (each carrying its
        ``rels`` and ``is_seed``), typed edges, and per-relation counts. None
        when ``seed_ref`` is blank or S2 has no paper for it.

    Raises:
        s2.S2Error: When a Semantic Scholar request fails after retries
            (surfaced by the route as a 502).
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

    # --- Cache: the whole assembled snapshot, keyed by the raw seed reference.
    # It's stored as JSON (model_dump), so a hit costs a Graph.model_validate to
    # rebuild the typed object — the deserialization price we accept for a
    # schema that validates instead of trusting a loose dict.
    cache_key = f"graph:{seed_ref}"
    if not refresh:
        cached = cache.get(cache_key, config.graph.cache_ttl)
        if cached:
            return Graph.model_validate(cached)

    # --- Resolve the seed. An arXiv id has to be handed to S2 as ``ARXIV:<id>``
    # (its external-id syntax); a raw paperId is passed through untouched.
    report(1, "Resolving seed paper…")
    lookup = f"ARXIV:{seed_ref}" if arxiv.looks_arxiv(seed_ref) else seed_ref
    seed_paper = s2.get_paper(lookup)
    if not seed_paper:  # S2 knows no paper for this reference — a dead link.
        return None
    seed_id = seed_paper["id"]

    # --- One detail call (above) + three traversals. The neighbors come back
    # already hydrated with light display fields, so there's no extra batch
    # call to flesh them out — what a traversal returns is ready to render.
    report(2, "Fetching references…")
    refs = s2.references(seed_id, config.graph.ref_limit)
    # Citations split into two disjoint relations — landmark (most-cited
    # historic citers) and the latest frontier (last ~12 months) — from OpenAlex
    # (server-sorted ``cites:`` queries, no recency bias), falling back to S2's
    # paged+mined path when OpenAlex can't resolve the seed. See
    # ``_citation_relations`` and the OpenAlex spike in OnePager.md.
    report(3, "Fetching citations…")
    landmark_cites, latest_cites = _citation_relations(seed_paper, seed_id)
    report(4, "Finding similar work…")
    similar = s2.recommendations(seed_id, config.graph.similar_limit)

    report(5, "Assembling graph…")

    # --- Dedupe neighbors into a single node table keyed by paperId. The same
    # paper can surface through more than one relation (e.g. it's both a
    # reference AND a recommendation); we want ONE node carrying BOTH relation
    # tags, not two nodes.
    nodes: dict[str, Node] = {}

    def add_neighbor(node_data: dict, rel: str) -> None:
        """Merge a neighbor into ``nodes``, accumulating its relation tags.

        First sighting builds the ``Node``; every later sighting just appends
        its relation to the existing node's ``rels`` (deduped), so a paper
        reached three ways ends up one node with three tags.

        Args:
            node_data: The normalized S2 node dict.
            rel: The relation that surfaced it (``reference | citation |
                similar | latest``).
        """
        existing = nodes.get(node_data["id"])
        if existing is None:
            nodes[node_data["id"]] = Node(**node_data, rels=[rel], is_seed=False)
        elif rel not in existing.rels:
            existing.rels.append(rel)

    # The seed goes in first, flagged so the frontend can render it distinctly.
    seed_node = Node(**seed_paper, rels=["seed"], is_seed=True)
    nodes[seed_id] = seed_node

    # --- Build the typed edges. The DIRECTION differs per relation and encodes
    # citation semantics — an edge always points from the citing paper to the
    # cited one:
    edges: list[Edge] = []

    # Each relation arrives already ranked (references/citations by citation
    # count, latest oldest-first so the reveal walks toward the present,
    # similar by S2 similarity), so an edge's enumeration index within its
    # relation IS its `rank` — the order the frontend's per-relation count
    # slider reveals through.

    # References: papers the SEED cites. The seed is the citer, so the arrow
    # runs seed -> ancestor. ``influential`` flags S2's "highly influential
    # citation" (the frontend can weight the edge).
    for reference_rank, reference in enumerate(refs):
        add_neighbor(reference["node"], "reference")
        edges.append(Edge(
            source=seed_id,
            target=reference["node"]["id"],
            type="reference",
            influential=reference["influential"],
            rank=reference_rank,
        ))

    # Citations: papers that cite the SEED. Now the neighbor is the citer, so
    # the arrow runs descendant -> seed (the opposite direction from above).
    # Two disjoint relations from the same split: landmark citers ("citation")
    # and the recent frontier ("latest"), both citer -> seed.
    for citation_rank, citation in enumerate(landmark_cites):
        add_neighbor(citation["node"], "citation")
        edges.append(Edge(
            source=citation["node"]["id"],
            target=seed_id,
            type="citation",
            influential=citation["influential"],
            rank=citation_rank,
        ))
    for latest_rank, latest in enumerate(latest_cites):
        add_neighbor(latest["node"], "latest")
        edges.append(Edge(
            source=latest["node"]["id"],
            target=seed_id,
            type="latest",
            influential=latest["influential"],
            rank=latest_rank,
        ))

    # Recommendations: embedding-similar papers. These are NOT citations, so
    # there's no direction meaning and no ``influential`` (left None); we draw
    # seed -> neighbor just to anchor them to the seed visually.
    for similar_rank, recommendation in enumerate(similar):
        add_neighbor(recommendation["node"], "similar")
        edges.append(Edge(
            source=seed_id,
            target=recommendation["node"]["id"],
            type="similar",
            rank=similar_rank,
        ))

    graph = Graph(
        seed=Seed(arxiv_id=seed_node.arxiv_id, id=seed_id, title=seed_node.title),
        nodes=list(nodes.values()),
        edges=edges,
        # Raw traversal sizes (not deduped) plus the final node count. Note
        # ``nodes`` < references + citations + similar + latest whenever a paper
        # appeared in more than one relation and got merged above.
        counts=Counts(
            references=len(refs),
            citations=len(landmark_cites),
            similar=len(similar),
            latest=len(latest_cites),
            nodes=len(nodes),
        ),
    )
    cache.set(cache_key, graph.model_dump(mode="json"))
    return graph
