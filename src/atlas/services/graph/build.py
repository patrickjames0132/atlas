"""Assemble a paper's neighborhood graph from a hybrid of OpenAlex + S2.

Given a seed paper, build a Connected-Papers-style graph: the seed plus its
references (papers it cites — its intellectual ancestors), its citations (papers
that cite it — its descendants), and recommendation neighbors (embedding-similar
papers S2 suggests). The seed, references, and similar come from Semantic
Scholar; the **citations** come from OpenAlex (``_citation_relations``), whose
server-sorted ``cites:`` queries surface the landmark citers directly — with an
S2 fallback. Cross-source nodes carry S2-resolvable ids so they hydrate and
re-seed uniformly, and node **identity resolves through the arXiv id** so the
same paper arriving under an S2 paperId and an OpenAlex ``DOI:``/``ARXIV:`` id
merges into one node instead of duplicating. Edges are tagged
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

import datetime
import logging
from typing import Callable, Literal

from ...config import config
from ...integrations import arxiv, openalex
from ...integrations import semantic_scholar as s2
from ...storage import cache
from . import bands, budget
from .model import Counts, Edge, Graph, Node, Seed

log = logging.getLogger(__name__)


def _adaptive_cite_limit(seed_paper: dict) -> int | None:
    """The seed-adapted landmark ship count from the trained cite-budget model.

    A thin wrapper over :func:`budget.adaptive_cite_limit` that pins the
    reference year to today (age is measured from here). The model, its feature
    contract, and the fallback rules live in ``budget.py``; the training
    pipeline that produces it lives in ``src/ml_pipelines/cite_budget``.

    Args:
        seed_paper: The normalized S2 seed node (``year`` and
            ``citation_count`` drive the model).

    Returns:
        The landmark limit to ship — a model-predicted count, or the configured
        ``cite_limit`` passed through when the feature is off, the seed lacks a
        year, or the model isn't loadable (see :func:`budget.adaptive_cite_limit`).
    """
    return budget.adaptive_cite_limit(seed_paper, as_of_year=datetime.date.today().year)


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
    # One budget for both sources, so the OpenAlex path and the S2 fallback
    # agree on how many landmarks a given seed deserves.
    landmark_limit = _adaptive_cite_limit(seed_paper)
    try:
        work = openalex.resolve_work(
            arxiv_id=seed_paper.get("arxiv_id"),
            title=seed_paper.get("title"),
        )
        work_id = openalex.bare_work_id(work) if work else None
        if work_id:
            landmark, latest = openalex.citation_relations(
                work_id,
                landmark_limit=landmark_limit,
                latest_limit=config.graph.latest_limit,
                band_start=bands.earliest_band_year,
            )
            log.info("citations via OpenAlex for seed %s (work %s)", seed_id, work_id)
            return landmark, latest
        log.info("OpenAlex resolved no work for seed %s; using S2 citations", seed_id)
    except openalex.OpenAlexError as exc:
        log.warning("OpenAlex citations failed for %s (%s); using S2 citations", seed_id, exc)
    return s2.citation_relations(
        seed_id,
        landmark_limit=landmark_limit,
        latest_limit=config.graph.latest_limit,
    )

def _upgrade_node(existing: Node, sighting: dict) -> None:
    """Fold a later sighting's better data into an already-merged node.

    Cross-source merging means the first-seen record wins the node slot, but a
    later sighting may know the paper better — S2's citation counts are far
    more complete than OpenAlex's for arXiv papers, and either source can be
    the one carrying the abstract/date. Field policy: ``citation_count`` takes
    the max (best-known count — it drives node size and figure-pool ranking);
    identity/summary fields fill in only where the existing node has none.
    The first sighting's title and year stay — churning them for a tie is
    noise.

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
    # historic citers) and the latest frontier (recent per-year bands) — from OpenAlex
    # (server-sorted ``cites:`` queries, no recency bias), falling back to S2's
    # paged+mined path when OpenAlex can't resolve the seed. See
    # ``_citation_relations`` and the OpenAlex spike in OnePager.md.
    report(3, "Fetching citations…")
    landmark_cites, latest_cites = _citation_relations(seed_paper, seed_id)
    report(4, "Finding similar work…")
    similar = s2.recommendations(seed_id, config.graph.similar_limit)

    report(5, "Assembling graph…")

    # --- Dedupe neighbors into a single node table. The same paper can surface
    # through more than one relation (e.g. it's both a reference AND a
    # recommendation) — and, since the OpenAlex hybrid, under more than one ID
    # SCHEME: S2 relations carry bare paperIds while OpenAlex citers carry
    # ``DOI:``/``ARXIV:``/``W…`` ids (and OpenAlex itself sometimes holds
    # duplicate works for one paper). Identity therefore resolves through the
    # **arXiv id** whenever a sighting has one — the one id both sources agree
    # on — so a paper reached from both sources ends up ONE node carrying every
    # relation tag, not two or three nodes (the DQN/DDPG triple of v4.4.0).
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
            node_data: The normalized node dict (S2 or OpenAlex sourced).
            rel: The relation that surfaced it (``reference | citation |
                similar | latest``).

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
    # and registered in the identity index, so a citer/recommendation that IS
    # the seed under another id merges into it instead of duplicating it.
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
                 edge_type: Literal["reference", "citation", "similar", "latest"],
                 influential: bool | None, rank: int) -> bool:
        """Append one edge unless it's a self-loop or already drawn.

        Args:
            source: The citing end's canonical node id.
            target: The cited end's canonical node id.
            edge_type: The relation tag (``reference | citation | similar |
                latest``).
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
    # count, latest oldest-first so the reveal walks toward the present,
    # similar by S2 similarity), so an edge's emission index within its
    # relation IS its `rank` — the order the frontend's per-relation count
    # slider reveals through. A skipped duplicate doesn't burn a rank.

    # References: papers the SEED cites. The seed is the citer, so the arrow
    # runs seed -> ancestor. ``influential`` flags S2's "highly influential
    # citation" (the frontend can weight the edge).
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

    # Recommendations: embedding-similar papers. These are NOT citations, so
    # there's no direction meaning and no ``influential`` (left None); we draw
    # seed -> neighbor just to anchor them to the seed visually.
    similar_rank = 0
    for recommendation in similar:
        node_id = add_neighbor(recommendation["node"], "similar")
        if add_edge(seed_id, node_id, "similar", None, similar_rank):
            similar_rank += 1

    graph = Graph(
        seed=Seed(arxiv_id=seed_node.arxiv_id, id=seed_id, title=seed_node.title),
        nodes=list(nodes.values()),
        edges=edges,
        # Post-dedupe edge counts per relation (what each slider can actually
        # reveal) plus the final node count. Note ``nodes`` < the relation sum
        # whenever a paper appeared in more than one relation and got merged.
        counts=Counts(
            references=reference_rank,
            citations=citation_rank,
            similar=similar_rank,
            latest=latest_rank,
            nodes=len(nodes),
        ),
    )
    cache.set(cache_key, graph.model_dump(mode="json"))
    return graph
