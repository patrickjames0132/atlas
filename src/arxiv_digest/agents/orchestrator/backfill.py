"""The "How we got here" time-travel walk: hop backward through references
before a history lecture, so the story can open at the field's roots.

Deterministic — no LLM ever touches this. A modern seed's graph rarely
reaches the foundational work, so the walk launches NOT from the seed (its
references are already on screen) but from the OLDEST visible papers, which
sit closest to the roots. Each hop pulls their references (day-cached via
``agents.traversal``), keeps the most-cited new ancestors, and carries the
oldest additions into the next hop — stopping at the hop budget, an
exhausted frontier, or once the story reaches ``lookback_years`` before the
seed. All knobs live in ``config.graph.backfill``; the algorithm is walked
step by step in this package's README.

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

    # --- The dedup ledger. ``known`` holds every paper id that is (or has
    # become) part of the graph — the visible nodes plus each hop's kept
    # additions. It serves two distinct jobs below: candidate filtering (a
    # paper already on the graph is never "discovered" again) and edge
    # filtering (an edge is only worth sending if BOTH its endpoints are on
    # the graph).
    known = {node.id for node in nodes}
    known.add(seed.id)

    # --- The stopping line. The walk is a march back through time, and
    # ``year_floor`` is where the story stops being this paper's prehistory:
    # once a hop's additions reach ``lookback_years`` (~a career length)
    # before the seed, older work stops being interpretable context and the
    # march ends. No seed year at all -> no floor; only the hop budget stops
    # the walk.
    seed_year = _seed_year(nodes, seed.id)
    year_floor = seed_year - knobs.lookback_years if seed_year else None

    # --- Launch from the OLDEST visible papers, never the seed. Expanding
    # the seed can only re-find its own references — which are, by
    # definition, already on the graph. The oldest papers on screen sit
    # closest to the field's roots, so *their* references are the first
    # papers the graph hasn't shown yet. (Seed-as-frontier is only the
    # degenerate fallback when the graph shows nothing but the seed.)
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

        # --- Fetch phase: pull every frontier paper's references (one
        # day-cached S2 call each — ``fetch_limit`` caps the fan-out).
        # ``candidates`` collects papers not yet on the graph, first-seen
        # wins; ``edges`` collects EVERY reference edge we saw, even to
        # papers that may not make the cut — the keep-or-drop decision
        # can't be made until ranking picks this hop's additions.
        candidates: dict[str, dict] = {}
        edges: list[Edge] = []
        for paper_id in frontier:
            try:
                hits = traversal.neighbors(paper_id, "references", knobs.fetch_limit)
            except s2.S2Error:
                # A failed hop is noted (for the final trace's error flag)
                # and skipped — the lecture happens with or without it.
                errored = True
                continue
            for hit in hits:
                neighbor = hit["node"]
                neighbor_id = neighbor.get("id")
                if not neighbor_id or neighbor_id == paper_id:
                    continue
                # Edge direction encodes citation semantics (same rule as
                # build_graph): a reference edge points citing -> cited, and
                # here the frontier paper is always the one doing the citing.
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
            break  # every reference we can reach is already on the graph

        # --- Selection phase: keep the most-cited candidates, capped at
        # ``per_hop``. Citation count is the proxy for "seminal" — the walk
        # exists to surface the foundational papers a lecture should open
        # with, not every stray reference. The cap keeps each hop's graph
        # growth digestible on the canvas.
        ranked = sorted(
            candidates.values(),
            key=lambda candidate: candidate.get("citation_count") or 0,
            reverse=True,
        )
        # idx stays None: numbering is positional and happens later, when
        # the orchestrator hands the enriched node set to the lecturer.
        additions = [
            events.DiscoveredNode(**candidate, rels=["reference"], is_seed=False)
            for candidate in ranked[: knobs.per_hop]
        ]
        known.update(addition.id for addition in additions)

        # --- Edge filter: only edges whose endpoints BOTH landed on the
        # graph. A candidate that lost the ranking never became a node, so
        # its edges would dangle — the frontend would either drop them or,
        # worse, invent phantom nodes for them.
        kept_edges = [
            edge for edge in edges if edge.source in known and edge.target in known
        ]

        years = [addition.year for addition in additions if addition.year is not None]
        oldest = min(years) if years else None
        total_added += len(additions)
        # Trace first ("hop 2: found 4, oldest 1986"), then the payload the
        # frontend merges — same order the user watches it happen.
        yield events.BackfillTrace(hop=hop + 1, found=len(additions), oldest=oldest)
        yield events.Discovery(nodes=additions, edges=kept_edges)

        # --- March phase: the OLDEST additions become the next frontier —
        # each hop launches from the furthest-back papers found so far, so
        # the walk moves monotonically toward the roots instead of wandering
        # sideways through contemporaries. All additions are on-graph now,
        # so the next hop's edges will connect to visible papers.
        by_year = sorted(
            additions, key=lambda addition: addition.year if addition.year is not None else 9999
        )
        frontier = [addition.id for addition in by_year[: knobs.frontier]]
        if year_floor and oldest is not None and oldest <= year_floor:
            break  # reached the field's prehistory — the story has its roots

    # --- Honest empty result. Zero additions across all hops gets ONE
    # explicit trace instead of silence, and ``errored`` distinguishes "the
    # graph already reaches its roots" (found nothing, fine) from "S2 was
    # down and we couldn't look" (found nothing, suspect).
    if total_added == 0:
        yield events.BackfillTrace(hop=1, found=0, oldest=None, error=errored)
