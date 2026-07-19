"""The librarian: graph-free RAG chat over the user's own uploaded library.

Retrieve-then-answer: the most relevant passages are fetched
deterministically (hybrid FTS5 + vector search) *before* the model is
engaged, then one streamed completion answers grounded only in them,
attributing inline by title and page. No graph, no searches — the
lightweight "just ask my books" path — but since v5.28.0 it carries **one
tool**, ``show_source_figure``, so an answer can attach real figures from
the user's uploaded PDFs (the researcher's library twin, same ``<<FIG n>>``
marker contract).

The tool forced two structural changes, both borrowed from the researcher:
the run is driven through the shared event bridge (``streams.drive``) so
``Figure``/``FigureTrace`` events flow out live between text deltas, and the
output became a structured ``Reply`` streamed from the output tool's partial
JSON — a model narrates its tool turns ("let me pull that figure…"), and
with plain-text output that narration would stream as answer prose
(PydanticAI marks the first text part as the provisional final result even
when tool calls follow). Structured output ignores everything outside the
final result, which is the house pattern.

Empty retrieval is an answer, not an error: a friendly no-hits line streams
back without the model ever running. Real failures (model, database)
propagate — the caller ends the event stream with ``Error``.
"""

from __future__ import annotations

from typing import Iterator

from pydantic import BaseModel, ConfigDict
from pydantic_ai import Agent, Tool
from pydantic_ai.messages import PartDeltaEvent, PartStartEvent, ToolCallPart, ToolCallPartDelta
from pydantic_ai.run import AgentRunResultEvent

from ...config import config
from ...services import sources
from .. import events, factory, prompts, streams
from .config import AGENT_ID, NO_HITS_ANSWER, SKILLS, SYSTEM_PROMPT
from .tools import LibrarianDeps, make_deps, show_source_figure


class Reply(BaseModel):
    """The librarian's structured final result: just the answer prose.

    One field on purpose — the structure isn't for data, it's for the
    narration-vs-answer boundary (see the module docstring).
    """

    model_config = ConfigDict(extra="forbid")

    text: str


agent: Agent[LibrarianDeps, Reply] = Agent(
    factory.build_model(AGENT_ID),
    deps_type=LibrarianDeps,
    output_type=Reply,
    instructions=[SYSTEM_PROMPT, *(prompts.skill(name) for name in SKILLS)],
    tools=[Tool(show_source_figure, sequential=True)],
)


def _hit_titles(hits: list[dict]) -> list[str]:
    """Distinct source titles among retrieved passages, first-seen order —
    surfaced in the retrieval trace so the chat can show what it drew on.

    Args:
        hits: Passage dicts from ``services.sources.search``.

    Returns:
        The distinct ``source_title`` values.
    """
    seen: set[str] = set()
    titles: list[str] = []
    for hit in hits:
        title = hit.get("source_title")
        if title and title not in seen:
            seen.add(title)
            titles.append(title)
    return titles


def _hit_source_lines(hits: list[dict]) -> str:
    """An id → title map of the sources behind the retrieved passages, so the
    model can address ``show_source_figure`` (passages cite by title+page;
    the tool wants the id).

    Args:
        hits: Passage dicts from ``services.sources.search``.

    Returns:
        One ``- [id] "Title"`` line per distinct source, first-seen order.
    """
    seen: set[str] = set()
    lines: list[str] = []
    for hit in hits:
        source_id = hit.get("source_id")
        if source_id and source_id not in seen:
            seen.add(source_id)
            lines.append(f'- [{source_id}] "{hit.get("source_title", "")}"')
    return "\n".join(lines)


def answer(
    question: str,
    history: list[dict] | None = None,
    source_ids: list[str] | None = None,
) -> Iterator[events.Event]:
    """Answer a question purely from the user's local library — no graph.

    Args:
        question: The user's question (doubles as the retrieval query).
        history: Prior turns as ``[{role, content}, ...]``; malformed turns
            are skipped.
        source_ids: Scope retrieval to these source ids. ``None`` means no
            scope — the whole library; an explicit empty list means "no
            sources selected" — retrieval finds nothing.

    Yields:
        One ``RetrievalTrace`` naming what was found, then ``Token`` prose
        interleaved with any ``FigureTrace``/``Figure`` events the
        show_source_figure tool emits — or the canned no-hits line when
        retrieval came up empty (the model is never engaged for that).

    Raises:
        Exception: Model/stream failures propagate — the caller ends the
            event stream with ``Error``. (Tool-level failures don't raise;
            they come back to the model as text it steers by.)
        sqlite3.Error: On library database failures during retrieval.
    """
    hits = sources.search(
        question, top_k=config.sources.retrieval.chat_k, source_ids=source_ids
    )
    yield events.RetrievalTrace(found=len(hits), sources=_hit_titles(hits))
    if not hits:
        yield events.Token(text=NO_HITS_ANSWER)
        return

    prompt = (
        f"Passages from your library:\n\n{prompts.format_passages(hits)}\n\n"
        f"Their sources (for show_source_figure):\n{_hit_source_lines(hits)}\n\n"
        f"Question: {question}"
    )
    deps = make_deps()

    final: Reply | None = None
    emitted = ""  # answer prose already yielded as Token events
    args_buffer = ""  # the output tool call's JSON args, accumulated
    output_part: int | None = None  # stream index of the output tool call

    stream = streams.drive(
        agent, prompt, deps=deps, message_history=prompts.history(history)
    )
    for event in stream:
        yield from deps.drain()
        answer_grew = False
        if isinstance(event, PartStartEvent) and isinstance(event.part, ToolCallPart):
            if event.part.tool_name == streams.OUTPUT_TOOL:
                output_part = event.index
                args = event.part.args
                args_buffer = args if isinstance(args, str) else ""
                answer_grew = True
        elif (
            isinstance(event, PartDeltaEvent)
            and event.index == output_part
            and isinstance(event.delta, ToolCallPartDelta)
            and isinstance(event.delta.args_delta, str)
        ):
            args_buffer += event.delta.args_delta
            answer_grew = True
        elif isinstance(event, AgentRunResultEvent):
            final = event.result.output
        if answer_grew:
            grown = streams.partial_text(args_buffer)
            if len(grown) > len(emitted):
                yield events.Token(text=grown[len(emitted) :])
                emitted = grown

    yield from deps.drain()
    if final is not None:
        remainder = final.text[len(emitted) :]
        if remainder:
            yield events.Token(text=remainder)
