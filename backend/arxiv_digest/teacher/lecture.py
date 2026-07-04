"""Streaming lecture beats, plus the "How we got here" time-travel backfill.

``lecture_beats(...)`` yields an ordered sequence of *beats* — each a short
paragraph bound to a set of graph nodes to highlight. The model emits
newline-delimited JSON so we can parse and stream one beat at a time.

``history_backfill(...)`` (Phase 3e) walks backward through references before a
history lecture, so it can open at a field's roots instead of mid-stream.
"""

from __future__ import annotations

import json
from typing import Iterator, Optional

from .. import config
from ..integrations import semantic_scholar as s2
from .backends import _stream
from .common import _idx_to_id, _node_lines, _number_nodes
from .neighbors import _s2_neighbors

_LECTURE_SYSTEM = (
    "You are an expert teacher narrating the intellectual history and intuition of "
    "a research area to a curious graduate student. You are given a SEED paper and "
    "the papers currently visible on an interactive citation graph (its references, "
    "citations, and similar work), presented as a numbered list. Produce a short, "
    "vivid lecture as an ordered sequence of BEATS. Each beat is one tight paragraph "
    "(2–4 sentences) that advances the story and points at specific papers so they "
    "can light up on the graph as you speak.\n\n"
    "OUTPUT FORMAT: emit ONE JSON object per line (newline-delimited JSON) and "
    "NOTHING else — no prose, no markdown, no code fences, no wrapping array. Each "
    'object is exactly: {"heading": "<3–6 word signpost>", "text": "<the narration '
    'paragraph>", "nodes": [<indices from the numbered list this beat is about>]}\n\n'
    "RULES:\n"
    "- 5–9 beats total.\n"
    "- 'nodes' must be integer indices from the numbered list; reference 1–4 papers "
    "per beat. Use [] only for a pure framing/closing beat.\n"
    "- Explain intuition and significance in plain English; avoid hype and jargon; "
    "do not merely list titles.\n"
    "- Ground claims in the titles, years, and summaries provided. Don't invent "
    "specifics the data doesn't support."
)

_MODE_INTENT = {
    "history": (
        "Mode: HOW WE GOT HERE. Tell the story chronologically — from the oldest "
        "roots among the references, through the key ideas that made each next step "
        "possible, to the SEED paper and the work it went on to spawn (its citations)."
    ),
    "intuition": (
        "Mode: INTUITION OF THIS PAPER. Center the SEED paper: what problem it "
        "solved, the core idea, and why it works — using the surrounding papers only "
        "for context and contrast."
    ),
    "bridge": (
        "Mode: BRIDGE. Build a conceptual bridge between the SEED paper and the "
        "TARGET paper, tracing the ideas that connect two areas that may look "
        "unrelated at first."
    ),
}


def _lecture_prompt(
    seed: dict, numbered: list[dict], mode: str, target: Optional[dict]
) -> str:
    """Assemble the user prompt for a lecture.

    Args:
        seed: The seed paper (title used in the header).
        numbered: Visible nodes that have been through ``_number_nodes``.
        mode: ``history``, ``intuition``, or ``bridge`` (unknown modes fall
            back to ``history``).
        target: The bridge target paper (bridge mode only), or None.

    Returns:
        The full prompt: mode intent, seed/target header, the numbered paper
        list, and the delivery instruction.
    """
    intent = _MODE_INTENT.get(mode, _MODE_INTENT["history"])
    seed_title = seed.get("title", "(the seed paper)")
    header = f"SEED paper: {seed_title}"
    if mode == "bridge" and target:
        header += f"\nTARGET paper: {target.get('title', '')}"
    return (
        f"{intent}\n\n"
        f"{header}\n\n"
        f"Papers on the graph (numbered):\n{_node_lines(numbered)}\n\n"
        f"Now deliver the lecture as newline-delimited JSON beats."
    )


def _parse_beat(line: str, numbered: list[dict]) -> Optional[dict]:
    """Parse one JSONL line into a beat dict.

    Tolerates stray code fences / blank lines the model might emit around the
    JSONL despite instructions.

    Args:
        line: One line of the model's newline-delimited JSON output.
        numbered: Visible nodes that have been through ``_number_nodes``
            (for mapping the beat's indices back to node ids).

    Returns:
        ``{"heading", "text", "node_ids"}`` — or None when the line isn't a
        valid beat (not JSON, or empty text).
    """
    line = line.strip().strip("`").strip()
    if not line or not line.startswith("{"):
        return None
    try:
        obj = json.loads(line)
    except json.JSONDecodeError:
        return None
    text = obj.get("text")
    if not isinstance(text, str) or not text.strip():
        return None
    return {
        "heading": (obj.get("heading") or "").strip(),
        "text": text.strip(),
        "node_ids": _idx_to_id(numbered, obj.get("nodes")),
    }


def lecture_beats(
    seed: dict, nodes: list[dict], mode: str = "history", target: Optional[dict] = None
) -> Iterator[dict]:
    """Stream a lecture as parsed beats.

    Args:
        seed: The seed paper.
        nodes: The visible graph nodes (already including any backfilled
            ancestors in history mode).
        mode: ``history``, ``intuition``, or ``bridge``.
        target: The bridge target paper (bridge mode only), or None.

    Yields:
        Beat dicts ``{heading, text, node_ids}`` one at a time as the model
        streams newline-delimited JSON.

    Raises:
        RuntimeError: When every teacher backend failed to start.
    """
    numbered = _number_nodes(nodes)
    prompt = _lecture_prompt(seed, numbered, mode, target)
    messages = [{"role": "user", "content": prompt}]

    buf = ""
    for chunk in _stream(_LECTURE_SYSTEM, messages, config.TEACHER_MAX_TOKENS):
        buf += chunk
        while "\n" in buf:
            line, buf = buf.split("\n", 1)
            beat = _parse_beat(line, numbered)
            if beat:
                yield beat
    beat = _parse_beat(buf, numbered)
    if beat:
        yield beat


