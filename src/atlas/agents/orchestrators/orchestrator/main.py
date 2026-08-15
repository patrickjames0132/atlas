"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
The orchestrator: one entry point for every teacher workflow.

Routes call ``run(intent, ...)`` with the UI's intent hint and get back the
full typed event stream, always terminated by ``Done`` or ``Error`` — this
is the one place that contract is enforced, so the frontend never hangs on
a dead stream. Known intents dispatch deterministically per the playbooks
in ``skills/workflows/``:

* ``lecture``   — delegation to ``lecturer.lecture``. A lecture narrates
  the graph *as the user sees it* — it never expands nodes (that's the
  researcher's job, on explicit questions). Modes are scoped by
  ``_story_nodes``, one graph relation each: history narrates the seed's
  references, evolution the landmark citers, frontier the Latest-Publications
  nodes; intuition stays on the seed alone and bridge sees the whole visible
  set.
* ``research``  — pure delegation to ``researcher.answer``.

**No model lives here yet — deliberately.** The locked design is hybrid
(deterministic dispatch for known intents, the orchestrator's own model
engaging only for ambiguous or multi-step asks), but every current entry
point passes a known intent, so building the Agent now would be speculative
LLM plumbing — the same call as the query-expansion seam in Phase 3. When a
free-form entry point exists in the UI, the model half lands here.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

import logging
from typing import Iterator

from ....services.graph import Node, Provider
from .. import lecturer, researcher
from ... import events
from ...models import Intent, LectureMode, PlayedLecture

log = logging.getLogger(__name__)

# Which graph relation each directional lecture narrates. A mode is now pinned
# to exactly ONE kind of neighbor (the tag ``build.py`` writes into a node's
# ``rels``) rather than to a slice of the timeline: HISTORY tells the story of
# the seed's references, LANDMARKS ("evolution") of the landmark citers, and
# FRONTIER of the recent "Latest Publications" bands. INTUITION and BRIDGE
# aren't relation-scoped (see ``_story_nodes``).
_MODE_RELATION: dict[LectureMode, str] = {
    LectureMode.HISTORY: "reference",
    LectureMode.EVOLUTION: "citation",
    LectureMode.FRONTIER: "latest",
}


def _chronological(nodes: list[Node]) -> list[Node]:
    """The nodes sorted oldest-first, undated ones last.

    The ordering half of the full-span guardrail: the lecturer numbers the
    story in this order and (via ``prompts.node_lines_by_era``) can band it by
    era, so a beat's papers read left-to-right in time instead of by citation
    count. ``node_lines``/``idx_to_id`` stay consistent because the same
    ordered list is both numbered and mapped back.

    Args:
        nodes: The story's nodes, in arbitrary order.

    Returns:
        The nodes sorted by year ascending, undated papers pushed to the end.
    """
    return sorted(nodes, key=lambda node: (node.year is None, node.year or 0))


def _story_nodes(seed: Node, nodes: list[Node], mode: LectureMode) -> list[Node]:
    """The node set a lecture mode may narrate.

    A lecture never expands the graph — and each mode is pinned to exactly one
    kind of neighbor so the four lectures don't overlap. Scoping is by
    *relation*, not by year: HISTORY narrates the seed's **references**,
    EVOLUTION ("The landmark papers since") the **landmark citers**,
    and FRONTIER the recent **Latest Publications** — each keeping only nodes
    carrying that ``rels`` tag (plus the seed itself), then sorted
    chronologically (see ``_chronological``). INTUITION stays on the **seed
    alone**, so it structurally can't wander onto another paper. BRIDGE sees
    the whole visible set.

    Args:
        seed: The seed paper (always included in every mode's set).
        nodes: The visible graph nodes.
        mode: The lecture mode being narrated.

    Returns:
        The mode-scoped node list to hand the lecturer.
    """
    if mode is LectureMode.INTUITION:
        return [node for node in nodes if node.is_seed or node.id == seed.id]
    relation = _MODE_RELATION.get(mode)
    if relation is None:  # BRIDGE (and any future non-directional mode)
        return list(nodes)
    return _chronological(
        [
            node
            for node in nodes
            if node.is_seed or node.id == seed.id or relation in node.rels
        ]
    )


def run(
    intent: Intent,
    *,
    question: str | None = None,
    seed: Node | None = None,
    nodes: list[Node] | None = None,
    mode: LectureMode = LectureMode.HISTORY,
    target: Node | None = None,
    history: list[dict] | None = None,
    source_ids: list[str] | None = None,
    lectures: list[PlayedLecture] | None = None,
    provider: Provider = "s2",
) -> Iterator[events.Event]:
    """Run one teacher workflow, yielding its full event stream.

    Args:
        intent: Which workflow — see ``models.Intent``.
        question: The user's question (research only).
        seed: The seed paper — required for a lecture, optional for research
            (absent = the graph-free chat).
        nodes: The visible graph nodes — same requirement as ``seed``.
        mode: The lecture mode (lecture only).
        target: The bridge target paper (lecture only, bridge mode).
        history: Prior conversation turns (research only; the routes layer
            keeps one store per chat surface and owns persistence).
        source_ids: Library scope (research only).
        lectures: Lectures already delivered this session (research only) —
            extra grounding so the answer builds on them instead of repeating.
        provider: The graph's academic-data provider (research only) — the
            researcher's expand/search/hydrate follow it.

    Yields:
        The workflow's typed events, then exactly one ``Done`` on success or
        ``Error`` on failure — always the last event, whatever happens.
    """
    try:
        if intent is Intent.LECTURE:
            if seed is None or nodes is None:
                yield events.Error(message="lecture needs a seed and the visible nodes")
                return
            # A lecture never expands the graph — every mode narrates only
            # nodes the user can see (only the researcher, on explicit Q&A,
            # may pull new papers in) — and each mode is pinned to one graph
            # relation: history=references, evolution=landmark citers,
            # frontier=latest; intuition stays on the seed alone.
            yield from lecturer.lecture(seed, _story_nodes(seed, nodes, mode), mode, target)
        elif intent is Intent.RESEARCH:
            if question is None:
                yield events.Error(message="research needs a question")
                return
            # seed/nodes are optional since v6.7.0: without them this is the
            # graph-free chat the librarian used to serve, run by the same
            # agent with an empty numbered list.
            yield from researcher.answer(
                question, seed, nodes, history, source_ids, lectures, provider
            )
        else:
            yield events.Error(message=f"unknown intent {intent!r}")
            return
    except Exception as exc:
        log.exception("%s workflow failed", intent)
        yield events.Error(message=str(exc))
        return
    yield events.Done()
