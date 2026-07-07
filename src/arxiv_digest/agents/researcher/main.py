"""The researcher: agentic Q&A over the graph — read, expand, search, then answer.

The flagship workflow. The model gets tools (``tools.py``) and a run-state
deps object; it investigates until it has enough, then produces a structured
``Answer`` whose ``text`` streams as it's generated and whose ``cited`` field
replaces the old ``<<CITED>>`` sentinel outright (no hold-back streaming, no
``discard`` events — narration text parts before a tool call are simply
never emitted).

The event bridge is the one piece with real machinery: PydanticAI's
``run_stream_events`` is async-only, so ``answer`` drives it one event at a
time on a private event loop, draining the deps event queue (traces,
discoveries, figures pushed by tools) between run events and decoding the
final answer's streamed tool-call args into ``Token`` deltas via partial
JSON parsing.
"""

from __future__ import annotations

from typing import Iterator

from pydantic import BaseModel, ConfigDict
from pydantic_ai import Agent, Tool, UsageLimits
from pydantic_ai.messages import (
    PartDeltaEvent,
    PartStartEvent,
    ToolCallPart,
    ToolCallPartDelta,
)
from pydantic_ai.run import AgentRunResultEvent
from pydantic_ai.tools import RunContext, ToolDefinition
from pydantic_core import from_json

from ...services.graph import Node
from ...services.sources import store
from .. import events, factory, prompts, streams
from .config import AGENT_ID, BUDGETS, SKILLS, SYSTEM_PROMPT
from .tools import (
    ResearcherDeps,
    expand_node,
    read_paper,
    search_papers,
    search_sources,
    show_figure,
)


class Answer(BaseModel):
    """The researcher's structured final result: the prose and its citations.

    ``cited`` holds numbered-list indices (the model never sees node ids) —
    mapped to ids and merged with the papers it actually read on the way out.
    """

    model_config = ConfigDict(extra="forbid")

    text: str
    cited: list[int]


async def _if_sources(
    ctx: RunContext[ResearcherDeps], tool_def: ToolDefinition
) -> ToolDefinition | None:
    """Offer search_sources only when the user actually has a library."""
    return tool_def if ctx.deps.has_sources else None


# The explicit annotation is load-bearing: with the prepare= kwarg in play,
# mypy can't jointly infer the Tool's ParamSpec without a declared target.
_search_sources_tool: Tool[ResearcherDeps] = Tool(
    search_sources, prepare=_if_sources, sequential=True
)

# sequential=True everywhere: PydanticAI runs a turn's tool calls
# concurrently by default, but these tools mutate shared deps state —
# budgets, and above all the numbered list, whose indices must be assigned
# in call order.
agent: Agent[ResearcherDeps, Answer] = Agent(
    factory.build_model(AGENT_ID),
    deps_type=ResearcherDeps,
    output_type=Answer,
    instructions=[SYSTEM_PROMPT, *(prompts.skill(name) for name in SKILLS)],
    tools=[
        Tool(read_paper, sequential=True),
        Tool(expand_node, sequential=True),
        Tool(search_papers, sequential=True),
        Tool(show_figure, sequential=True),
        _search_sources_tool,
    ],
)


def _library_context(library: list[dict]) -> str:
    """The "Your library" listing so the model knows what it can search and
    can scope search_sources by id."""
    lines = []
    for source in library:
        location = f"{source['pages']}pp" if source.get("pages") else source.get("kind", "")
        lines.append(f'- [{source["id"]}] "{source["title"]}" ({location})')
    return "Your library (search with search_sources):\n" + "\n".join(lines)


def _prompt(seed: Node, nodes: list[Node], library: list[dict], question: str) -> str:
    """Assemble the question turn: grounding context + the question."""
    context = (
        f"SEED paper: {seed.title}\n\n"
        f"Papers on the graph (numbered):\n{prompts.node_lines(nodes)}"
    )
    if library:
        context += "\n\n" + _library_context(library)
    return f"{context}\n\nQuestion: {question}"


