"""The agentic teacher's tool surface (Phase 3b): the tool schemas Claude sees,
the agent system prompt, and the runners that execute each tool call.

The agent answers by READING the visible papers (``read_paper``), EXPANDING the
graph to papers not yet shown (``expand_node`` — one hop of references /
citations / similar work), free-text SEARCHING Semantic Scholar (``search_papers``
for work not connected to the graph at all), and — when the user has a library —
semantically SEARCHING their own uploaded sources (``search_sources``). Each has
its own budget; the loop that drives them lives in ``agentic.py``.

Every ``_run_*`` runner returns plain text for the tool result plus a ``trace``
dict the route streams to the frontend, so the user watches the agent work.
"""

from __future__ import annotations

import logging
import urllib.parse
from typing import TYPE_CHECKING, Optional

from .. import config
from ..integrations import figures as figures_mod
from ..integrations import fulltext
from ..integrations import semantic_scholar as s2
from ..library import sources
from .common import _CITED, _format_passages
from .neighbors import _REL_TAG, _s2_neighbors, _s2_search, _search_scope

if TYPE_CHECKING:
    from anthropic.types import ToolParam

log = logging.getLogger(__name__)

_AGENT_SYSTEM = (
    "You are a sharp, friendly research teacher answering a student's question "
    "about the papers on their citation graph (numbered below). You have tools to "
    "READ those papers and to EXPAND the graph to papers not yet shown, so answer "
    "from real content and pull in outside papers when the visible ones don't have "
    "what you need.\n\n"
    "Use read_paper to pull in what you need: detail='summary' for a quick "
    "abstract + TL;DR, detail='full' for the full text when the question needs "
    "specifics (methods, results, numbers). Use expand_node(index, relation) to "
    "fetch a paper's references, citations, or similar work when the answer needs "
    "a paper that isn't on the graph yet — the papers it finds get numbered and "
    "added, so you can read_paper them right after. Use search_papers(query, "
    "year_from?, year_to?) when the answer needs work not connected to the graph "
    "at all — recent or topical papers that citation and similarity hops can't "
    "reach (e.g. \"the latest approach to X in 2026\"); pass year_from to bias "
    "toward recent work. Its hits also get numbered and added for you to read. "
    "When a full read lists a paper's figures and one would make your explanation "
    "clearer, call show_figure(index, figure) to place it in your answer, and "
    "point to it in your prose (e.g. \"as Figure 2 shows\"). "
    "Read, expand, and search only what you need — each has its own limited "
    "budget. Do NOT narrate that you're about to use a tool; just call it. When "
    "you have enough, write the answer in at most a few short paragraphs, grounded "
    "in what you read. Begin with the answer itself — do NOT preface it with "
    "remarks about your reading process (no \"I found the sections\"). If nothing "
    "you can reach supports an answer, say so briefly. Never invent facts or cite "
    "papers you haven't read."
)
# Appended only when the user has a source library (Phase 3d): tells the agent it
# can search the user's own uploaded books / pages and how to attribute them.
_SOURCES_PARA = (
    "\n\nThe student has also uploaded their own sources (books, PDFs, web pages), "
    "listed under \"Your library\" below. Use search_sources(query, source_id?) to "
    "semantically search them for relevant passages when the question touches their "
    "own material (e.g. \"how does this relate to my textbook?\") — pass a source_id "
    "to search one source, or omit it to search the whole library. When you use a "
    "passage, attribute it inline in your prose, e.g. \"(Deep Learning, p.243)\". "
    "Source passages are NOT graph papers — don't put them in the " + _CITED + " list."
)
# The final-line citation instruction (kept separate so _SOURCES_PARA can slot in
# ahead of it — nothing may come after this line).
_CITED_INSTRUCTION = (
    "\n\nAfter your answer, on a new final line, emit exactly " + _CITED + " followed "
    "by a JSON array of the indices of the papers your answer draws on, e.g. "
    + _CITED + " [1, 4]. Use " + _CITED + " [] if you drew on none. Output nothing "
    "after that line."
)
_AGENT_SYSTEM += _CITED_INSTRUCTION


def _agent_system(has_sources: bool) -> str:
    """Build the agent system prompt.

    Args:
        has_sources: True when the user has a searchable source library.

    Returns:
        The base agent prompt; with ``has_sources``, the source-search
        guidance is slotted in ahead of the final-line citation instruction
        (nothing may come after that line).
    """
    if not has_sources:
        return _AGENT_SYSTEM
    return _AGENT_SYSTEM[: -len(_CITED_INSTRUCTION)] + _SOURCES_PARA + _CITED_INSTRUCTION

