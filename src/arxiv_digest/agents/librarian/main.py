"""The librarian: graph-free RAG chat over the user's own uploaded library.

Retrieve-then-answer: the most relevant passages are fetched
deterministically (hybrid FTS5 + vector search) *before* the model is
engaged, then one streamed completion answers grounded only in them,
attributing inline by title and page. No tools, no graph — the lightweight
"just ask my books" path, and the whole ``skills/workflows/librarian.md``
playbook in one generator.

Empty retrieval is an answer, not an error: a friendly no-hits line streams
back without the model ever running. Real failures (model, database)
propagate — the caller ends the event stream with ``Error``.
"""

from __future__ import annotations

from typing import Iterator

from pydantic_ai import Agent

from ...config import config
from ...services import sources
from .. import events, factory, prompts
from .config import AGENT_ID, NO_HITS_ANSWER, SKILLS, SYSTEM_PROMPT

agent: Agent[None, str] = Agent(
    factory.build_model(AGENT_ID),
    instructions=prompts.assemble(SYSTEM_PROMPT, SKILLS),
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


def answer(
    question: str,
    history: list[dict] | None = None,
    source_ids: list[str] | None = None,
) -> Iterator[events.RetrievalTrace | events.Token]:
    """Answer a question purely from the user's local library — no graph.

    Args:
        question: The user's question (doubles as the retrieval query).
        history: Prior turns as ``[{role, content}, ...]``; malformed turns
            are skipped.
        source_ids: Scope retrieval to these source ids. ``None`` means no
            scope — the whole library; an explicit empty list means "no
            sources selected" — retrieval finds nothing.

    Yields:
        One ``RetrievalTrace`` naming what was found, then ``Token`` prose —
        the streamed answer, or the canned no-hits line when retrieval came
        up empty (the model is never engaged for that).

    Raises:
        Exception: Model/stream failures propagate — the caller ends the
            event stream with ``Error``.
        sqlite3.Error: On library database failures during retrieval.
    """
    hits = sources.search(question, k=config.sources.retrieval.chat_k, source_ids=source_ids)
    yield events.RetrievalTrace(found=len(hits), sources=_hit_titles(hits))
    if not hits:
        yield events.Token(text=NO_HITS_ANSWER)
        return

    prompt = (
        f"Passages from your library:\n\n{prompts.format_passages(hits)}\n\n"
        f"Question: {question}"
    )
    result = agent.run_stream_sync(prompt, message_history=prompts.history(history))
    for delta in result.stream_text(delta=True):
        if delta:
            yield events.Token(text=delta)