def answer(
    question: str,
    seed: Node,
    nodes: list[Node],
    history: list[dict] | None = None,
    source_ids: list[str] | None = None,
) -> Iterator[events.Event]:
    """Answer a question agentically: read / expand / search via tool use.

    Args:
        question: The user's question.
        seed: The seed paper (heads the grounding context).
        nodes: The visible graph nodes — the initial numbered list; grows as
            the agent expands and searches.
        history: Prior turns as ``[{role, content}, ...]``; malformed turns
            are skipped.
        source_ids: User-selected library scope. ``None`` = no scope (the
            whole library); a present list pins context and every source
            search to exactly those; an empty list disables source search.

    Yields:
        ``Trace`` / ``Discovery`` / ``Figure`` events live as the agent
        works, then ``Token`` deltas of the answer prose, and finally one
        ``Cited`` — the papers it read plus any it named, as node ids.

    Raises:
        Exception: Model/stream failures propagate — the caller ends the
            event stream with ``Error``. (Tool-level failures don't raise;
            they come back to the model as text it steers by.)
    """
    library = store.list_sources()
    if source_ids is not None:
        wanted = set(source_ids)
        library = [source for source in library if source.get("id") in wanted]

    deps = ResearcherDeps(
        nodes=list(nodes),
        known_ids={node.id for node in nodes},
        scope=source_ids,
        # No availability probe: retrieval degrades by itself (lexical-only
        # without the embedder), so an existing library is enough — and an
        # empty one never pays the torch load.
        has_sources=bool(library),
        steps_left=BUDGETS["max_steps"],
        full_reads_left=BUDGETS["full_reads"],
        summary_reads_left=BUDGETS["summary_reads"],
        hops_left=BUDGETS["hops"],
        searches_left=BUDGETS["searches"],
        source_searches_left=BUDGETS["source_searches"],
        figures_left=BUDGETS["figures"],
    )

    final: Answer | None = None
    emitted = ""  # answer prose already yielded as Token events
    args_buffer = ""  # the output tool call's JSON args, accumulated
    output_part: int | None = None  # stream index of the output tool call

    # The step cap lives in the tools (each returns "answer now" once spent,
    # so the model lands the answer itself); the usage limit is only a hard
    # backstop against pathological loops, and exceeding it is an error.
    stream = streams.drive(
        agent,
        _prompt(seed, deps.nodes, library, question),
        deps=deps,
        message_history=prompts.history(history),
        usage_limits=UsageLimits(request_limit=BUDGETS["max_steps"] + 4),
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
            grown = _partial_text(args_buffer)
            if len(grown) > len(emitted):
                yield events.Token(text=grown[len(emitted) :])
                emitted = grown

    if final is None:  # pragma: no cover — the run raises before this
        raise RuntimeError("researcher run ended without a final result")
    yield from deps.drain()
    remainder = final.text[len(emitted) :]
    if remainder:
        yield events.Token(text=remainder)
    # The papers it actually read, plus any it named — reads first, order kept.
    cited = list(deps.cited_ids)
    for node_id in prompts.idx_to_id(deps.nodes, final.cited):
        if node_id not in cited:
            cited.append(node_id)
    yield events.Cited(node_ids=cited)


def _partial_text(args_json: str) -> str:
    """The ``text`` field of a partially-streamed Answer args JSON.

    ``allow_partial="trailing-strings"`` keeps the truncated tail of the
    in-flight string, so prose streams smoothly instead of buffering until
    the field closes. Undecodable/absent yields "" (nothing to emit yet).
    """
    try:
        parsed = from_json(args_json, allow_partial="trailing-strings")
    except ValueError:
        return ""
    if isinstance(parsed, dict) and isinstance(parsed.get("text"), str):
        return parsed["text"]
    return ""
