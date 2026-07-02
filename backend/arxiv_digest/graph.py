"""Assemble a paper's neighborhood graph from Semantic Scholar.

Given a seed arXiv id, build a Connected-Papers-style graph: the seed plus its
references (ancestors it cites), citations (descendants that cite it), and
recommendation neighbors (embedding-similar papers). Nodes are deduped by S2
paperId; edges are tagged ``reference | citation | similar`` so the frontend can
color/route them. The whole snapshot is cached (see cache.py) so repeat
exploration doesn't re-hit the rate-limited API.
"""

from __future__ import annotations

import logging
from typing import Optional

from . import arxiv_client, cache, config
from . import semantic_scholar as s2

log = logging.getLogger(__name__)


def _looks_arxiv(ref: str) -> bool:
    """True if `ref` is an arXiv id (vs. a raw Semantic Scholar paperId)."""
    return bool(arxiv_client._ID_RE.fullmatch(ref))


def build_graph(seed_ref: str, *, refresh: bool = False) -> Optional[dict]:
    """Build (or load from cache) the neighborhood graph for a seed paper.

    `seed_ref` may be an **arXiv id** (e.g. "1706.03762") or a raw **Semantic
    Scholar paperId** (a node's ``id`` from a previous graph) — the latter lets
    the user re-seed on any node, including journal papers with no arXiv id, so
    visual traversal never dead-ends. Returns ``{seed, nodes, edges, counts}`` or
    None if S2 has no paper for that ref.
    """
    seed_ref = (seed_ref or "").strip()
    if not seed_ref:
        return None

    cache_key = f"graph:{seed_ref}"
    if not refresh:
        cached = cache.get(cache_key, config.GRAPH_CACHE_TTL)
        if cached:
            return cached

    lookup = f"ARXIV:{seed_ref}" if _looks_arxiv(seed_ref) else seed_ref
    seed = s2.get_paper(lookup)
    if not seed:
        return None
    seed_id = seed["id"]

    # One detail call (above) + three traversals. Neighbors arrive already
    # hydrated with light fields, so no extra batch call is needed.
    refs = s2.references(seed_id, config.GRAPH_REF_LIMIT)
    cites = s2.citations(seed_id, config.GRAPH_CITE_LIMIT)
    similar = s2.recommendations(seed_id, config.GRAPH_SIMILAR_LIMIT)

    nodes: dict[str, dict] = {}

    def add(node: dict, rel: str) -> None:
        existing = nodes.get(node["id"])
        if existing is None:
            node = dict(node)
            node["rels"] = [rel]
            node["is_seed"] = False
            nodes[node["id"]] = node
        elif rel not in existing["rels"]:
            existing["rels"].append(rel)

    seed = dict(seed)
    seed["rels"] = ["seed"]
    seed["is_seed"] = True
    nodes[seed_id] = seed

    edges: list[dict] = []
    for r in refs:
        add(r["node"], "reference")
        # seed -> ancestor (the seed cites it)
        edges.append({
            "source": seed_id, "target": r["node"]["id"],
            "type": "reference", "influential": r["influential"],
        })
    for c in cites:
        add(c["node"], "citation")
        # descendant -> seed (it cites the seed)
        edges.append({
            "source": c["node"]["id"], "target": seed_id,
            "type": "citation", "influential": c["influential"],
        })
    for s in similar:
        add(s["node"], "similar")
        edges.append({
            "source": seed_id, "target": s["node"]["id"], "type": "similar",
        })

    result = {
        "seed": {
            "arxiv_id": seed.get("arxiv_id"),
            "id": seed_id,
            "title": seed["title"],
        },
        "nodes": list(nodes.values()),
        "edges": edges,
        "counts": {
            "references": len(refs),
            "citations": len(cites),
            "similar": len(similar),
            "nodes": len(nodes),
        },
    }
    cache.set(cache_key, result)
    return result
