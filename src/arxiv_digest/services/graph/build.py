"""Assemble a paper's neighborhood graph from Semantic Scholar.

Given a seed paper, build a Connected-Papers-style graph: the seed plus its
references (papers it cites — its intellectual ancestors), its citations (papers
that cite it — its descendants), and recommendation neighbors (embedding-similar
papers S2 suggests). Nodes are deduped by S2 ``paperId``; edges are tagged
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

from ...config import config
from ...integrations import arxiv
from ...integrations import semantic_scholar as s2
from ...storage import cache
from .model import Counts, Edge, Graph, Node, Seed

log = logging.getLogger(__name__)


def _looks_arxiv(ref: str) -> bool:
    """Distinguish an arXiv id from a raw Semantic Scholar paperId.

    The seed can arrive as either — an arXiv id (from the search box) or a raw
    S2 ``paperId`` (from clicking a node in an existing graph). S2's lookup
    needs them addressed differently (an arXiv id must be prefixed ``ARXIV:``),
    so we sniff which one we're holding.

    Args:
        ref: The seed reference the user (or a re-seed click) supplied.

    Returns:
        True when ``ref`` is *entirely* an arXiv id (new- or old-style, with or
        without a version suffix). ``fullmatch`` — not ``search`` — because a
        bare S2 paperId must NOT be mistaken for one.
    """
    return bool(arxiv.ID_RE.fullmatch(ref))


def build_graph(seed_ref: str, *, refresh: bool = False) -> Graph | None:
    """Build (or load from cache) the neighborhood graph for a seed paper.

    Args:
        seed_ref: An **arXiv id** (e.g. ``"1706.03762"``) or a raw **Semantic
            Scholar paperId** (a node's ``id`` from a previous graph). The
            latter is what lets the user re-seed on *any* node — including a
            journal paper with no arXiv id — so visual traversal never
            dead-ends.
        refresh: When True, bypass the cached snapshot and rebuild from S2.

    Returns:
        A ``Graph`` — the seed summary, deduped nodes (each carrying its
        ``rels`` and ``is_seed``), typed edges, and per-relation counts. None
        when ``seed_ref`` is blank or S2 has no paper for it.

    Raises:
        s2.S2Error: When a Semantic Scholar request fails after retries
            (surfaced by the route as a 502).
    """
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
    lookup = f"ARXIV:{seed_ref}" if _looks_arxiv(seed_ref) else seed_ref
    seed_paper = s2.get_paper(lookup)
    if not seed_paper:  # S2 knows no paper for this reference — a dead link.
        return None
    seed_id = seed_paper["id"]

    # --- One detail call (above) + three traversals. The neighbors come back
    # already hydrated with light display fields, so there's no extra batch
    # call to flesh them out — what a traversal returns is ready to render.
    refs = s2.references(seed_id, config.graph.ref_limit)
    cites = s2.citations(seed_id, config.graph.cite_limit)
    similar = s2.recommendations(seed_id, config.graph.similar_limit)

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
                similar``).
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

    # References: papers the SEED cites. The seed is the citer, so the arrow
    # runs seed -> ancestor. ``influential`` flags S2's "highly influential
    # citation" (the frontend can weight the edge).
    for reference in refs:
        add_neighbor(reference["node"], "reference")
        edges.append(Edge(
            source=seed_id,
            target=reference["node"]["id"],
            type="reference",
            influential=reference["influential"],
        ))

    # Citations: papers that cite the SEED. Now the neighbor is the citer, so
    # the arrow runs descendant -> seed (the opposite direction from above).
    for citation in cites:
        add_neighbor(citation["node"], "citation")
        edges.append(Edge(
            source=citation["node"]["id"],
            target=seed_id,
            type="citation",
            influential=citation["influential"],
        ))

    # Recommendations: embedding-similar papers. These are NOT citations, so
    # there's no direction meaning and no ``influential`` (left None); we draw
    # seed -> neighbor just to anchor them to the seed visually.
    for recommendation in similar:
        add_neighbor(recommendation["node"], "similar")
        edges.append(Edge(
            source=seed_id,
            target=recommendation["node"]["id"],
            type="similar",
        ))

    graph = Graph(
        seed=Seed(arxiv_id=seed_node.arxiv_id, id=seed_id, title=seed_node.title),
        nodes=list(nodes.values()),
        edges=edges,
        # Raw traversal sizes (not deduped) plus the final node count. Note
        # ``nodes`` < references + citations + similar whenever a paper appeared
        # in more than one relation and got merged above.
        counts=Counts(
            references=len(refs),
            citations=len(cites),
            similar=len(similar),
            nodes=len(nodes),
        ),
    )
    cache.set(cache_key, graph.model_dump(mode="json"))
    return graph
