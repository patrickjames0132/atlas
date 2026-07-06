"""The lecturer: a streamed lecture over the visible graph, in typed beats.

The model produces a ``list[LectureBeat]`` as structured output — heading,
one tight narration paragraph, and the numbered-list indices to light up.
Streaming partial validation lets each beat surface as soon as the model
starts the next one, so the frontend reveals the story beat-by-beat without
waiting for the whole lecture. This replaces the old newline-delimited-JSON
protocol and its fence-stripping parser outright: the shape is enforced by
Pydantic, not begged for in the prompt.

Mode picks the story (``history`` / ``intuition`` / ``bridge``); in history
mode the orchestrator runs its ``history_backfill`` tool first and passes the
ancestor-enriched node set in. Model failures propagate — the caller ends the
event stream with ``Error``.
"""

from __future__ import annotations

from typing import Iterator, Literal

from pydantic import BaseModel, ConfigDict
from pydantic_ai import Agent

from ...services.graph import Node
from .. import events, factory, prompts
from .config import AGENT_ID, MODE_INTENTS, SKILLS, SYSTEM_PROMPT

Mode = Literal["history", "intuition", "bridge"]


class LectureBeat(BaseModel):
    """One beat as the model emits it: numbered-list indices, not node ids
    (the model never sees ids — ``prompts.idx_to_id`` maps them back)."""

    model_config = ConfigDict(extra="forbid")

    heading: str
    text: str
    nodes: list[int]


agent: Agent[None, list[LectureBeat]] = Agent(
    factory.build_model(AGENT_ID),
    output_type=list[LectureBeat],
    instructions=[SYSTEM_PROMPT, *(prompts.skill(name) for name in SKILLS)],
)


def _prompt(seed: Node, nodes: list[Node], mode: Mode, target: Node | None) -> str:
    """Assemble the lecture request: mode intent, seed/target header, and the
    numbered paper list.

    Args:
        seed: The seed paper.
        nodes: The visible graph nodes, in display order.
        mode: Which story to tell.
        target: The bridge target (bridge mode only), or None.

    Returns:
        The full user prompt.
    """
    header = f"SEED paper: {seed.title}"
    if mode == "bridge" and target:
        header += f"\nTARGET paper: {target.title}"
    return (
        f"{MODE_INTENTS[mode]}\n\n"
        f"{header}\n\n"
        f"Papers on the graph (numbered):\n{prompts.node_lines(nodes)}\n\n"
        f"Now deliver the lecture."
    )


def _beat(beat: LectureBeat, nodes: list[Node]) -> events.Beat:
    """Convert a model beat to the event the frontend consumes (indices
    mapped back to node ids)."""
    return events.Beat(
        heading=beat.heading.strip(),
        text=beat.text.strip(),
        node_ids=prompts.idx_to_id(nodes, beat.nodes),
    )


def lecture(
    seed: Node,
    nodes: list[Node],
    mode: Mode = "history",
    target: Node | None = None,
) -> Iterator[events.Beat]:
    """Stream a lecture over the visible graph as typed beats.

    Args:
        seed: The seed paper.
        nodes: The visible graph nodes (in history mode, already enriched
            with the orchestrator's backfilled ancestors).
        mode: ``history``, ``intuition``, or ``bridge``.
        target: The bridge target paper (bridge mode only), or None.

    Yields:
        ``events.Beat`` per beat, as soon as each is complete — a beat is
        final once the model starts the next one, so narration begins before
        the lecture ends. Beats with blank text are dropped.

    Raises:
        Exception: Model/stream failures propagate — the caller ends the
            event stream with ``Error``.
    """
    result = agent.run_stream_sync(_prompt(seed, nodes, mode, target))
    emitted = 0
    for partial in result.stream_output():
        # The last element may still be mid-generation under partial
        # validation; everything before it is closed and safe to emit.
        for beat in partial[emitted : len(partial) - 1]:
            if beat.text.strip():
                yield _beat(beat, nodes)
        emitted = max(emitted, len(partial) - 1)
    for beat in result.get_output()[emitted:]:
        if beat.text.strip():
            yield _beat(beat, nodes)
