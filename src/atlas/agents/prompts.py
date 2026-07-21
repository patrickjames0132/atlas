"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
Turns app data into model input, shared by every sub-agent: skill loading,
retrieved passages rendered for a prompt, and route-layer conversation turns
converted to PydanticAI message history.

Agents combine their prompt parts natively — ``instructions=[SYSTEM_PROMPT,
*(skill(name) for name in SKILLS)]`` — since PydanticAI accepts a sequence and
joins it with blank lines itself; this module only supplies the parts.

(Named ``prompts`` rather than ``skills`` — that name belongs to the
``skills/`` directory this module reads from.)

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

import math
import re
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


def _node_line(number: int, node: Node) -> str:
    """One paper's numbered line: ``[n] (year, citations; relations) Title —
    <tldr or abstract, truncated>``.

    Args:
        number: The paper's 1-based position in the numbered list.
        node: The graph node to render.

    Returns:
        The single formatted line.
    """
    year = node.year if node.year is not None else "n.d."
    citations = (
        f", {node.citation_count} citations" if node.citation_count is not None else ""
    )
    summary = node.tldr or node.abstract or ""
    if summary:
        summary = " — " + " ".join(summary.split())[:240]
    relations = ",".join(node.rels) or "?"
    return f"[{number}] ({year}{citations}; {relations}) {node.title}{summary}"


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
    return "\n".join(_node_line(number, node) for number, node in enumerate(nodes, start=1))


def node_lines_by_era(nodes: Sequence[Node], buckets: int = 3) -> str:
    """``node_lines`` with the papers banded into era separators.

    The rendering half of the lecture's full-span guardrail: the same numbered
    lines (numbers still come from the list position, so ``idx_to_id`` is
    unchanged), but split into ``buckets`` equal-width year spans with a
    ``--- YEAR1–YEAR2 ---`` header before each. The nodes are assumed already
    sorted oldest-first (the orchestrator's ``_chronological``), so the headers
    read top-to-bottom in time and an undated tail lands under ``--- undated
    ---``. Seeing the timeline laid out this way nudges the model to give each
    era a beat instead of dwelling on the oldest, most-cited papers.

    Falls back to a plain ``node_lines`` when there aren't at least two distinct
    years to band (nothing to spread).

    Args:
        nodes: The story's nodes, oldest-first.
        buckets: How many era bands to split the dated range into.

    Returns:
        The numbered list with era-separator lines interleaved.
    """
    dated_years = {node.year for node in nodes if node.year is not None}
    if len(dated_years) < 2:
        return node_lines(nodes)
    earliest, latest = min(dated_years), max(dated_years)
    width = max(1, math.ceil((latest - earliest + 1) / buckets))
    lines: list[str] = []
    current_band: int | None = -1  # sentinel: no header emitted yet
    for number, node in enumerate(nodes, start=1):
        band = None if node.year is None else min(buckets - 1, (node.year - earliest) // width)
        if band != current_band:
            current_band = band
            if band is None:
                lines.append("--- undated ---")
            else:
                start = earliest + band * width
                end = min(latest, start + width - 1)
                label = f"{start}" if start == end else f"{start}–{end}"
                lines.append(f"--- {label} ---")
        lines.append(_node_line(number, node))
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


#: An inline citation marker in model prose: a single index (``[7]``) or a
#: combined list the model sometimes writes (``[14, 29]`` / ``[14 29]``). Group
#: 1 holds the digits and separators between the brackets; split it on
#: ``_REF_SEP`` for the individual indices.
_REF_MARKER = re.compile(r"\[(\d+(?:[\s,]+\d+)*)\]")
#: The separator between indices inside a combined marker (comma and/or space).
_REF_SEP = re.compile(r"[\s,]+")


def refs_from_text(nodes: Sequence[Node], text: str) -> dict[str, str]:
    """Map the ``[n]`` markers a passage of prose *used* back to node ids.

    The clickable-citation counterpart to ``idx_to_id``: where that resolves an
    explicit index list, this scans prose for the markers actually written and
    resolves each against the same numbered list. Only referenced, in-range
    indices are kept, so the map stays small and reload-safe. A combined marker
    (``[14, 29]``) contributes each of its indices, so every number in it stays
    clickable.

    Args:
        nodes: The same node sequence ``node_lines`` numbered.
        text: The prose to scan (a lecture beat, an answer).

    Returns:
        ``{"7": "<node id>", ...}`` — keyed by the marker's number as a string.
    """
    refs: dict[str, str] = {}
    for match in _REF_MARKER.finditer(text):
        for token in _REF_SEP.split(match.group(1)):
            index = int(token)
            if 1 <= index <= len(nodes):
                refs[token] = nodes[index - 1].id
    return refs


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
