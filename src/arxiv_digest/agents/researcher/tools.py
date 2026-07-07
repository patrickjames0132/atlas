"""The researcher's model-callable tool surface, plus the run-state (deps) the
tools share.

Every tool follows the old runners' one hard rule: **failures are reported in
the tool-result text, never raised** — a spent budget, an invalid index, or a
failed fetch is information the model steers by ("answer now with what
you've gathered"), not an error that kills the answer. Each tool also pushes
typed events (``Trace`` / ``Discovery`` / ``Figure``) onto the deps queue,
which ``main.answer`` drains into the workflow's event stream so the user
watches the agent work live.

Budgets come from ``config.BUDGETS`` (the agent entry's ``extras``): a total
step cap across all tools, plus per-tool budgets. Visited-sets and the read
cache make repeats free instead of wasteful.
"""

from __future__ import annotations

import logging
import urllib.parse
from dataclasses import dataclass, field
from typing import Literal

from pydantic_ai import RunContext

from ...integrations import semantic_scholar as s2
from ...integrations.arxiv import figures as figures_mod
from ...integrations.arxiv import fulltext
from ...services.graph import Edge, Node
from ...services.sources import retrieval
from .. import events, prompts, traversal
from .config import BUDGETS

log = logging.getLogger(__name__)


@dataclass
class ResearcherDeps:
    """One question's run-state, shared by the loop and every tool.

    ``nodes`` is the numbered list — a paper's index is its position + 1,
    and expansion/search append so new papers take the next indices. The
    ``queue`` is how tool-side happenings (traces, discoveries, figures)
    reach the workflow's event stream: tools push, ``main.answer`` drains
    between run events. (Not named ``events`` — that would shadow the
    ``events`` module inside this class's annotations.)
    """

    nodes: list[Node]
    known_ids: set[str]
    scope: list[str] | None  # user-pinned source_ids; overrides the model's pick
    has_sources: bool
    steps_left: int = 0
    full_reads_left: int = 0
    summary_reads_left: int = 0
    hops_left: int = 0
    searches_left: int = 0
    source_searches_left: int = 0
    figures_left: int = 0
    read_cache: dict[tuple[str, str], str] = field(default_factory=dict)
    expanded: set[tuple[str, str]] = field(default_factory=set)
    searched: set[tuple[str, int | None, int | None]] = field(default_factory=set)
    figures_shown: dict[tuple[str, int], int] = field(default_factory=dict)
    cited_ids: list[str] = field(default_factory=list)
    queue: list[events.Event] = field(default_factory=list)

    def emit(self, event: events.Event) -> None:
        self.queue.append(event)

    def drain(self) -> list[events.Event]:
        queued, self.queue = self.queue, []
        return queued


STEPS_EXHAUSTED = "Step budget exhausted — answer now with what you've gathered."


def _spend_step(deps: ResearcherDeps) -> bool:
    """Charge the total step budget; False when it's already spent."""
    if deps.steps_left <= 0:
        return False
    deps.steps_left -= 1
    return True


def _node_at(deps: ResearcherDeps, index: int) -> Node | None:
    """The numbered-list node for a model-given 1-based index, or None."""
    if 1 <= index <= len(deps.nodes):
        return deps.nodes[index - 1]
    return None


def _record_cited(deps: ResearcherDeps, node_id: str) -> None:
    if node_id not in deps.cited_ids:
        deps.cited_ids.append(node_id)


def _figure_list(arxiv_id: str, index: int) -> str:
    """A full read's "Figures" block, so the model can show_figure the right
    one. Empty on no figures or a failed fetch — figures are a nicety, not
    the read."""
    try:
        result = figures_mod.get_figures(arxiv_id)
    except Exception:
        log.warning("figure list fetch failed for %s", arxiv_id, exc_info=True)
        return ""
    figs = result.get("figures") or []
    if not figs:
        return ""
    lines = [
        f"{number}. {(figure.get('caption') or '(no caption)')[:200]}"
        for number, figure in enumerate(figs, 1)
    ]
    return (
        f"\n\nFigures (show one with show_figure(index={index}, figure=N)):\n"
        + "\n".join(lines)
    )