_TOOLS: list[ToolParam] = [
    {
        "name": "read_paper",
        "description": (
            "Read one of the numbered papers on the graph to ground your answer. "
            "detail='summary' returns its abstract + TL;DR (cheap); detail='full' "
            "returns the full text via ar5iv (use sparingly — limited budget)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "index": {
                    "type": "integer",
                    "description": "The [n] index of the paper from the numbered list.",
                },
                "detail": {
                    "type": "string",
                    "enum": ["summary", "full"],
                    "description": "summary = abstract + TL;DR; full = full text.",
                },
            },
            "required": ["index", "detail"],
        },
    },
    {
        "name": "expand_node",
        "description": (
            "Pull one hop of neighbors — references, citations, or similar work — "
            "for a paper that's already numbered, and add them to the graph as new "
            "numbered papers you can then read_paper. Use when the question needs a "
            "paper that isn't currently visible."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "index": {
                    "type": "integer",
                    "description": "The [n] index of the paper to expand from.",
                },
                "relation": {
                    "type": "string",
                    "enum": ["references", "citations", "similar"],
                    "description": (
                        "references = papers it cites; citations = papers that cite "
                        "it; similar = embedding-similar work."
                    ),
                },
            },
            "required": ["index", "relation"],
        },
    },
    {
        "name": "search_papers",
        "description": (
            "Free-text search across all of Semantic Scholar for papers matching a "
            "query, optionally bounded by year — NOT limited to the graph or its "
            "citation neighborhood. Use for recent or topical work that references / "
            "citations / similar hops can't reach (e.g. the newest paper on a topic, "
            "which an old seed can't cite). Hits get numbered and added so you can "
            "read_paper them."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Free-text query — keywords or a topic, not an id.",
                },
                "year_from": {
                    "type": "integer",
                    "description": "Earliest publication year (inclusive). Omit for no floor.",
                },
                "year_to": {
                    "type": "integer",
                    "description": "Latest publication year (inclusive). Omit for no ceiling.",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "show_figure",
        "description": (
            "Place one of a paper's own figures (image + caption, from ar5iv) into "
            "your answer to illustrate a point. Only for a paper you've read in full "
            "— a full read lists that paper's figures and their numbers. Reference "
            "the figure in your prose (e.g. \"as Figure 2 shows\"); don't rely on it "
            "alone to make the point."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "index": {
                    "type": "integer",
                    "description": "The [n] index of the paper the figure comes from.",
                },
                "figure": {
                    "type": "integer",
                    "description": "The figure's number as listed in the paper's full read (1-based).",
                },
            },
            "required": ["index", "figure"],
        },
    },
]

# Added to the tool set only when the user has a source library (Phase 3d).
_SOURCE_TOOL: ToolParam = {
    "name": "search_sources",
    "description": (
        "Semantic search over the student's OWN uploaded sources (books, PDFs, web "
        "pages) — not the citation graph or Semantic Scholar. Returns the most "
        "relevant passages, each with its source title and page. Use when the "
        "question touches their own material. Omit source_id to search everything, "
        "or pass one from \"Your library\" to search a single source."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "What to look for — a concept or question, not an id.",
            },
            "source_id": {
                "type": "string",
                "description": "Restrict to one source's id from the library (optional).",
            },
        },
        "required": ["query"],
    },
}


def agentic_available() -> bool:
    """Report whether the tool-use agent can run.

    Returns:
        True when the backend is the Anthropic API and a key is configured —
        the claude CLI can't take our custom tools, so that backend falls
        back to the non-agentic ``answer_stream``.
    """
    return config.TEACHER_BACKEND == "api" and bool(config.ANTHROPIC_API_KEY)


def _node_by_idx(numbered: list[dict], idx: object) -> Optional[dict]:
    """Look up a numbered node by the index the model referenced.

    Args:
        numbered: The numbered node list (grows as the agent expands).
        idx: Whatever the model passed as an index — non-integers (including
            bools) resolve to None rather than raising.

    Returns:
        The node dict, or None when the index doesn't resolve.
    """
    if not isinstance(idx, int) or isinstance(idx, bool):
        return None
    for n in numbered:
        if n.get("idx") == idx:
            return n
    return None


