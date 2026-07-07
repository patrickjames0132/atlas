"""The lecturer: a streamed lecture over the visible graph, in typed beats.

The model produces a ``list[LectureBeat]`` as structured output — heading,
one tight narration paragraph, and the numbered-list indices to light up.
The beats stream out as the model writes them: the run is driven through
``streams.drive`` (the shared sync event bridge), the output tool's argument
JSON is partial-parsed as it grows, and each beat is emitted the moment the
model starts the next one. This replaces the old newline-delimited-JSON
protocol and its fence-stripping parser outright — the shape is enforced by
Pydantic, not begged for in the prompt.

(Why the bridge and not ``run_stream_sync().stream_output()``: the sync
convenience wrapper delivered the whole lecture in one burst at the end
against the live API — verified with frame timestamps. See ``streams.py``.)

Mode picks the story (``history`` / ``intuition`` / ``bridge``); in history
mode the orchestrator runs its ``history_backfill`` tool first and passes the
ancestor-enriched node set in. Model failures propagate — the caller ends the
event stream with ``Error``.
"""

from __future__ import annotations

from typing import Iterator

from pydantic import BaseModel, ConfigDict, ValidationError
from pydantic_ai import Agent
from pydantic_ai.messages import (
    PartDeltaEvent,
    PartStartEvent,
    ToolCallPart,
    ToolCallPartDelta,
)
from pydantic_ai.run import AgentRunResultEvent
from pydantic_core import from_json

from ...services.graph import Node
from .. import events, factory, prompts, streams
from ..models import LectureMode
from .config import AGENT_ID, MODE_INTENTS, SKILLS, SYSTEM_PROMPT


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


def _prompt(seed: Node, nodes: list[Node], mode: LectureMode, target: Node | None) -> str:
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


def _partial_beats(args_json: str) -> list[LectureBeat]:
    """Parse the beats already complete inside a partially-streamed args JSON.

    The output tool's args stream as ``{"response": [{beat}, {beat}, ...``;
    ``allow_partial`` tolerates the truncated tail, and validation stops at
    the first element that doesn't (yet) have a beat's full shape.
    """
    try:
        parsed = from_json(args_json, allow_partial="trailing-strings")
    except ValueError:
        return []
    items = parsed.get("response") if isinstance(parsed, dict) else None
    if not isinstance(items, list):
        return []
    beats: list[LectureBeat] = []
    for item in items:
        try:
            beats.append(LectureBeat.model_validate(item))
        except ValidationError:
            break  # the trailing, still-generating element
    return beats


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
    mode: LectureMode = LectureMode.HISTORY,
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
    emitted = 0
    args_buffer = ""
    output_part: int | None = None
    final: list[LectureBeat] | None = None

    def flush(beats: list[LectureBeat]) -> Iterator[events.Beat]:
        nonlocal emitted
        for beat in beats[emitted:]:
            emitted += 1
            if beat.text.strip():
                yield _beat(beat, nodes)

    for event in streams.drive(agent, _prompt(seed, nodes, mode, target)):
        if isinstance(event, PartStartEvent) and isinstance(event.part, ToolCallPart):
            if event.part.tool_name == streams.OUTPUT_TOOL:
                output_part = event.index
                args = event.part.args
                args_buffer = args if isinstance(args, str) else ""
        elif (
            isinstance(event, PartDeltaEvent)
            and event.index == output_part
            and isinstance(event.delta, ToolCallPartDelta)
            and isinstance(event.delta.args_delta, str)
        ):
            args_buffer += event.delta.args_delta
        elif isinstance(event, AgentRunResultEvent):
            final = event.result.output
            continue
        else:
            continue
        # The last parsed beat may still be mid-generation — emit up to it.
        partial = _partial_beats(args_buffer)
        yield from flush(partial[:-1])

    # The validated final output flushes whatever the partial view hadn't.
    if final is not None:
        yield from flush(final)