def _paper_text(node: Node, detail: str, index: int) -> str:
    """The text handed back for one paper read.

    Discovered neighbors arrive without abstract/tldr, so those hydrate from
    S2 on demand. A full read pulls the ar5iv full text (truncated to the
    ``fulltext_max_chars`` budget) when the paper has an arXiv render;
    otherwise it degrades to the summary form with a note.
    """
    abstract, tldr = node.abstract, node.tldr
    if abstract is None and tldr is None:
        lookup = f"ARXIV:{node.arxiv_id}" if node.arxiv_id else node.id
        hydrated = s2.get_paper(lookup)
        if hydrated:
            abstract = hydrated.get("abstract")
            tldr = hydrated.get("tldr")

    header = f"Title: {node.title}" + (f" ({node.year})" if node.year else "")
    if detail == "full" and node.arxiv_id:
        text = fulltext.get_fulltext(node.arxiv_id)
        if text.get("available") and text.get("text"):
            limit = BUDGETS["fulltext_max_chars"]
            body = text["text"][:limit]
            tail = "\n\n[...truncated]" if len(text["text"]) > limit else ""
            figs = _figure_list(node.arxiv_id, index)
            return f"{header}\nTL;DR: {tldr or '—'}\n\nFull text:\n{body}{tail}{figs}"

    parts = [header]
    if tldr:
        parts.append(f"TL;DR: {tldr}")
    parts.append(f"Abstract: {abstract}" if abstract else "Abstract: (unavailable)")
    if detail == "full" and not node.arxiv_id:
        parts.append("(No arXiv full text for this paper — summary only.)")
    return "\n".join(parts)


def read_paper(
    ctx: RunContext[ResearcherDeps], index: int, detail: Literal["summary", "full"]
) -> str:
    """Read one of the numbered papers to ground your answer.

    Args:
        index: The [n] index of the paper from the numbered list.
        detail: "summary" for its abstract + TL;DR (cheap); "full" for the
            full text via ar5iv — use sparingly, it has a smaller budget. A
            full read also lists the paper's figures for show_figure.
    """
    deps = ctx.deps
    node = _node_at(deps, index)
    if node is None:
        deps.emit(events.ReadTrace(ok=False, index=index, title=None, detail=detail))
        return f"No paper at index {index}."
    if not _spend_step(deps):
        deps.emit(events.ReadTrace(ok=False, index=index, title=node.title, detail=detail))
        return STEPS_EXHAUSTED

    # A full read downgrades to summary when the full budget is spent.
    if detail == "full" and deps.full_reads_left <= 0:
        detail = "summary"
    budget_attr = "full_reads_left" if detail == "full" else "summary_reads_left"
    if getattr(deps, budget_attr) <= 0:
        deps.emit(events.ReadTrace(ok=False, index=index, title=node.title, detail=detail))
        _record_cited(deps, node.id)
        return "Read budget exhausted — answer now with what you've already gathered."

    cache_key = (node.id, detail)
    if cache_key in deps.read_cache:
        text = deps.read_cache[cache_key]
    else:
        text = _paper_text(node, detail, index)
        deps.read_cache[cache_key] = text
        setattr(deps, budget_attr, getattr(deps, budget_attr) - 1)
    deps.emit(events.ReadTrace(ok=True, index=index, title=node.title, detail=detail))
    _record_cited(deps, node.id)
    return text


def expand_node(ctx: RunContext[ResearcherDeps], index: int, relation: traversal.Relation) -> str:
    """Pull one hop of neighbors for a numbered paper and add them to the
    graph as new numbered papers you can then read.

    Args:
        index: The [n] index of the paper to expand from.
        relation: "references" (papers it cites), "citations" (papers citing
            it), or "similar" (embedding-similar work).
    """
    deps = ctx.deps
    node = _node_at(deps, index)
    if node is None:
        deps.emit(events.ExpandTrace(ok=False, index=index, title=None, relation=relation))
        return f"No paper at index {index}."
    if not _spend_step(deps):
        deps.emit(events.ExpandTrace(ok=False, index=index, title=node.title, relation=relation))
        return STEPS_EXHAUSTED
    if deps.hops_left <= 0:
        deps.emit(events.ExpandTrace(ok=False, index=index, title=node.title, relation=relation))
        return "Expansion budget exhausted — work with what's already on the graph."

    visit_key = (node.id, relation)
    if visit_key in deps.expanded:
        deps.emit(
            events.ExpandTrace(ok=True, index=index, title=node.title, relation=relation, found=0)
        )
        return f'Already expanded {relation} of "{node.title}" — see the numbered papers above.'
    deps.expanded.add(visit_key)
    deps.hops_left -= 1

    try:
        hits = traversal.neighbors(node.id, relation, BUDGETS["expand_limit"])
    except s2.S2Error as exc:
        deps.emit(events.ExpandTrace(ok=False, index=index, title=node.title, relation=relation))
        return f'Couldn\'t expand {relation} of "{node.title}": {exc}'

    rel_tag = traversal.REL_TAG[relation]
    new_nodes: list[events.DiscoveredNode] = []
    new_edges: list[Edge] = []
    lines: list[str] = []
    for hit in hits:
        neighbor = hit["node"]
        neighbor_id = neighbor["id"]
        if neighbor_id == node.id:
            continue
        # Direction encodes citation semantics, same rules as build_graph:
        # reference = expanded paper cites neighbor; citation = neighbor cites it.
        if rel_tag == "reference":
            edge = Edge(source=node.id, target=neighbor_id, type="reference",
                        influential=hit.get("influential", False))
        elif rel_tag == "citation":
            edge = Edge(source=neighbor_id, target=node.id, type="citation",
                        influential=hit.get("influential", False))
        else:
            edge = Edge(source=node.id, target=neighbor_id, type="similar")
        new_edges.append(edge)

        if neighbor_id in deps.known_ids:
            continue
        deps.known_ids.add(neighbor_id)
        discovered = events.DiscoveredNode(
            **neighbor, rels=[rel_tag], is_seed=False, idx=len(deps.nodes) + 1
        )
        deps.nodes.append(discovered)
        new_nodes.append(discovered)
        lines.append(f"[{discovered.idx}] ({discovered.year or 'n.d.'}) {discovered.title}")

    deps.emit(
        events.ExpandTrace(
            ok=True, index=index, title=node.title, relation=relation, found=len(lines)
        )
    )
    if new_nodes or new_edges:
        deps.emit(events.Discovery(nodes=new_nodes, edges=new_edges))
    if not lines:
        return f'No new papers — {relation} of "{node.title}" is already on the graph.'
    return (
        f'Expanded {relation} of "{node.title}" — {len(lines)} new paper(s) added:\n'
        + "\n".join(lines)
    )