def _paper_text(node: dict, detail: str) -> str:
    """Assemble the text handed back to the agent for one paper read.

    Neighbor nodes arrive without abstract/tldr, so those are hydrated from
    S2 on demand. A ``detail='full'`` read pulls the ar5iv full text
    (truncated to ``FULLTEXT_MAX_CHARS``) when the paper has an arXiv id and
    a render; otherwise it degrades to the summary form.

    Args:
        node: The numbered node being read.
        detail: ``"summary"`` (title + TL;DR + abstract) or ``"full"``.

    Returns:
        The formatted paper text for the tool result.

    Raises:
        s2.S2Error: When on-demand hydration fails after retries.
    """
    title = node.get("title") or "(untitled)"
    year = node.get("year")
    arxiv_id = node.get("arxiv_id")
    abstract = node.get("abstract")
    tldr = node.get("tldr")
    # Neighbor nodes arrive without abstract/tldr — hydrate on demand.
    if abstract is None and tldr is None:
        lookup = f"ARXIV:{arxiv_id}" if arxiv_id else node.get("id")
        hydrated = s2.get_paper(lookup) if lookup else None
        if hydrated:
            abstract = hydrated.get("abstract")
            tldr = hydrated.get("tldr")

    header = f"Title: {title}" + (f" ({year})" if year else "")
    if detail == "full" and arxiv_id:
        ft = fulltext.get_fulltext(arxiv_id)
        if ft.get("available") and ft.get("text"):
            body = ft["text"][: config.FULLTEXT_MAX_CHARS]
            tail = "\n\n[...truncated]" if len(ft["text"]) > config.FULLTEXT_MAX_CHARS else ""
            figs = _figure_list(arxiv_id, node.get("idx"))
            return f"{header}\nTL;DR: {tldr or '—'}\n\nFull text:\n{body}{tail}{figs}"

    parts = [header]
    if tldr:
        parts.append(f"TL;DR: {tldr}")
    parts.append(f"Abstract: {abstract}" if abstract else "Abstract: (unavailable)")
    if detail == "full" and not arxiv_id:
        parts.append("(No arXiv full text for this paper — summary only.)")
    return "\n".join(parts)


def _figure_list(arxiv_id: str, idx: object) -> str:
    """List a read paper's figures so the agent can ``show_figure`` the right one.

    Args:
        arxiv_id: The paper's arXiv id (its figures come from ar5iv).
        idx: The paper's ``[n]`` index, echoed into the show_figure hint.

    Returns:
        A numbered "Figures" block (caption per figure) to append to a full
        read, or an empty string when the paper has no ar5iv figures (or the
        fetch fails — never raised, figures are a nicety, not the read).
    """
    try:
        res = figures_mod.get_figures(arxiv_id)
    except Exception:
        log.warning("figure list fetch failed for %s", arxiv_id, exc_info=True)
        return ""
    figs = res.get("figures") or []
    if not figs:
        return ""
    lines = [f"{i}. {(f.get('caption') or '(no caption)')[:200]}" for i, f in enumerate(figs, 1)]
    return (
        f"\n\nFigures (show one with show_figure(index={idx}, figure=N)):\n" + "\n".join(lines)
    )


