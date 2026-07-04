"""The agentic Q&A loop (Phase 3b): Claude reads the visible papers via tool use,
expands / searches for papers it needs, then answers — grounded in what it read.

Requires the Anthropic API (the ``claude`` CLI can't take our custom tools, so
the CLI backend falls back to ``qa.answer_stream``). Guardrails come from
``config.AGENT_*``: a total-step cap, per-kind read budgets, a hop budget for
expansion, a search budget, and a wall-clock ceiling. The tool schemas and
runners it drives live in ``tools.py``.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Iterator, Optional, cast

from .. import config

if TYPE_CHECKING:
    from anthropic.types import MessageParam
from ..library import sources
from .common import (
    _CITED,
    _emit_hiding_sentinel,
    _number_nodes,
    _parse_citations,
    _qa_context,
)
from .tools import (
    _SOURCE_TOOL,
    _TOOLS,
    _agent_system,
    _run_expand,
    _run_read,
    _run_search,
    _run_search_sources,
    _run_show_figure,
    _sources_context,
)


def answer_agentic(
    question: str,
    seed: dict,
    nodes: list[dict],
    history: Optional[list[dict]] = None,
    source_ids: Optional[list[str]] = None,
) -> Iterator[tuple[str, object]]:
    """Answer a question agentically: read / expand / search via tool use.

    The loop streams each model turn. Prose is emitted live while hiding the
    ``<<CITED>>`` sentinel (a held-back tail keeps a split sentinel from
    leaking); if a turn transpires to be a tool call, the streamed preamble is
    disavowed with a ``discard`` event. Tool results feed back into the
    conversation and the loop continues until the model answers, the step
    budget runs out (forcing a tool-free answer), or the wall clock passes
    ``AGENT_WALLCLOCK`` (after which turns run without tools). The
    source-search tool is offered only when the user actually has a library —
    checked before touching the embedding model, so an empty library never
    pays the torch load.

    Args:
        question: The user's question.
        seed: The seed paper (heads the grounding context).
        nodes: The visible graph nodes (the initial grounding scope; grows as
            the agent expands/searches).
        history: Prior conversation turns as ``[{role, content}, ...]``;
            malformed turns are skipped.
        source_ids: A user-selected subset of library sources to scope the
            agent's ``search_sources`` to (from the assistant panel). ``None``
            means "no scope" — the agent may search the whole library. A
            **present** list restricts context + search to exactly those
            sources, and an **empty** list ("no sources selected") disables
            source search entirely.

    Yields:
        ``("trace", {...})`` as it reads/expands/searches, ``("nodes", {...})``
        when expansion discovers papers not previously on the graph,
        ``("figure", {...})`` when it attaches a paper's figure to the answer,
        ``("token", str)`` for the streamed answer, ``("discard", None)`` when
        streamed preamble must be dropped, and one final
        ``("cited", node_ids)`` — the papers it actually read, plus any it
        named via the sentinel.

    Raises:
        anthropic.APIError: On API failures.
    """
    import anthropic
    from anthropic.types import (
        RawContentBlockDeltaEvent,
        RawContentBlockStartEvent,
        TextDelta,
        ToolUseBlock,
    )

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    numbered = _number_nodes(nodes)

    # Offer the source-search tool only when the user actually has a library
    # (checked before touching the embedding model, so an empty library never
    # pays the torch load). list_sources is cheap; available() loads the model.
    library = sources.list_sources()
    # A user-set scope (present list) pins the teacher to exactly those sources:
    # show only them in context and force every source search to them (below).
    # An explicit EMPTY scope ("no sources selected") filters the library to
    # nothing → no source tool. None means no scope → the whole library.
    if source_ids is not None:
        wanted = set(source_ids)
        library = [s for s in library if s.get("id") in wanted]
    has_sources = bool(library) and sources.available()
    tools = _TOOLS + [_SOURCE_TOOL] if has_sources else _TOOLS
    system = _agent_system(has_sources)

    messages: list[dict] = []
    for turn in history or []:
        if turn.get("role") in ("user", "assistant") and isinstance(turn.get("content"), str):
            messages.append({"role": turn["role"], "content": turn["content"]})
    context = _qa_context(seed, numbered)
    if has_sources:
        context += "\n\n" + _sources_context(library)
    messages.append({"role": "user", "content": f"{context}\n\nQuestion: {question}"})

    budgets = {"full": config.AGENT_MAX_FULL_READS, "summary": config.AGENT_MAX_SUMMARY_READS}
    read_cache: dict = {}
    known_ids = {n["id"] for n in numbered if n.get("id")}
    expanded: set[tuple[str, str]] = set()
    hops = {"left": config.AGENT_MAX_HOPS}
    searched: set = set()
    searches = {"left": config.AGENT_MAX_SEARCHES}
    source_searches = {"left": config.AGENT_MAX_SOURCE_SEARCHES}
    figs_shown: set = set()
    figures_budget = {"left": config.AGENT_MAX_FIGURES}
    cited: list[str] = []
    start = time.time()

    for _ in range(config.AGENT_MAX_STEPS):
        use_tools = (time.time() - start) < config.AGENT_WALLCLOCK
        turn_text = ""
        tool_turn = False
        emit_buf = ""  # held-back tail so a split <<CITED>> sentinel never leaks
        cut = False  # once we hit the sentinel, stop emitting this turn's prose
        hold = len(_CITED)
        with client.messages.stream(
            model=config.AGENT_MODEL,
            max_tokens=config.TEACHER_MAX_TOKENS,
            system=system,
            # Our {role, content} dicts are MessageParams; the cast just says so.
            messages=cast("list[MessageParam]", messages),
            tools=tools if use_tools else [],
        ) as stream:
            for event in stream:
                if (
                    isinstance(event, RawContentBlockStartEvent)
                    and event.content_block.type == "tool_use"
                ):
                    if not tool_turn:
                        tool_turn = True
                        emit_buf = ""  # this turn is a tool call, not the answer
                        if turn_text.strip():
                            yield ("discard", None)  # streamed preamble wasn't the answer
                elif isinstance(event, RawContentBlockDeltaEvent) and isinstance(
                    event.delta, TextDelta
                ):
                    turn_text += event.delta.text
                    if tool_turn or cut:
                        continue
                    # Stream the answer while hiding the <<CITED>> sentinel from view.
                    emit_buf += event.delta.text
                    if _CITED in emit_buf:
                        visible = emit_buf.split(_CITED, 1)[0]
                        if visible:
                            yield ("token", visible)
                        cut = True
                        emit_buf = ""
                    elif len(emit_buf) > hold:
                        out, emit_buf = emit_buf[:-hold], emit_buf[-hold:]
                        yield ("token", out)
            final = stream.get_final_message()
        # Flush the held tail once we know this turn was the spoken answer.
        if not tool_turn and not cut and emit_buf:
            yield ("token", emit_buf)

        if final.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": final.content})
            results = []
            for b in final.content:
                if not isinstance(b, ToolUseBlock):
                    continue
                if b.name == "read_paper":
                    content, trace, read_id = _run_read(b, numbered, budgets, read_cache)
                    yield ("trace", trace)
                    if read_id and read_id not in cited:
                        cited.append(read_id)
                elif b.name == "expand_node":
                    content, trace, discovery = _run_expand(b, numbered, known_ids, expanded, hops)
                    yield ("trace", trace)
                    if discovery:
                        yield ("nodes", discovery)
                elif b.name == "search_papers":
                    content, trace, discovery = _run_search(b, numbered, known_ids, searched, searches)
                    yield ("trace", trace)
                    if discovery:
                        yield ("nodes", discovery)
                elif b.name == "search_sources":
                    content, trace = _run_search_sources(b, source_searches, scope=source_ids)
                    yield ("trace", trace)
                elif b.name == "show_figure":
                    content, trace, figure = _run_show_figure(b, numbered, figs_shown, figures_budget)
                    yield ("trace", trace)
                    if figure:
                        yield ("figure", figure)
                else:
                    content = f"Unknown tool {b.name!r}."
                results.append({"type": "tool_result", "tool_use_id": b.id, "content": content})
            messages.append({"role": "user", "content": results})
            continue
        # end_turn: the answer already streamed as tokens. Fold the papers it
        # named via <<CITED>> into `cited` (so a follow-up answered from context,
        # without re-reading, still highlights the papers it drew on).
        for cid in _parse_citations(turn_text, numbered):
            if cid not in cited:
                cited.append(cid)
        yield ("cited", cited)
        return

    # Step budget spent mid-investigation — force a tool-free answer.
    messages.append({"role": "user", "content": "Answer now with what you've gathered."})
    full_box = [""]
    with client.messages.stream(
        model=config.AGENT_MODEL,
        max_tokens=config.TEACHER_MAX_TOKENS,
        system=system,
        messages=cast("list[MessageParam]", messages),
    ) as stream:
        for text in _emit_hiding_sentinel(stream.text_stream, full_box):
            yield ("token", text)
    for cid in _parse_citations(full_box[0], numbered):
        if cid not in cited:
            cited.append(cid)
    yield ("cited", cited)
