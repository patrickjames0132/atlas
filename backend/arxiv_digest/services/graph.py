"""Assemble a paper's neighborhood graph from Semantic Scholar.

Given a seed arXiv id, build a Connected-Papers-style graph: the seed plus its
references (ancestors it cites), citations (descendants that cite it), and
recommendation neighbors (embedding-similar papers). Nodes are deduped by S2
paperId; edges are tagged ``reference | citation | similar`` so the frontend can
color/route them. The whole snapshot is cached (see storage/cache.py) so repeat
exploration doesn't re-hit the rate-limited API.
"""

from __future__ import annotations

import logging
from typing import Optional

from .. import config
from ..integrations import arxiv_client
from ..integrations import semantic_scholar as s2
from ..storage import cache

log = logging.getLogger(__name__)


def _looks_arxiv(ref: str) -> bool:
    """Distinguish an arXiv id from a raw Semantic Scholar paperId.

    Args:
        ref: The seed reference the user (or a re-seed click) supplied.

    Returns:
        True when ``ref`` matches the arXiv id pattern (new- or old-style,
        with or without a version suffix); False for anything else — treated
        as an S2 paperId.
    """
    return bool(arxiv_client._ID_RE.fullmatch(ref))


def build_graph(seed_ref: str, *, refresh: bool = False) -> Optional[dict]:
    """Build (or load from cache) the neighborhood graph for a seed paper.

    One S2 detail call for the seed plus three traversals (references,
    citations, recommendations). Neighbors arrive already hydrated with light
    fields, so no extra batch call is needed. The finished snapshot is cached
    under ``graph:<seed_ref>`` for ``GRAPH_CACHE_TTL`` seconds.

    Args:
        seed_ref: An **arXiv id** (e.g. ``"1706.03762"``) or a raw **Semantic
            Scholar paperId** (a node's ``id`` from a previous graph) — the
            latter lets the user re-seed on any node, including journal papers
            with no arXiv id, so visual traversal never dead-ends.
        refresh: When True, bypass the cached snapshot and rebuild from S2.

    Returns:
        ``{"seed", "nodes", "edges", "counts"}`` — the seed summary, deduped
        node dicts (each carrying its ``rels`` and ``is_seed`` flags), typed
        edges, and per-relation counts. None when ``seed_ref`` is blank or S2
        has no paper for it.

    Raises:
        s2.S2Error: When a Semantic Scholar request fails after retries
            (surfaced by the route as a 502).
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
        """Dedupe a neighbor into ``nodes``, accumulating its relation tags.

        Args:
            node: The normalized S2 node dict.
            rel: The relation that surfaced it (``reference | citation |
                similar``) — appended to an existing node's ``rels`` rather
                than duplicating the node.
        """
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