def _run_show_figure(
    block, numbered: list[dict], shown: set, budget: dict
) -> tuple[str, dict, Optional[dict]]:
    """Execute a ``show_figure`` tool call — attach a paper's figure to the answer.

    Args:
        block: The tool_use content block (``input`` carries ``index`` and the
            1-based ``figure`` number).
        numbered: The numbered node list.
        shown: Mutable visited set of ``(node id, figure number)`` — a repeat
            show is a no-op (no budget spent, no duplicate image).
        budget: Mutable ``{"left": int}`` figure budget (decremented here).

    Returns:
        ``(tool_result_text, trace, figure)`` — ``figure`` is
        ``{image, caption, title, index, figure}`` for the frontend to render
        inline (``image`` is the same-origin proxy URL), or None when nothing
        was attached (invalid index/number, no arXiv id, no ar5iv figures,
        budget spent, or a repeat — all reported in the text, never raised).
    """
    inp = getattr(block, "input", None) or {}
    idx = inp.get("index")
    num = inp.get("figure")
    node = _node_by_idx(numbered, idx)
    fail = {"action": "figure", "ok": False, "index": idx, "title": None, "figure": num}
    if node is None or not isinstance(num, int) or isinstance(num, bool) or num < 1:
        return (f"Invalid show_figure call (index={idx}, figure={num}).", fail, None)

    title = node.get("title")
    fail["title"] = title
    arxiv_id = node.get("arxiv_id")
    if not arxiv_id:
        return (f'"{title}" has no arXiv figures to show.', fail, None)
    if budget["left"] <= 0:
        return ("Figure budget spent — answer with the figures already shown.", fail, None)

    key = (node.get("id"), num)
    if key in shown:
        return (f'Figure {num} of "{title}" is already shown.',
                {"action": "figure", "ok": True, "index": idx, "title": title, "figure": num}, None)

    try:
        res = figures_mod.get_figures(arxiv_id)
    except Exception as exc:
        log.exception("show_figure fetch failed")
        return (f"Couldn't fetch figures for \"{title}\": {exc}", fail, None)
    figs = res.get("figures") or []
    if not figs:
        return (f'"{title}" has no figures on ar5iv.', fail, None)
    if num > len(figs):
        return (f'"{title}" has only {len(figs)} figure(s); {num} doesn\'t exist.', fail, None)

    shown.add(key)
    budget["left"] -= 1
    fig = figs[num - 1]
    proxy = "/api/figure_proxy?src=" + urllib.parse.quote(fig["image"], safe="")
    payload = {
        "image": proxy,
        "caption": fig.get("caption") or "",
        "title": title,
        "index": idx,
        "figure": num,
    }
    trace = {"action": "figure", "ok": True, "index": idx, "title": title, "figure": num}
    return (f'Attached Figure {num} of "{title}" to your answer.', trace, payload)


def _run_read(block, numbered: list[dict], budgets: dict, read_cache: dict) -> tuple[str, dict, Optional[str]]:
    """Execute a ``read_paper`` tool call.

    A full read downgrades to summary when the full budget is spent; repeat
    reads of the same (paper, detail) come from ``read_cache`` without
    consuming budget.

    Args:
        block: The tool_use content block (its ``input`` carries ``index``
            and ``detail``).
        numbered: The numbered node list.
        budgets: Mutable ``{"full": int, "summary": int}`` remaining-read
            counters (decremented here).
        read_cache: Mutable ``(node id, detail) -> text`` cache.

    Returns:
        ``(tool_result_text, trace, node_id)`` — ``node_id`` is the paper
        that was (or was attempted to be) read, for the cited list; None for
        an invalid index.
    """
    inp = getattr(block, "input", None) or {}
    idx = inp.get("index")
    detail = "full" if inp.get("detail") == "full" else "summary"
    node = _node_by_idx(numbered, idx)
    if node is None:
        return (f"No paper at index {idx}.", {"action": "read", "ok": False, "index": idx, "title": None, "detail": detail}, None)

    title = node.get("title")
    # Downgrade a full read to summary when the full budget is spent.
    if detail == "full" and budgets["full"] <= 0:
        detail = "summary"
    if budgets[detail] <= 0:
        return (
            "Read budget exhausted — answer now with what you've already gathered.",
            {"action": "read", "ok": False, "index": idx, "title": title, "detail": detail},
            node.get("id"),
        )

    ck = (node.get("id"), detail)
    if ck in read_cache:
        text = read_cache[ck]
    else:
        text = _paper_text(node, detail)
        read_cache[ck] = text
        budgets[detail] -= 1
    return (text, {"action": "read", "ok": True, "index": idx, "title": title, "detail": detail}, node.get("id"))


