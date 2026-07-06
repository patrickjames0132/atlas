"""The "How we got here" time-travel walk: hop backward through references
before a history lecture, so the story can open at the field's roots.

Deterministic — no LLM ever touches this. A modern seed's graph rarely
reaches the foundational work, so the walk launches NOT from the seed (its
references are already on screen) but from the OLDEST visible papers, which
sit closest to the roots. Each hop pulls their references (day-cached via
``agents.traversal``), keeps the most-cited new ancestors, and carries the
oldest additions into the next hop — stopping at the hop budget, an
exhausted frontier, or once the story reaches ``lookback_years`` before the
seed. All knobs live in ``config.graph.backfill``.

S2 errors on a hop are noted and skipped, never raised: a failed hop must
not abort the lecture.
"""

from __future__ import annotations

from typing import Iterator

from ...config import config
from ...integrations import semantic_scholar as s2
from ...services.graph import Edge, Node
from .. import events, traversal


def _seed_year(nodes: list[Node], seed_id: str) -> int | None:
    """The seed's publication year: its own when present, else the newest
    visible year (the seed is almost always the most recent paper), else
    None when no node carries a year at all."""
    for node in nodes:
        if node.id == seed_id and node.year is not None:
            return node.year
    years = [node.year for node in nodes if node.year is not None]
    return max(years) if years else None


def history_backfill(
    seed: Node, nodes: list[Node]
) -> Iterator[events.BackfillTrace | events.Discovery]:
    """Walk backward through references, yielding ancestors for the graph.

    Args:
        seed: The seed paper (a blank id makes the walk a no-op).
        nodes: The visible graph nodes.

    Yields:
        Per productive hop, one ``BackfillTrace`` (hop number, papers found,
        oldest year) then one ``Discovery`` (the ancestor nodes + the edges
        whose endpoints both landed on the graph). Discovered nodes carry
        ``idx=None`` — the walk runs *before* the lecturer numbers anything.
        When nothing older was found at all, one final trace says so, with
        ``error=True`` if any hop failed ("we found nothing" and "we
        couldn't look" read differently).
    """
    knobs = config.graph.backfill
    if not seed.id:
        return

    known = {node.id for node in nodes}
    known.add(seed.id)
    seed_year = _seed_year(nodes, seed.id)
    year_floor = seed_year - knobs.lookback_years if seed_year else None

    launch = sorted(
        (node for node in nodes if node.id and not node.is_seed),
        key=lambda node: node.year if node.year is not None else 9999,
    )
    frontier = [node.id for node in launch[: knobs.frontier]] or [seed.id]
    total_added = 0
    errored = False

    for hop in range(knobs.hops):
        if not frontier:
            break
        candidates: dict[str, dict] = {}
        edges: list[Edge] = []
        for paper_id in frontier:
            try:
                hits = traversal.neighbors(paper_id, "references", knobs.fetch_limit)
            except s2.S2Error:
                errored = True
                continue
            for hit in hits:
                neighbor = hit["node"]
                neighbor_id = neighbor.get("id")
                if not neighbor_id or neighbor_id == paper_id:
                    continue
                edges.append(
                    Edge(
                        source=paper_id,
                        target=neighbor_id,
                        type="reference",
                        influential=hit.get("influential", False),
                    )
                )
                if neighbor_id not in known and neighbor_id not in candidates:
                    candidates[neighbor_id] = neighbor
        if not candidates:
            break

        # Keep the most-cited new ancestors (the seminal ones), capped per hop.
        ranked = sorted(
            candidates.values(),
            key=lambda candidate: candidate.get("citation_count") or 0,
            reverse=True,
        )
        additions = [
            events.DiscoveredNode(**candidate, rels=["reference"], is_seed=False)
            for candidate in ranked[: knobs.per_hop]
        ]
        known.update(addition.id for addition in additions)

        # Only edges whose endpoints both landed on the graph (no danglers).
        kept_edges = [
            edge for edge in edges if edge.source in known and edge.target in known
        ]
        years = [addition.year for addition in additions if addition.year is not None]
        oldest = min(years) if years else None
        total_added += len(additions)
        yield events.BackfillTrace(hop=hop + 1, found=len(additions), oldest=oldest)
        yield events.Discovery(nodes=additions, edges=kept_edges)

        # March further back: the oldest additions become the next launch points.
        by_year = sorted(
            additions, key=lambda addition: addition.year if addition.year is not None else 9999
        )
        frontier = [addition.id for addition in by_year[: knobs.frontier]]
        if year_floor and oldest is not None and oldest <= year_floor:
            break

    # Never found anything older — say so once, rather than failing silently.
    if total_added == 0:
        yield events.BackfillTrace(hop=1, found=0, oldest=None, error=errored)
