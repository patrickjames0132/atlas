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
from typing import Iterator, Optional

from .. import config, sources
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
    _sources_context,
)


def answer_agentic(
    question: str,
    seed: dict,
    nodes: list[dict],
    history: Optional[list[dict]] = None,
) -> Iterator[tuple[str, object]]:
    """Agentic Q&A: Claude reads the visible papers via tool use, then answers.

    Yields ``("trace", {...})`` as it reads/expands, ``("nodes", {...})`` when
    expand_node discovers papers not previously on the graph, ``("token", str)``
    for the streamed answer, ``("discard", None)`` if streamed preamble must be
    dropped (the turn turned out to be a tool call), and a final
    ``("cited", node_ids)`` (the papers it actually read)."""
    import anthropic

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    numbered = _number_nodes(nodes)

    # Offer the source-search tool only when the user actually has a library
    # (checked before touching the embedding model, so an empty library never
    # pays the torch load). list_sources is cheap; available() loads the model.
    library = sources.list_sources()
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
            messages=messages,
            tools=tools if use_tools else [],
        ) as stream:
            for event in stream:
                et = getattr(event, "type", "")
                if et == "content_block_start" and getattr(event.content_block, "type", "") == "tool_use":
                    if not tool_turn:
                        tool_turn = True
                        emit_buf = ""  # this turn is a tool call, not the answer
                        if turn_text.strip():
                            yield ("discard", None)  # streamed preamble wasn't the answer
                elif et == "content_block_delta" and getattr(event.delta, "type", "") == "text_delta":
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
                if getattr(b, "type", "") != "tool_use":
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
                    content, trace = _run_search_sources(b, source_searches)
                    yield ("trace", trace)
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
        messages=messages,
    ) as stream:
        for text in _emit_hiding_sentinel(stream.text_stream, full_box):
            yield ("token", text)
    for cid in _parse_citations(full_box[0], numbered):
        if cid not in cited:
            cited.append(cid)
    yield ("cited", cited)
