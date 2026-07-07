"""Turns app data into model input, shared by every sub-agent: skill loading,
retrieved passages rendered for a prompt, and route-layer conversation turns
converted to PydanticAI message history.

Agents combine their prompt parts natively — ``instructions=[SYSTEM_PROMPT,
*(skill(name) for name in SKILLS)]`` — since PydanticAI accepts a sequence and
joins it with blank lines itself; this module only supplies the parts.

(Named ``prompts`` rather than ``skills`` — that name belongs to the
``skills/`` directory this module reads from.)
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from pathlib import Path

from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    UserPromptPart,
)

from ..services.graph import Node

SKILLS_DIR = Path(__file__).parent / "skills"


def skill(name: str) -> str:
    """Read one skill's prompt-ready markdown from ``agents/skills/``.

    Args:
        name: The skill's file stem, e.g. ``"teaching-voice"``.

    Returns:
        The skill file's content, stripped.

    Raises:
        FileNotFoundError: When no such skill exists — a typo'd name in an
            agent's config.py fails at agent import, not by silently
            weakening its prompt.
    """
    return (SKILLS_DIR / f"{name}.md").read_text().strip()


def node_lines(nodes: Sequence[Node]) -> str:
    """Render graph nodes as the numbered list the model refers into.

    A paper's number is simply its list position + 1 — the model never sees
    Semantic Scholar's long hex ids (the ``numbered-papers`` skill explains
    the protocol to the model; ``idx_to_id`` maps its indices back).

    Args:
        nodes: The visible graph nodes, in display order.

    Returns:
        One line per paper — ``[n] (year, citations; relations) Title — <tldr
        or abstract, truncated>``.
    """
    lines = []
    for number, node in enumerate(nodes, start=1):
        year = node.year if node.year is not None else "n.d."
        citations = (
            f", {node.citation_count} citations"
            if node.citation_count is not None
            else ""
        )
        summary = node.tldr or node.abstract or ""
        if summary:
            summary = " — " + " ".join(summary.split())[:240]
        relations = ",".join(node.rels) or "?"
        lines.append(f"[{number}] ({year}{citations}; {relations}) {node.title}{summary}")
    return "\n".join(lines)


def idx_to_id(nodes: Sequence[Node], indices: Iterable[int]) -> list[str]:
    """Map the model's 1-based numbered-list indices back to node ids.

    Args:
        nodes: The same node sequence ``node_lines`` numbered.
        indices: Indices the model emitted; out-of-range values are ignored,
            never raised on (a hallucinated index just means one fewer
            highlight).

    Returns:
        The node ids for the valid indices, in the model's order.
    """
    return [nodes[index - 1].id for index in indices if 1 <= index <= len(nodes)]


def format_passages(hits: list[dict]) -> str:
    """Render retrieved library passages for a prompt.

    Args:
        hits: Passage dicts from ``services.sources.search`` (each carrying
            ``source_title``, optional ``page``, and ``text``).

    Returns:
        One passage per paragraph, tagged ``[Title, p.N]`` so the model can
        attribute it inline, whitespace collapsed.
    """
    lines = []
    for hit in hits:
        location = f", p.{hit['page']}" if hit.get("page") else ""
        lines.append(f"[{hit['source_title']}{location}] {' '.join(hit['text'].split())}")
    return "\n\n".join(lines)


def history(turns: list[dict] | None) -> list[ModelMessage]:
    """Convert route-layer conversation turns into PydanticAI message history.

    Only usable with agents built on ``instructions=`` (as all of ours are):
    with ``system_prompt=``, PydanticAI drops the prompt entirely whenever a
    message history is passed, silently losing the persona on every
    follow-up turn.

    Args:
        turns: Prior turns as ``[{role: user|assistant, content: str}, ...]``.
            Malformed turns are skipped, never raised on — history is
            nice-to-have context, not worth failing an answer over.

    Returns:
        The turns as ``ModelRequest`` / ``ModelResponse`` messages.
    """
    messages: list[ModelMessage] = []
    for turn in turns or []:
        content = turn.get("content")
        if not isinstance(content, str):
            continue
        if turn.get("role") == "user":
            messages.append(ModelRequest(parts=[UserPromptPart(content=content)]))
        elif turn.get("role") == "assistant":
            messages.append(ModelResponse(parts=[TextPart(content=content)]))
    return messages