def search_papers(
    ctx: RunContext[ResearcherDeps],
    query: str,
    year_from: int | None = None,
    year_to: int | None = None,
) -> str:
    """Free-text search across all of Semantic Scholar — NOT limited to the
    graph's citation neighborhood. Use for recent or topical work that
    expand_node can't reach; hits get numbered and added for you to read.

    Args:
        query: Free-text query — keywords or a topic, not an id.
        year_from: Earliest publication year (inclusive). Omit for no floor.
        year_to: Latest publication year (inclusive). Omit for no ceiling.
    """
    deps = ctx.deps
    query = query.strip()
    if not query:
        deps.emit(events.SearchTrace(ok=False, query=query))
        return "Invalid search_papers call (empty query)."
    if not _spend_step(deps):
        deps.emit(events.SearchTrace(ok=False, query=query))
        return STEPS_EXHAUSTED
    if deps.searches_left <= 0:
        deps.emit(events.SearchTrace(ok=False, query=query))
        return "Search budget exhausted — answer with what you've found."

    visit_key = (query.lower(), year_from, year_to)
    if visit_key in deps.searched:
        deps.emit(events.SearchTrace(ok=True, query=query, found=0))
        return f'Already searched "{query}" — see the numbered papers above.'
    deps.searched.add(visit_key)
    deps.searches_left -= 1

    try:
        hits = traversal.search(query, BUDGETS["search_limit"], year_from, year_to)
    except s2.S2Error as exc:
        deps.emit(events.SearchTrace(ok=False, query=query))
        return f'Couldn\'t search "{query}": {exc}'

    new_nodes = []
    lines = []
    for hit in hits:
        found = hit["node"]
        if found["id"] in deps.known_ids:
            continue
        deps.known_ids.add(found["id"])
        discovered = events.DiscoveredNode(
            **found, rels=["search"], is_seed=False, idx=len(deps.nodes) + 1
        )
        deps.nodes.append(discovered)
        new_nodes.append(discovered)
        lines.append(f"[{discovered.idx}] ({discovered.year or 'n.d.'}) {discovered.title}")

    deps.emit(
        events.SearchTrace(
            ok=True, query=query, found=len(lines), year_from=year_from, year_to=year_to
        )
    )
    if new_nodes:
        # No edges: a topic search links its hits to no specific paper.
        deps.emit(events.Discovery(nodes=new_nodes, edges=[]))
        window = f" ({year_from or ''}–{year_to or ''})" if (year_from or year_to) else ""
        return f'Search "{query}"{window} — {len(lines)} new paper(s) added:\n' + "\n".join(lines)
    return f'Search "{query}" returned nothing new.'


