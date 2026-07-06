"""The orchestrator: one entry point for every teacher workflow.

Routes call ``run(intent, ...)`` with the UI's intent hint and get back the
full typed event stream, always terminated by ``Done`` or ``Error`` — this
is the one place that contract is enforced, so the frontend never hangs on
a dead stream. Known intents dispatch deterministically per the playbooks
in ``skills/workflows/``:

* ``lecture``   — history mode runs the ``backfill`` walk first (its
  discoveries stream out AND enrich the node set the lecturer narrates),
  then delegates to ``lecturer.lecture``.
* ``q&a``       — pure delegation to ``tutor.answer``.
* ``librarian`` — pure delegation to ``librarian.answer``.

**No model lives here yet — deliberately.** The locked design is hybrid
(deterministic dispatch for known intents, the orchestrator's own model
engaging only for ambiguous or multi-step asks), but every current entry
point passes a known intent, so building the Agent now would be speculative
LLM plumbing — the same call as the query-expansion seam in Phase 3. When a
free-form entry point exists in the UI, the model half lands here.
"""

from __future__ import annotations

import logging
from typing import Iterator, Literal

from ...services.graph import Node
from .. import events, lecturer, librarian, tutor
from ..lecturer.main import Mode
from . import backfill

log = logging.getLogger(__name__)

Intent = Literal["lecture", "q&a", "librarian"]


def run(
    intent: Intent,
    *,
    question: str | None = None,
    seed: Node | None = None,
    nodes: list[Node] | None = None,
    mode: Mode = "history",
    target: Node | None = None,
    history: list[dict] | None = None,
    source_ids: list[str] | None = None,
) -> Iterator[events.Event]:
    """Run one teacher workflow, yielding its full event stream.

    Args:
        intent: Which workflow — ``lecture``, ``q&a``, or ``librarian``.
        question: The user's question (q&a and librarian).
        seed: The seed paper (lecture and q&a).
        nodes: The visible graph nodes (lecture and q&a).
        mode: The lecture mode (lecture only).
        target: The bridge target paper (lecture only, bridge mode).
        history: Prior conversation turns (q&a and librarian — separate
            stores; routes own persistence).
        source_ids: Library scope (q&a and librarian).

    Yields:
        The workflow's typed events, then exactly one ``Done`` on success or
        ``Error`` on failure — always the last event, whatever happens.
    """
    try:
        if intent == "lecture":
            if seed is None or nodes is None:
                yield events.Error(message="lecture needs a seed and the visible nodes")
                return
            work_nodes = list(nodes)
            if mode == "history":
                # Backfill discoveries stream to the frontend AND join the
                # node set, so the lecturer can narrate the found ancestors.
                for event in backfill.history_backfill(seed, work_nodes):
                    if isinstance(event, events.Discovery):
                        work_nodes.extend(event.nodes)
                    yield event
            yield from lecturer.lecture(seed, work_nodes, mode, target)
        elif intent == "q&a":
            if question is None or seed is None or nodes is None:
                yield events.Error(message="q&a needs a question, a seed, and the visible nodes")
                return
            yield from tutor.answer(question, seed, nodes, history, source_ids)
        elif intent == "librarian":
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
