"""Grounded Q&A (Phase 3a): a conversational reply to a question, grounded ONLY
in the papers currently visible on the graph, streamed token-by-token and ending
with the nodes it cited.

This is the non-agentic path — no tool use, no traversal — so it runs under both
teacher backends. The agentic upgrade lives in ``agentic.py``.
"""

from __future__ import annotations

from typing import Iterator, Optional

from .. import config
from .backends import _stream
from .common import _CITED, _number_nodes, _parse_citations, _qa_context

_QA_SYSTEM = (
    "You are a sharp, friendly research teacher answering a student's question, "
    "grounded ONLY in the papers currently visible on their citation graph (the "
    "numbered list below). Answer conversationally and concretely, in a few short "
    "paragraphs at most. If the answer isn't supported by the visible papers, say "
    "so briefly and suggest where on the graph to look — do NOT invent facts or "
    "cite papers that aren't listed.\n\n"
    "After your answer, on a new final line, emit exactly " + _CITED + " followed "
    "by a JSON array of the indices of the papers you drew from, e.g. "
    + _CITED + " [1, 4]. Use " + _CITED + " [] if you cited none. Output nothing "
    "after that line."
)


def answer_stream(
    question: str,
    seed: dict,
    nodes: list[dict],
    history: Optional[list[dict]] = None,
) -> Iterator[tuple[str, object]]:
    """Answer a question grounded in the visible graph, streaming tokens.

    The graph context rides on the current question (not the history) so it
    always reflects the latest on-screen neighborhood, even as the user pans
    and expands between turns. The ``<<CITED>>`` sentinel and everything
    after it is stripped from the visible answer and parsed into node ids —
    a tail is held back on every emit so a sentinel split across chunks never
    leaks to the user.

    Args:
        question: The user's question.
        seed: The seed paper (heads the grounding context).
        nodes: The visible graph nodes (the grounding scope).
        history: Prior conversation turns as ``[{role, content}, ...]``;
            malformed turns are skipped.

    Yields:
        ``("token", text)`` events as the prose streams, then one final
        ``("cited", node_ids)`` event.

    Raises:
        RuntimeError: When every teacher backend failed to start.
    """
    numbered = _number_nodes(nodes)
    messages: list[dict] = []
    for turn in history or []:
        role = turn.get("role")
        content = turn.get("content")
        if role in ("user", "assistant") and isinstance(content, str):
            messages.append({"role": role, "content": content})
    # The graph context rides on the current question so it always reflects the
    # latest on-screen neighborhood, even as the user pans/expands between turns.
    messages.append(
        {"role": "user", "content": f"{_qa_context(seed, numbered)}\n\nQuestion: {question}"}
    )

    buf = ""
    full = ""
    cut = False  # once we hit the sentinel, stop emitting prose
    # Hold back a tail so a sentinel split across chunks never leaks to the user.
    hold = len(_CITED)
    for chunk in _stream(_QA_SYSTEM, messages, config.TEACHER_MAX_TOKENS):
        full += chunk
        if cut:
            continue
        buf += chunk
        if _CITED in buf:
            visible, _ = buf.split(_CITED, 1)
            if visible:
                yield ("token", visible)
            cut = True
            buf = ""
            continue
        # Emit everything except a trailing window that might start the sentinel.
        if len(buf) > hold:
            emit, buf = buf[:-hold], buf[-hold:]
            if emit:
                yield ("token", emit)
    if not cut and buf:
        yield ("token", buf)

    yield ("cited", _parse_citations(full, numbered))