def _run_expand(
    block,
    numbered: list[dict],
    known_ids: set[str],
    expanded: set[tuple[str, str]],
    hops: dict,
) -> tuple[str, dict, Optional[dict]]:
    """Execute an ``expand_node`` tool call.

    Pulls one hop of neighbors for a paper already numbered and appends any
    new ones to ``numbered`` (mutated in place) so the agent can read them
    next turn. A visited (paper, relation) set kills repeat traversal.

    Args:
        block: The tool_use content block (``input`` carries ``index`` and
            ``relation``).
        numbered: The numbered node list (appended to in place).
        known_ids: Mutable set of every node id already on the graph.
        expanded: Mutable visited set of ``(paper_id, relation)`` pairs.
        hops: Mutable ``{"left": int}`` expansion budget (decremented here).

    Returns:
        ``(tool_result_text, trace, discovery)`` — ``discovery`` is
        ``{"nodes": [...], "edges": [...]}`` for the frontend to merge into
        the live graph, or None when nothing new came back (invalid call,
        budget spent, repeat expansion, or an S2 failure — all reported in
        the text, never raised).
    """
    inp = getattr(block, "input", None) or {}
    idx = inp.get("index")
    relation = inp.get("relation")
    node = _node_by_idx(numbered, idx)
    if node is None or relation not in _REL_TAG:
        return (
            f"Invalid expand_node call (index={idx}, relation={relation!r}).",
            {"action": "expand", "ok": False, "index": idx, "title": None, "relation": relation},
            None,
        )

    title = node.get("title")
    paper_id = node["id"]
    if hops["left"] <= 0:
        return (
            "Expansion budget exhausted — work with what's already on the graph.",
            {"action": "expand", "ok": False, "index": idx, "title": title, "relation": relation},
            None,
        )

    key = (paper_id, relation)
    if key in expanded:
        return (
            f"Already expanded {relation} of \"{title}\" — see the numbered papers above.",
            {"action": "expand", "ok": True, "index": idx, "title": title, "relation": relation, "found": 0},
            None,
        )
    expanded.add(key)
    hops["left"] -= 1

    rel_tag = _REL_TAG[relation]
    try:
        hits = _s2_neighbors(paper_id, relation)
    except s2.S2Error as exc:
        return (
            f"Couldn't expand {relation} of \"{title}\": {exc}",
            {"action": "expand", "ok": False, "index": idx, "title": title, "relation": relation},
            None,
        )

    new_nodes: list[dict] = []
    new_edges: list[dict] = []
    lines: list[str] = []
    next_idx = numbered[-1]["idx"] + 1
    for hit in hits:
        n = hit["node"]
        nid = n["id"]
        if nid == paper_id:
            continue
        if rel_tag == "reference":
            edge = {"source": paper_id, "target": nid, "type": "reference", "influential": hit.get("influential", False)}
        elif rel_tag == "citation":
            edge = {"source": nid, "target": paper_id, "type": "citation", "influential": hit.get("influential", False)}
        else:
            edge = {"source": paper_id, "target": nid, "type": "similar"}
        new_edges.append(edge)

        if nid in known_ids:
            continue
        known_ids.add(nid)
        disc = dict(n)
        disc["rels"] = [rel_tag]
        disc["is_seed"] = False
        disc["discovered"] = True
        disc["idx"] = next_idx
        numbered.append(disc)
        new_nodes.append(disc)
        lines.append(f"[{next_idx}] ({disc.get('year') or 'n.d.'}) {disc.get('title', '')}")
        next_idx += 1

    if not lines:
        text = f"No new papers — {relation} of \"{title}\" is already on the graph."
    else:
        text = (
            f"Expanded {relation} of \"{title}\" — {len(lines)} new paper(s) added:\n"
            + "\n".join(lines)
        )
    trace = {"action": "expand", "ok": True, "index": idx, "title": title, "relation": relation, "found": len(lines)}
    discovery = {"nodes": new_nodes, "edges": new_edges} if (new_nodes or new_edges) else None
    return (text, trace, discovery)