# --- "How we got here" time travel (Phase 3e) --------------------------------
def _seed_year(nodes: list[dict], seed_id: Optional[str]) -> Optional[int]:
    """Determine the seed's publication year.

    Args:
        nodes: The visible graph nodes.
        seed_id: The seed's node id, or None.

    Returns:
        The seed node's year when present; otherwise the newest visible year
        (the seed is almost always the most recent paper on the graph); None
        when no node carries a year at all.
    """
    for n in nodes:
        if n.get("id") == seed_id and isinstance(n.get("year"), int):
            return n["year"]
    years = [n["year"] for n in nodes if isinstance(n.get("year"), int)]
    return max(years) if years else None


def history_backfill(seed: dict, nodes: list[dict]) -> Iterator[tuple[str, object]]:
    """Walk BACKWARD through references before the history lecture.

    Lets the story start at a field's roots instead of mid-stream (a modern
    seed's graph rarely reaches the foundational work). We launch NOT from the
    seed — its references are already on the graph — but from the OLDEST
    papers already visible, which sit closest to the roots; each hop pulls
    their references, adds the most-cited new (older) ones, and carries the
    oldest additions into the next hop, stopping once we reach papers
    ~``LECTURE_HISTORY_LOOKBACK`` years older than the seed or spend the hop
    budget. Reuses the Phase 3c reference-hop machinery (``_s2_neighbors``,
    day-cached). S2 errors on a hop are noted and skipped, never raised.

    Args:
        seed: The seed paper (must carry an ``id``; otherwise the walk is a
            no-op).
        nodes: The visible graph nodes.

    Yields:
        ``("trace", {hop, found, oldest})`` per productive level, and
        ``("nodes", {nodes, edges})`` discoveries to merge into the live
        graph. When nothing older was found at all, one final
        ``("trace", {found: 0, error: bool})`` says so rather than failing
        silently.
    """
    seed_id = seed.get("id")
    if not seed_id:
        return

    known = {n["id"] for n in nodes if n.get("id")}
    known.add(seed_id)
    seed_year = _seed_year(nodes, seed_id)
    year_floor = seed_year - config.LECTURE_HISTORY_LOOKBACK if seed_year else None

    # Launch from the oldest papers already on the graph, not the seed: expanding
    # the seed only re-finds its already-visible references. The oldest visible
    # papers are the closest to the roots — walking back from them reaches the
    # foundational work the graph doesn't show yet.
    launch = sorted(
        (n for n in nodes if n.get("id") and not n.get("is_seed")),
        key=lambda n: (n.get("year") or 9999),
    )
    frontier = [n["id"] for n in launch[: config.LECTURE_HISTORY_FRONTIER]] or [seed_id]
    total_added = 0
    errored = False

    for hop in range(config.LECTURE_HISTORY_HOPS):
        if not frontier:
            break
        candidates: dict[str, dict] = {}
        edges: list[dict] = []
        for pid in frontier:
            try:
                hits = _s2_neighbors(pid, "references")
            except s2.S2Error:
                errored = True
                continue
            for hit in hits:
                n = hit["node"]
                nid = n.get("id")
                if not nid or nid == pid:
                    continue
                edges.append({
                    "source": pid, "target": nid, "type": "reference",
                    "influential": hit.get("influential", False),
                })
                if nid not in known and nid not in candidates:
                    candidates[nid] = n
        if not candidates:
            break

        # Add the most-cited new ancestors (the seminal ones), capped per hop.
        ranked = sorted(
            candidates.values(),
            key=lambda n: (n.get("citation_count") or 0),
            reverse=True,
        )
        additions = ranked[: config.LECTURE_HISTORY_PER_HOP]
        new_nodes = []
        for n in additions:
            known.add(n["id"])
            disc = dict(n)
            disc["rels"] = ["reference"]
            disc["is_seed"] = False
            disc["discovered"] = True
            new_nodes.append(disc)

        # Keep only edges whose endpoints both landed on the graph (no danglers).
        kept_edges = [e for e in edges if e["source"] in known and e["target"] in known]
        years = [n["year"] for n in additions if isinstance(n.get("year"), int)]
        oldest = min(years) if years else None
        total_added += len(new_nodes)
        yield ("trace", {"hop": hop + 1, "found": len(new_nodes), "oldest": oldest})
        yield ("nodes", {"nodes": new_nodes, "edges": kept_edges})

        # March further back: carry the oldest additions (all on-graph) into the
        # next hop so their edges stay coherent.
        by_year = sorted(additions, key=lambda n: (n.get("year") or 9999))
        frontier = [n["id"] for n in by_year[: config.LECTURE_HISTORY_FRONTIER]]
        if year_floor and oldest is not None and oldest <= year_floor:
            break

    # Never found anything older — say so once, rather than failing silently.
    if total_added == 0:
        yield ("trace", {"hop": 1, "found": 0, "oldest": None, "error": errored})
