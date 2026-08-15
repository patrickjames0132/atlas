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

from ..services.graph import Node, Provider

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


def graph_refs_from_text(nodes: Sequence[Node], text: str) -> dict[str, str]:
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
    graph_refs: dict[str, str] = {}
    for match in _REF_MARKER.finditer(text):
        for token in _REF_SEP.split(match.group(1)):
            index = int(token)
            if 1 <= index <= len(nodes):
                graph_refs[token] = nodes[index - 1].id
    return graph_refs


def source_order(hits: list[dict]) -> list[dict]:
    """The distinct sources behind a set of passages, first-seen order.

    The library counterpart to a graph's node list: what ``source_lines``
    numbers and ``source_refs`` resolves against, derived from whatever
    retrieval actually returned — what a graph-free turn can cite, as
    against the whole library the researcher is shown when a graph is open.

    Args:
        hits: Passage dicts from ``services.sources.search``.

    Returns:
        One ``{"id", "title"}`` dict per distinct source, first-seen order.
    """
    seen: set[str] = set()
    sources: list[dict] = []
    for hit in hits:
        source_id = hit.get("source_id")
        if source_id and source_id not in seen:
            seen.add(source_id)
            sources.append({"id": source_id, "title": hit.get("source_title", "")})
    return sources


def source_lines(sources: Sequence[dict]) -> str:
    """Render the library as the numbered list the model cites into.

    The exact analogue of ``node_lines`` for uploaded sources, and for the
    same reason: the model never sees a source's real id, only its position,
    because a one-token index is the only thing it can reproduce exactly. It
    freely rewords a *title* mid-prose ("The Feynman Lectures on Physics,
    Vol. III" for a source stored as ``the_feynman_lectures_vol_III_…``),
    which is precisely what made prose citations unresolvable before.

    Args:
        sources: The library entries to number, in display order — dicts
            carrying ``id``, ``title``, and optionally ``pages``/``kind``.

    Returns:
        One ``[Sn] "Title" (extent)`` line per source.
    """
    lines = []
    for number, source in enumerate(sources, start=1):
        extent = f"{source['pages']}pp" if source.get("pages") else source.get("kind", "")
        suffix = f" ({extent})" if extent else ""
        lines.append(f'[S{number}] "{source["title"]}"{suffix}')
    return "\n".join(lines)


def paper_refs(nodes: Sequence[Node], text: str, provider: Provider) -> dict[str, dict]:
    """Resolve the ``[n]`` markers prose used to readable paper references.

    The richer sibling of ``graph_refs_from_text``: same scan, same numbering, but
    it carries the title and URL rather than only the node id. With a graph
    open the frontend resolves ``[n]`` itself against the list it already
    holds, so the id is enough; with no graph it holds nothing, and a bare id
    points at no canvas — the marker would render as dead text with no way to
    learn which paper it named.

    Args:
        nodes: The same node sequence ``node_lines`` numbered.
        text: The finished answer prose.
        provider: The backend the run searched — stamped on every reference,
            since the ids are only resolvable there (see ``events.PaperRef``).

    Returns:
        ``{"3": {"node_id": ..., "title": ..., "url": ..., "provider": ...},
        ...}`` — keyed by the marker's number as a string, referenced in-range
        indices only.
    """
    paper_refs: dict[str, dict] = {}
    for token, node_id in graph_refs_from_text(nodes, text).items():
        node = nodes[int(token) - 1]
        paper_refs[token] = {
            "node_id": node_id,
            "title": node.title,
            "url": node.url or "",
            "provider": provider,
        }
    return paper_refs


def format_passages(hits: list[dict], sources: Sequence[dict]) -> str:
    """Render retrieved library passages for a prompt.

    Each passage is tagged with the citation marker the model should copy
    into its prose verbatim — ``[Sn, p.N]``, indexing into ``sources`` — so
    attribution is a copy, not a recall.

    Args:
        hits: Passage dicts from ``services.sources.search`` (each carrying
            ``source_id``, ``source_title``, optional ``page``, and ``text``).
        sources: The numbered library the tags index into, as from
            ``source_order`` (a turn's retrieved set) or the whole library.

    Returns:
        One passage per paragraph, tagged ``[Sn, p.N]``, whitespace collapsed.
        A passage whose source isn't in ``sources`` falls back to its bare
        title — unciteable, but never silently dropped.
    """
    numbers = {source["id"]: number for number, source in enumerate(sources, start=1)}
    lines = []
    for hit in hits:
        page = f", p.{hit['page']}" if hit.get("page") else ""
        number = numbers.get(hit.get("source_id", ""))
        tag = f"S{number}{page}" if number else f"{hit['source_title']}{page}"
        lines.append(f"[{tag}] {' '.join(hit['text'].split())}")
    return "\n\n".join(lines)


#: A library citation marker in model prose: ``[S3, p.243]``, or ``[S3]`` for
#: a source with no pages (a web page). Group 1 is the source's index into the
#: numbered library, group 2 the page when one is cited.
_SOURCE_MARKER = re.compile(r"\[S(\d+)(?:,?\s*p\.\s*(\d+))?\]", re.IGNORECASE)


def source_refs(sources: Sequence[dict], text: str) -> dict[str, dict]:
    """Map the ``[Sn]`` markers in prose back to the sources they name.

    The library counterpart to ``graph_refs_from_text``, with one deliberate
    difference: it is keyed by **index alone**, not by the full marker, and
    carries no page. The page is already in the marker, so the frontend reads
    it from there and this map stays page-free — which lets it be emitted
    *before* the prose streams, so a marker resolves the moment it appears
    instead of flickering as raw ``[S3, p.243]`` until the answer ends.

    Args:
        sources: The same library sequence ``source_lines`` numbered.
        text: The prose to scan, or ``""`` to map every source (the up-front
            emit, before any prose exists).

    Returns:
        ``{"3": {"source_id": ..., "title": ...}, ...}`` — keyed by the
        marker's index as a string. Out-of-range indices are dropped: a
        hallucinated marker degrades to plain text, it never raises.
    """
    if text:
        wanted = {int(match.group(1)) for match in _SOURCE_MARKER.finditer(text)}
    else:
        wanted = set(range(1, len(sources) + 1))
    return {
        str(index): {"source_id": sources[index - 1]["id"], "title": sources[index - 1]["title"]}
        for index in sorted(wanted)
        if 1 <= index <= len(sources)
    }


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
