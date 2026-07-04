"""Offline library chat (Phase 3d): a graph-free RAG chat straight over the
user's local library. Retrieve the most relevant passages, then answer grounded
only in them, citing inline by page.

No tool loop, so it works under BOTH backends (api and the claude CLI) and needs
no open graph — the lightweight entry point for "just ask my books a question".
"""

from __future__ import annotations

from typing import Iterator, Optional

from .. import config
from ..library import sources
from .backends import _stream
from .common import _format_passages

_SOURCES_CHAT_SYSTEM = (
    "You are a sharp, friendly teacher answering a student's question grounded ONLY "
    "in passages retrieved from their OWN uploaded library (books, PDFs, web pages), "
    "shown below. Answer conversationally and concretely, in a few short paragraphs "
    "at most. Attribute what you draw on inline by source and page, e.g. "
    "\"(Deep Learning, p.243)\". If the passages don't contain the answer, say so "
    "plainly and suggest what to upload or how to rephrase — do NOT invent facts or "
    "cite sources that aren't shown."
)


def _hit_titles(hits: list[dict]) -> list[str]:
    """Collect the distinct source titles among retrieved passages.

    Args:
        hits: Passage dicts from ``library.sources.search``.

    Returns:
        The distinct ``source_title`` values in first-seen order — surfaced
        in the trace so the chat can show which sources it drew on.
    """
    seen: set[str] = set()
    out: list[str] = []
    for h in hits:
        t = h.get("source_title")
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out


def answer_from_sources(
    question: str,
    history: Optional[list[dict]] = None,
    source_ids: Optional[list[str]] = None,
) -> Iterator[tuple[str, object]]:
    """Answer a question purely from the user's local library — no graph.

    Retrieve-then-answer (no tool use), so it runs on either teacher backend.
    When retrieval comes up empty, a friendly "nothing found" message is
    emitted as the answer rather than an error.

    Args:
        question: The user's question (doubles as the retrieval query).
        history: Prior conversation turns as ``[{role, content}, ...]``;
            malformed turns are skipped.
        source_ids: Scope retrieval to this subset of source ids. None means no
            scope — the whole library; an explicit empty list means no sources
            selected — retrieval finds nothing.

    Yields:
        A single ``("trace", {found, sources})`` naming the retrieved
        passages, then ``("token", str)`` prose events.

    Raises:
        RuntimeError: When every teacher backend failed to start.
        sqlite3.Error: On library database failures during retrieval.
    """
    hits = sources.search(question, k=config.SOURCES_CHAT_K, source_ids=source_ids)
    yield ("trace", {"found": len(hits), "sources": _hit_titles(hits)})
    if not hits:
        yield (
            "token",
            "I couldn't find anything in your library about that. Try rephrasing, "
            "or upload a source that covers it.",
        )
        return

    messages: list[dict] = []
    for turn in history or []:
        role = turn.get("role")
        content = turn.get("content")
        if role in ("user", "assistant") and isinstance(content, str):
            messages.append({"role": role, "content": content})
    messages.append(
        {
            "role": "user",
            "content": (
                f"Passages from your library:\n\n{_format_passages(hits)}\n\n"
                f"Question: {question}"
            ),
        }
    )

    for chunk in _stream(_SOURCES_CHAT_SYSTEM, messages, config.TEACHER_MAX_TOKENS):
        yield ("token", chunk)
