"""Shared text plumbing for the teacher: how visible papers are numbered and
rendered for a prompt, how the model's 1-based indices map back to node ids, and
how the ``<<CITED>>`` sentinel (which trails a Q&A answer) is parsed and hidden.

These helpers carry no domain logic of their own — every teacher product
(lecture, Q&A, agentic, sources chat) leans on them, so they live here to avoid
circular imports between the concern modules.
"""

from __future__ import annotations

import json
from typing import Iterator

# Sentinel the Q&A model prints after its prose, followed by the JSON list of
# node indices it drew from. Kept out of the visible answer.
_CITED = "<<CITED>>"


def _number_nodes(nodes: list[dict]) -> list[dict]:
    """Attach a 1-based index to each visible node.

    The model never handles the long Semantic Scholar paperIds — it refers to
    papers by these indices, which map back to ids on the way out.

    Args:
        nodes: The visible graph nodes, in display order.

    Returns:
        Shallow copies of the nodes, each with an ``idx`` key (1-based, input
        order preserved).
    """
    return [{**n, "idx": i + 1} for i, n in enumerate(nodes)]


def _node_lines(numbered: list[dict]) -> str:
    """Render the numbered papers for a prompt.

    Args:
        numbered: Nodes that have been through ``_number_nodes``.

    Returns:
        One line per paper — index, year, citation count, relations, title,
        and a summary snippet (TL;DR or abstract, truncated) when we have one.
    """
    lines = []
    for n in numbered:
        year = n.get("year") or "n.d."
        cites = n.get("citation_count")
        cite_str = f", {cites} citations" if isinstance(cites, int) else ""
        summary = n.get("tldr") or n.get("abstract") or ""
        if summary:
            summary = " — " + summary.strip().replace("\n", " ")[:240]
        rels = ",".join(n.get("rels", [])) or "?"
        lines.append(f"[{n['idx']}] ({year}{cite_str}; {rels}) {n.get('title', '')}{summary}")
    return "\n".join(lines)


def _idx_to_id(numbered: list[dict], indices: object) -> list[str]:
    """Map model-emitted 1-based indices back to Semantic Scholar node ids.

    Args:
        numbered: Nodes that have been through ``_number_nodes``.
        indices: Whatever the model emitted as its index list — anything that
            isn't a list of in-range integers is tolerated (bools, floats,
            and out-of-range values are ignored, never raised on).

    Returns:
        The node ids for the valid indices, in the model's order.
    """
    out: list[str] = []
    if not isinstance(indices, list):
        return out
    by_idx = {n["idx"]: n["id"] for n in numbered if n.get("id")}
    for i in indices:
        if isinstance(i, bool):
            continue
        if isinstance(i, int) and i in by_idx:
            out.append(by_idx[i])
    return out


def _qa_context(seed: dict, numbered: list[dict]) -> str:
    """Build the grounding context block for a Q&A prompt.

    Args:
        seed: The seed paper (its title heads the block).
        numbered: Nodes that have been through ``_number_nodes``.

    Returns:
        The seed line plus the numbered paper list, ready to prepend to a
        question.
    """
    return (
        f"SEED paper: {seed.get('title', '')}\n\n"
        f"Papers on the graph (numbered):\n{_node_lines(numbered)}"
    )


def _parse_citations(full: str, numbered: list[dict]) -> list[str]:
    """Pull the ``<<CITED>> [..]`` index list out of a full answer text.

    Args:
        full: The complete raw model output (prose + sentinel tail).
        numbered: Nodes that have been through ``_number_nodes``.

    Returns:
        The cited node ids, or an empty list when the sentinel is absent or
        its JSON array is malformed (never raises — a garbled citation line
        just means no highlights).
    """
    if _CITED not in full:
        return []
    tail = full.split(_CITED, 1)[1].strip()
    start = tail.find("[")
    end = tail.find("]", start)
    if start == -1 or end == -1:
        return []
    try:
        indices = json.loads(tail[start : end + 1])
    except json.JSONDecodeError:
        return []
    return _idx_to_id(numbered, indices)


def _emit_hiding_sentinel(chunks: Iterator[str], full_box: list[str]) -> Iterator[str]:
    """Stream visible prose while withholding the ``<<CITED>>`` sentinel.

    A tail the length of the sentinel is held back on every emit so a
    sentinel split across chunk boundaries never leaks to the user.

    Args:
        chunks: The raw streamed text chunks from the model.
        full_box: A single-element list; the complete raw text is appended to
            ``full_box[0]`` so the caller can parse citations afterwards
            (a mutable cell, since generators can't return values mid-stream).

    Yields:
        The visible prose chunks — everything before the sentinel, with the
        sentinel and its citation tail suppressed.
    """
    buf = ""
    cut = False
    hold = len(_CITED)
    for chunk in chunks:
        full_box[0] += chunk
        if cut:
            continue
        buf += chunk
        if _CITED in buf:
            visible = buf.split(_CITED, 1)[0]
            if visible:
                yield visible
            cut = True
            buf = ""
        elif len(buf) > hold:
            out, buf = buf[:-hold], buf[-hold:]
            yield out
    if not cut and buf:
        yield buf


def _format_passages(hits: list[dict]) -> str:
    """Render retrieved source passages for a prompt.

    Args:
        hits: Passage dicts from ``library.sources.search`` (each carrying
            ``source_title``, optional ``page``, and ``text``).

    Returns:
        One passage per paragraph, tagged with the source title and (for
        PDFs) page so the model can cite them inline, whitespace collapsed.
    """
    lines = []
    for h in hits:
        loc = f", p.{h['page']}" if h.get("page") else ""
        lines.append(f"[{h['source_title']}{loc}] {' '.join(h['text'].split())}")
    return "\n\n".join(lines)