def show_figure(ctx: RunContext[ResearcherDeps], index: int, figure: int) -> str:
    """Place one of a paper's own figures (image + caption, from ar5iv) into
    your answer. Only for a paper you've read in full — the full read lists
    its figures. The result gives you a <<FIG n>> marker: put it on its own
    line in your prose exactly where the figure belongs.

    Args:
        index: The [n] index of the paper the figure comes from.
        figure: The figure's number as listed in the full read (1-based).
    """
    deps = ctx.deps
    node = _node_at(deps, index)
    if node is None or figure < 1:
        deps.emit(events.FigureTrace(ok=False, index=index, title=None, figure=figure))
        return f"Invalid show_figure call (index={index}, figure={figure})."
    if not _spend_step(deps):
        deps.emit(events.FigureTrace(ok=False, index=index, title=node.title, figure=figure))
        return STEPS_EXHAUSTED
    if not node.arxiv_id:
        deps.emit(events.FigureTrace(ok=False, index=index, title=node.title, figure=figure))
        return f'"{node.title}" has no arXiv figures to show.'
    if deps.figures_left <= 0:
        deps.emit(events.FigureTrace(ok=False, index=index, title=node.title, figure=figure))
        return "Figure budget spent — answer with the figures already shown."

    shown_key = (node.id, figure)
    if shown_key in deps.figures_shown:
        deps.emit(events.FigureTrace(ok=True, index=index, title=node.title, figure=figure))
        return (
            f'Figure {figure} of "{node.title}" is already shown — its marker is '
            f"<<FIG {deps.figures_shown[shown_key]}>>."
        )

    try:
        result = figures_mod.get_figures(node.arxiv_id)
    except Exception as exc:
        log.exception("show_figure fetch failed")
        deps.emit(events.FigureTrace(ok=False, index=index, title=node.title, figure=figure))
        return f'Couldn\'t fetch figures for "{node.title}": {exc}'
    figs = result.get("figures") or []
    if not figs:
        deps.emit(events.FigureTrace(ok=False, index=index, title=node.title, figure=figure))
        return f'"{node.title}" has no figures on ar5iv.'
    if figure > len(figs):
        deps.emit(events.FigureTrace(ok=False, index=index, title=node.title, figure=figure))
        return f'"{node.title}" has only {len(figs)} figure(s); {figure} doesn\'t exist.'

    slot = len(deps.figures_shown) + 1
    deps.figures_shown[shown_key] = slot
    deps.figures_left -= 1
    chosen = figs[figure - 1]
    deps.emit(events.FigureTrace(ok=True, index=index, title=node.title, figure=figure))
    deps.emit(
        events.Figure(
            # Same-origin proxy — the frontend can't hotlink ar5iv directly.
            image="/api/figure_proxy?src=" + urllib.parse.quote(chosen["image"], safe=""),
            caption=chosen.get("caption") or "",
            title=node.title,
            index=index,
            figure=figure,
            slot=slot,
        )
    )
    return (
        f'Attached Figure {figure} of "{node.title}" to your answer. Place the '
        f"marker <<FIG {slot}>> on its own line in your prose at exactly the "
        f"point where this figure belongs."
    )


def search_sources(ctx: RunContext[ResearcherDeps], query: str, source_id: str | None = None) -> str:
    """Semantic search over the student's OWN uploaded sources (books, PDFs,
    web pages) — not the citation graph. Returns the most relevant passages
    with source title and page; attribute them inline in your prose.

    Args:
        query: What to look for — a concept or question, not an id.
        source_id: Restrict to one source's id from "Your library" (optional).
    """
    deps = ctx.deps
    query = query.strip()
    if not query:
        deps.emit(events.SourceSearchTrace(ok=False, query=query))
        return "Invalid search_sources call (empty query)."
    if not _spend_step(deps):
        deps.emit(events.SourceSearchTrace(ok=False, query=query))
        return STEPS_EXHAUSTED
    if deps.source_searches_left <= 0:
        deps.emit(events.SourceSearchTrace(ok=False, query=query))
        return "Source-search budget exhausted — answer with what you've found."
    deps.source_searches_left -= 1

    # A user-pinned scope wins over the model's own pick, so the search can't
    # stray outside the chosen sources.
    if deps.scope is not None:
        source_ids: list[str] | None = deps.scope
    else:
        source_ids = [source_id] if source_id else None
    try:
        hits = retrieval.search(query, source_ids=source_ids)
    except Exception as exc:
        log.exception("search_sources failed")
        deps.emit(events.SourceSearchTrace(ok=False, query=query))
        return f"Couldn't search your sources: {exc}"

    deps.emit(events.SourceSearchTrace(ok=True, query=query, found=len(hits)))
    if not hits:
        return f'No passages in your library matched "{query}".'
    return f'Passages from your library for "{query}":\n\n' + prompts.format_passages(hits)