def _run_search(
    block,
    numbered: list[dict],
    known_ids: set[str],
    searched: set,
    searches: dict,
) -> tuple[str, dict, Optional[dict]]:
    """Execute a ``search_papers`` tool call.

    Runs an ungrounded free-text S2 search and appends any papers not already
    numbered so the agent can read them. Repeat searches of the same
    (query, year window) are short-circuited.

    Args:
        block: The tool_use content block (``input`` carries ``query`` and
            optional ``year_from`` / ``year_to``).
        numbered: The numbered node list (appended to in place).
        known_ids: Mutable set of every node id already on the graph.
        searched: Mutable visited set of ``(query, year_from, year_to)``.
        searches: Mutable ``{"left": int}`` search budget (decremented here).

    Returns:
        ``(tool_result_text, trace, discovery)``. Discovery carries only
        nodes — no edges — since a topic search links the hits to no specific
        paper; the frontend anchors them near the seed so they don't fly in
        from the origin. None discovery on an invalid/exhausted/repeat call
        or an S2 failure (reported in the text, never raised).
    """
    inp = getattr(block, "input", None) or {}
    query = (inp.get("query") or "").strip()
    year_from = inp.get("year_from")
    year_to = inp.get("year_to")
    if not query:
        return (
            "Invalid search_papers call (empty query).",
            {"action": "search", "ok": False, "query": query},
            None,
        )
    if searches["left"] <= 0:
        return (
            "Search budget exhausted — answer with what you've found.",
            {"action": "search", "ok": False, "query": query},
            None,
        )

    key = (query.lower(), year_from, year_to)
    if key in searched:
        return (
            f'Already searched "{query}" — see the numbered papers above.',
            {"action": "search", "ok": True, "query": query, "found": 0},
            None,
        )
    searched.add(key)
    searches["left"] -= 1

    try:
        hits = _s2_search(query, year_from, year_to)
    except s2.S2Error as exc:
        return (
            f'Couldn\'t search "{query}": {exc}',
            {"action": "search", "ok": False, "query": query},
            None,
        )

    new_nodes: list[dict] = []
    lines: list[str] = []
    next_idx = numbered[-1]["idx"] + 1
    for hit in hits:
        n = hit["node"]
        nid = n["id"]
        if nid in known_ids:
            continue
        known_ids.add(nid)
        disc = dict(n)
        disc["rels"] = ["search"]
        disc["is_seed"] = False
        disc["discovered"] = True
        disc["idx"] = next_idx
        numbered.append(disc)
        new_nodes.append(disc)
        lines.append(f"[{next_idx}] ({disc.get('year') or 'n.d.'}) {disc.get('title', '')}")
        next_idx += 1

    scope = _search_scope(year_from, year_to)
    if not lines:
        text = f'Search "{query}"{scope} returned nothing new.'
    else:
        text = (
            f'Search "{query}"{scope} — {len(lines)} new paper(s) added:\n'
            + "\n".join(lines)
        )
    trace = {
        "action": "search", "ok": True, "query": query, "found": len(lines),
        "year_from": year_from, "year_to": year_to,
    }
    discovery = {"nodes": new_nodes, "edges": []} if new_nodes else None
    return (text, trace, discovery)


def _sources_context(library: list[dict]) -> str:
    """Render the user's uploaded sources for the agent's context.

    Args:
        library: Source records from ``library.sources.list_sources``.

    Returns:
        A compact "Your library" listing (id, title, size) so the agent knows
        what it can search and can scope ``search_sources`` by id.
    """
    lines = []
    for s in library:
        loc = f"{s['pages']}pp" if s.get("pages") else s.get("kind", "")
        lines.append(f"- [{s['id']}] \"{s['title']}\" ({loc})")
    return "Your library (search with search_sources):\n" + "\n".join(lines)


def _run_search_sources(
    block, source_searches: dict, scope: Optional[list[str]] = None
) -> tuple[str, dict]:
    """Execute a ``search_sources`` tool call.

    Semantic search over the user's own uploaded library. No graph discovery
    — source passages aren't graph nodes; the agent cites them inline by
    page.

    Args:
        block: The tool_use content block (``input`` carries ``query`` and
            optional ``source_id``).
        source_searches: Mutable ``{"left": int}`` budget (decremented here).
        scope: The user-selected subset of source ids the whole answer is
            pinned to. When set it overrides the agent's own ``source_id``, so
            the search can't stray outside the chosen sources; None lets the
            agent choose one source (or search the whole library).

    Returns:
        ``(tool_result_text, trace)``. Failures (empty query, spent budget,
        or a search exception) are reported in the text, never raised.
    """
    inp = getattr(block, "input", None) or {}
    query = (inp.get("query") or "").strip()
    # A user scope (a present list, even empty) wins; otherwise fall back to the
    # single source_id the agent chose (as a one-element list), or None for the
    # whole library. An empty scope means "no sources" → search returns nothing.
    if scope is not None:
        source_ids: Optional[list[str]] = scope
    else:
        one = inp.get("source_id") or None
        source_ids = [one] if one else None
    if not query:
        return (
            "Invalid search_sources call (empty query).",
            {"action": "search_sources", "ok": False, "query": query},
        )
    if source_searches["left"] <= 0:
        return (
            "Source-search budget exhausted — answer with what you've found.",
            {"action": "search_sources", "ok": False, "query": query},
        )
    source_searches["left"] -= 1
    try:
        hits = sources.search(query, source_ids=source_ids)
    except Exception as exc:
        log.exception("search_sources failed")
        return (
            f"Couldn't search your sources: {exc}",
            {"action": "search_sources", "ok": False, "query": query},
        )
    if not hits:
        return (
            f'No passages in your library matched "{query}".',
            {"action": "search_sources", "ok": True, "query": query, "found": 0},
        )
    trace = {"action": "search_sources", "ok": True, "query": query, "found": len(hits)}
    return (f'Passages from your library for "{query}":\n\n' + _format_passages(hits), trace)
