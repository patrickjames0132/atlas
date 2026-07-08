"""The orchestrator: one entry point for every teacher workflow.

Routes call ``run(intent, ...)`` with the UI's intent hint and get back the
full typed event stream, always terminated by ``Done`` or ``Error`` — this
is the one place that contract is enforced, so the frontend never hangs on
a dead stream. Known intents dispatch deterministically per the playbooks
in ``skills/workflows/``:

* ``lecture``   — delegation to ``lecturer.lecture``. A lecture narrates
  the graph *as the user sees it* — it never expands nodes (that's the
  researcher's job, on explicit questions). Modes are scoped by
  ``_story_nodes``: history ends AT the seed, evolution starts from it,
  frontier keeps only the last ~12 months (the leading edge); intuition and
  bridge see the whole visible set.
* ``research``  — pure delegation to ``researcher.answer``.
* ``librarian`` — pure delegation to ``librarian.answer``.

**No model lives here yet — deliberately.** The locked design is hybrid
(deterministic dispatch for known intents, the orchestrator's own model
engaging only for ambiguous or multi-step asks), but every current entry
point passes a known intent, so building the Agent now would be speculative
LLM plumbing — the same call as the query-expansion seam in Phase 3. When a
free-form entry point exists in the UI, the model half lands here.
"""

from __future__ import annotations

import datetime
import logging
from typing import Iterator

from ...services.graph import Node
from .. import events, lecturer, librarian, researcher
from ..models import Intent, LectureMode

log = logging.getLogger(__name__)

# The current-frontier lecture's recency window. Matches the `latest` citation
# relation's window (semantic_scholar traversal `_LATEST_WINDOW_MONTHS`) so the
# frontier the lecture narrates lines up with the light-green `latest` nodes.
_FRONTIER_WINDOW_MONTHS = 12


def _is_recent(node: Node, cutoff_iso: str, min_year: int) -> bool:
    """Whether a node falls in the current-frontier window — by ``pub_date`` at
    or after ``cutoff_iso``, or (lacking a pub_date) by ``year >= min_year``."""
    if node.pub_date:
        return node.pub_date >= cutoff_iso
    return node.year is not None and node.year >= min_year


def _story_nodes(seed: Node, nodes: list[Node], mode: LectureMode) -> list[Node]:
    """The node set a lecture mode may narrate.

    A lecture never expands the graph — but a mode also shouldn't wander onto
    the wrong part of the story. HISTORY tells the story *up to* the seed, so it
    only sees the seed plus papers published in or before the seed's year;
    EVOLUTION tells the story *since* it (in or after). FRONTIER stays at the
    leading edge: the seed plus only papers from the last
    ``_FRONTIER_WINDOW_MONTHS`` (any relation — so recent citations AND recent
    similar work), scoped by absolute recency, not relative to the seed.
    INTUITION and BRIDGE see everything. Undated papers are left out of the
    year-clamped directional modes — they can't be placed in a chronological
    story. No seed year -> no history/evolution clamp (frontier still applies).

    Args:
        seed: The seed paper (its year anchors the history/evolution clamp).
        nodes: The visible graph nodes.
        mode: The lecture mode being narrated.

    Returns:
        The (possibly narrowed) node list to hand the lecturer.
    """
    if mode is LectureMode.FRONTIER:
        today = datetime.date.today()
        months = today.year * 12 + (today.month - 1) - _FRONTIER_WINDOW_MONTHS
        cutoff = f"{months // 12:04d}-{months % 12 + 1:02d}-{today.day:02d}"
        return [
            node
            for node in nodes
            if node.is_seed or node.id == seed.id or _is_recent(node, cutoff, today.year - 1)
        ]
    if seed.year is None or mode not in (LectureMode.HISTORY, LectureMode.EVOLUTION):
        return list(nodes)
    backward = mode is LectureMode.HISTORY
    return [
        node
        for node in nodes
        if node.is_seed
        or node.id == seed.id
        or (
            node.year is not None
            and (node.year <= seed.year if backward else node.year >= seed.year)
        )
    ]


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
) -> Iterator[events.Event]:
    """Run one teacher workflow, yielding its full event stream.

    Args:
        intent: Which workflow — see ``models.Intent``.
        question: The user's question (research and librarian).
        seed: The seed paper (lecture and research).
        nodes: The visible graph nodes (lecture and research).
        mode: The lecture mode (lecture only).
        target: The bridge target paper (lecture only, bridge mode).
        history: Prior conversation turns (research and librarian — separate
            stores; routes own persistence).
        source_ids: Library scope (research and librarian).

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
            # may pull new papers in) — and the directional modes are scoped
            # to their side of the seed: history ends AT the seed, evolution
            # starts from it.
            yield from lecturer.lecture(seed, _story_nodes(seed, nodes, mode), mode, target)
        elif intent is Intent.RESEARCH:
            if question is None or seed is None or nodes is None:
                yield events.Error(message="research needs a question, a seed, and the visible nodes")
                return
            yield from researcher.answer(question, seed, nodes, history, source_ids)
        elif intent is Intent.LIBRARIAN:
            if question is None:
                yield events.Error(message="librarian needs a question")
                return
            yield from librarian.answer(question, history, source_ids)
        else:
            yield events.Error(message=f"unknown intent {intent!r}")
            return
    except Exception as exc:
        log.exception("%s workflow failed", intent)
        yield events.Error(message=str(exc))
        return
    yield events.Done()
