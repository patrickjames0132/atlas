"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
The researcher: agentic Q&A over the graph — read, expand, search, then answer.

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

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

import logging
from typing import Iterator, Literal

from pydantic import BaseModel, ConfigDict
from pydantic_ai import Agent, Tool, UsageLimits
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.messages import (
    PartDeltaEvent,
    PartStartEvent,
    ToolCallPart,
    ToolCallPartDelta,
)
from pydantic_ai.run import AgentRunResultEvent
from pydantic_ai.tools import RunContext, ToolDefinition

from ....services.graph import Node, Provider
from ....services.sources import store
from ... import events, factory, prompts, streams
from ...models import PlayedLecture
from .config import AGENT_ID, BUDGETS, SKILLS, SYSTEM_PROMPT
from .tools import (
    ResearcherDeps,
    expand_node,
    read_paper,
    search_papers,
    search_sources,
    show_figure,
    show_source_figure,
)

log = logging.getLogger(__name__)


class Answer(BaseModel):
    """The researcher's structured final result: the prose and its citations.

    ``cited`` holds numbered-list indices (the model never sees node ids) —
    mapped to ids and merged with the papers it actually read on the way out.

    ``kind`` exists for **enforcement, not provenance**. It says whether this
    turn was a substantive answer or just conversation ("hi", "thanks", "what
    can you do?"), which is what ``_must_have_looked`` needs to decide whether
    skipping the library was legitimate. It deliberately does *not* say where
    the answer's knowledge came from: real teaching answers are mixed (the
    book supplies the objective, recall supplies the background it assumes),
    so a turn-level provenance label would misreport the common case in both
    directions. Provenance is derived instead — see ``_provenance``.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["conversational", "answered"]
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
# Library figures ride the same gate: no library, no tool.
_show_source_figure_tool: Tool[ResearcherDeps] = Tool(
    show_source_figure, prepare=_if_sources, sequential=True
)

# sequential=True everywhere: PydanticAI runs a turn's tool calls
# concurrently by default, but these tools mutate shared deps state —
# budgets, and above all the numbered list, whose indices must be assigned
# in call order.
#: What the model is told when it answered substantively without ever
#: consulting a library it had. Phrased as an instruction, not a scolding —
#: it's a retry prompt, and the next attempt has to know what to do.
_MUST_SEARCH_RETRY = (
    "You answered without searching the student's library. Their own uploaded "
    "sources may cover this, and an answer that ignores the textbook they "
    "uploaded is a worse answer. Call search_sources first, then answer — "
    "drawing on what it returns where it speaks to the question, and saying "
    "so plainly if it doesn't. (If this turn was only conversational, set "
    "kind to 'conversational' instead.)"
)


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
        _show_source_figure_tool,
    ],
)


@agent.output_validator
def _must_have_looked(ctx: RunContext[ResearcherDeps], output: Answer) -> Answer:
    """Reject a substantive answer that never consulted an available library.

    This is what replaces the librarian's grounding-by-construction. When
    retrieval ran *before* the model, the model could not answer without the
    passages in front of it; as a tool it can simply not call it and answer
    from memory, and the student will reasonably believe the answer came from
    their book. Prompting alone is known to be insufficient here — the agent
    already skips ``show_figure`` when asked outright — so the guard is
    structural: an ``answered`` turn that never reached retrieval is bounced
    back for another attempt.

    Two deliberate limits. It asks whether the library was **consulted**, not
    whether it *helped*: a search returning nothing still satisfies it, or an
    empty library would make every answer unreachable. And it never fires
    without a library — there is nothing to look in, and ``search_sources``
    isn't even registered.

    Args:
        ctx: The run context carrying the researcher's deps.
        output: The model's structured answer.

    Returns:
        The answer unchanged, when the guard is satisfied.

    Raises:
        ModelRetry: When a substantive answer skipped an available library.
    """
    deps = ctx.deps
    if output.kind == "answered" and deps.has_sources and deps.source_searches_run == 0:
        raise ModelRetry(_MUST_SEARCH_RETRY)
    return output


def _doomed(args_buffer: str, deps: ResearcherDeps) -> bool:
    """Whether the in-flight answer is one ``_must_have_looked`` will bounce.

    The guard can only run once the output tool call is complete — by which
    point, without this, the whole rejected answer would already have streamed
    to the student, only to be replaced by the retry. So the same condition is
    evaluated *while* the args stream and prose is withheld until the attempt
    is known-good. Streaming therefore implies acceptance: the two predicates
    are identical, and no tool runs between them to change the answer.

    Reading ``kind`` out of partial JSON is safe on one character, because the
    two values disagree at the first: ``a``nswered vs ``c``onversational. An
    empty read means it hasn't arrived — hold, don't guess. (If a model ever
    emits ``text`` before ``kind``, this degrades to buffering the answer and
    flushing it whole, which is slower but never wrong.)

    Args:
        args_buffer: The output tool call's JSON args accumulated so far.
        deps: The run's deps, for the observed search count.

    Returns:
        True while this attempt would be rejected, so its prose must be held.
    """
    if not (deps.has_sources and deps.source_searches_run == 0):
        return False  # nothing to violate — no library, or it already looked
    return not streams.partial_text(args_buffer, "kind").startswith("c")


def _library_context(library: list[dict]) -> str:
    """The "Your library" listing so the model knows what it can search, can
    scope search_sources by number, and can cite passages by ``[Sn, p.N]``.

    Args:
        library: The user's sources, in display order.

    Returns:
        The numbered listing, headed by what the numbers are for.
    """
    return (
        "Your library (search with search_sources; attach a cited page's "
        "figure with show_source_figure; cite a passage by its [Sn, p.N] "
        "marker):\n" + prompts.source_lines(library)
    )


# How much of the already-played lectures to fold into the prompt. Bounded so a
# full set of four lectures (7–12 beats each) can't blow the context — the
# earliest lectures fit whole, then the block is truncated once the budget runs
# out. It's grounding the model MAY lean on, not a required read.
_LECTURES_MAX_CHARS = 6000


def _lectures_context(lectures: list[PlayedLecture]) -> str:
    """The lectures already delivered this session, as a compact prompt block.

    Each lecture becomes a titled list of its beats (``heading: text``), joined
    under a header that tells the model to build on them rather than repeat
    them. Bounded by ``_LECTURES_MAX_CHARS`` — lectures are added whole until the
    budget runs out, then the overflowing one is truncated and the rest dropped
    (the student saw the earliest-played first, so that ordering is preserved).

    Args:
        lectures: The played lectures, in the order they were delivered.

    Returns:
        The formatted block, or an empty string when there are no lectures.
    """
    blocks: list[str] = []
    budget = _LECTURES_MAX_CHARS
    for lecture in lectures:
        lines = [f"## {lecture.title}"]
        for beat in lecture.beats:
            heading = beat.heading.strip()
            text = beat.text.strip()
            lines.append(f"- {heading}: {text}" if heading else f"- {text}")
        block = "\n".join(lines)
        if len(block) > budget:
            blocks.append(block[:budget].rstrip() + " …")
            break
        blocks.append(block)
        budget -= len(block)
    return "\n\n".join(blocks)


def _prompt(
    seed: Node | None,
    nodes: list[Node],
    library: list[dict],
    question: str,
    lectures: list[PlayedLecture],
) -> str:
    """Assemble the question turn: grounding context + the question.

    Args:
        seed: The seed paper (heads the grounding context), or None when no
            graph is open — the graph-free chat that replaced the librarian.
        nodes: The visible graph nodes, as the numbered grounding list. Empty
            in graph-free mode; ``search_papers`` can still fill it.
        library: The user's source library (listed so the model can scope
            search_sources); empty when there is none.
        question: The user's question.
        lectures: Lectures already delivered this session — folded in as extra
            context the answer may build on; empty when none have played.

    Returns:
        The full user prompt.
    """
    if seed is not None:
        context = (
            f"SEED paper: {seed.title}\n\n"
            f"Papers on the graph (numbered):\n{prompts.node_lines(nodes)}"
        )
    else:
        # Graph-free: no seed, no numbered papers yet. search_papers still
        # works and numbers what it finds, so the list starts empty rather
        # than being absent — this is the researcher with an empty graph.
        # An earlier version told the model to prefer its own knowledge here
        # and search only as a last resort. That was an attempt to make the
        # graph-free chat behave like a general assistant, and it was both
        # unenforceable (a soft prompt rule against an always-available tool)
        # and off-mission: Atlas grounds answers in papers and the student's
        # own material. Reaching for the literature with no graph open is the
        # right instinct, not one to suppress.
        context = (
            "No citation graph is open — the student is asking outside any "
            "paper neighborhood. There are no numbered papers yet; "
            "search_papers can find some and they'll be numbered as they "
            "arrive, and can be cited [n] as usual."
        )
    if library:
        context += "\n\n" + _library_context(library)
    if lectures:
        context += (
            "\n\nLectures already delivered to the student this session — build on "
            "them and refer back to them where relevant; don't re-derive or repeat "
            "a lecture wholesale:\n" + _lectures_context(lectures)
        )
    return f"{context}\n\nQuestion: {question}"


def answer(
    question: str,
    seed: Node | None = None,
    nodes: list[Node] | None = None,
    history: list[dict] | None = None,
    source_ids: list[str] | None = None,
    lectures: list[PlayedLecture] | None = None,
    provider: Provider = "s2",
) -> Iterator[events.Event]:
    """Answer a question agentically: read / expand / search via tool use.

    Args:
        question: The user's question.
        seed: The seed paper (heads the grounding context), or None for the
            graph-free chat — asking straight over the library, with no
            neighborhood open. Both halves of the same agent since v6.7.0;
            the librarian that used to own this path is gone.
        nodes: The visible graph nodes — the initial numbered list; grows as
            the agent expands and searches. None/empty in graph-free mode.
        history: Prior turns as ``[{role, content}, ...]``; malformed turns
            are skipped.
        source_ids: User-selected library scope. ``None`` = no scope (the
            whole library); a present list pins context and every source
            search to exactly those; an empty list disables source search.
        lectures: Lectures already delivered this session (from the frontend's
            transcript cache) — folded into the prompt as context the answer
            may build on, so it doesn't re-derive a lecture the student saw.
            ``None``/empty when no lecture has played.
        provider: The graph's academic-data provider (``s2`` / ``openalex``) —
            expand_node, search_papers, and lazy detail hydration follow it, so
            the agent stays in the same backend (and id space) as the graph.

    Yields:
        One ``SourceRefs`` up front when a library is in play, then ``Trace``
        / ``Discovery`` / ``Figure`` events live as the agent works, then
        ``Token`` deltas of the answer prose, and finally ``Cited`` — the
        papers it read plus any it named, as node ids — and ``Provenance``,
        the observed record of what actually grounded the answer.

    Raises:
        Exception: Model/stream failures propagate — the caller ends the
            event stream with ``Error``. (Tool-level failures don't raise;
            they come back to the model as text it steers by.)
    """
    library = store.list_sources()
    if source_ids is not None:
        wanted = set(source_ids)
        library = [source for source in library if source.get("id") in wanted]

    graph_nodes = list(nodes or [])
    deps = ResearcherDeps(
        nodes=graph_nodes,
        known_ids={node.id for node in graph_nodes},
        scope=source_ids,
        # No availability probe: retrieval degrades by itself (lexical-only
        # without the embedder), so an existing library is enough — and an
        # empty one never pays the torch load.
        has_sources=bool(library),
        sources=library,
        provider=provider,
        steps_left=BUDGETS["max_steps"],
        full_reads_left=BUDGETS["full_reads"],
        summary_reads_left=BUDGETS["summary_reads"],
        hops_left=BUDGETS["hops"],
        searches_left=BUDGETS["searches"],
        source_searches_left=BUDGETS["source_searches"],
        figures_left=BUDGETS["figures"],
    )

    # The numbered library, resolved up front (the map is page-free) so every
    # [Sn, p.N] marker renders as a real title the moment it streams in.
    if library:
        yield events.SourceRefs(
            refs={
                key: events.SourceRef(**ref)
                for key, ref in prompts.source_refs(library, "").items()
            }
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
        _prompt(seed, deps.nodes, library, question, lectures or []),
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
        if answer_grew and not _doomed(args_buffer, deps):
            grown = streams.partial_text(args_buffer)
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
    # The papers the prose actually names, resolved to title + URL. With a
    # graph the frontend resolves [n] itself and this is redundant; with none
    # it's the only thing standing between the reader and a dead marker.
    paper_refs = prompts.paper_refs(deps.nodes, final.text, deps.provider)
    if paper_refs:
        yield events.PaperRefs(
            refs={key: events.PaperRef(**ref) for key, ref in paper_refs.items()}
        )
    # Logged as well as streamed: a mislabelled turn is the one failure the
    # output guard cannot catch (it only fires on `answered`), so the
    # classification needs to be greppable in data/atlas.log after the fact.
    log.info(
        "answer kind=%s library=%s searches=%d passages=%d paper_searches=%d",
        final.kind,
        deps.has_sources,
        deps.source_searches_run,
        deps.source_hits,
        deps.paper_searches_run,
    )
    yield events.Provenance(
        kind=final.kind,
        had_library=deps.has_sources,
        searches=deps.source_searches_run,
        passages=deps.source_hits,
        paper_searches=deps.paper_searches_run,
        # Counted off the finished prose, not claimed: which [Sn] markers the
        # answer actually kept, and which papers it cites.
        cited_sources=len(prompts.source_refs(deps.sources, final.text)),
        cited_papers=len(cited),
    )
