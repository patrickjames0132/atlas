"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
The researcher's model-callable tool surface, plus the run-state (deps) the
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

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

import logging
import urllib.parse
from dataclasses import dataclass, field
from typing import Literal

from pydantic_ai import RunContext

from ....integrations import openalex
from ....integrations import semantic_scholar as s2
from ....integrations.arxiv import figures as figures_mod
from ....integrations.arxiv import fulltext
from ....services import pdf as pdf_service
from ....services.graph import Edge, Node, Provider
from ....services.sources import retrieval
from ... import captions, events, library_figures, prompts, traversal
from ...workers.search import papers, web
from .config import BUDGETS

# A hop or search can fail on either provider's client; both come back to the
# model as steerable text, never raised.
_TRAVERSAL_ERRORS = (s2.S2Error, openalex.OpenAlexError)

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
    #: The numbered library ``[Sn]`` markers and the source tools index into —
    #: the same list ``prompts.source_lines`` renders into the prompt, so a
    #: citation and a tool call can't disagree about which source ``S3`` is.
    sources: list[dict] = field(default_factory=list)
    provider: Provider = "s2"  # the graph provider — expand/search/hydrate follow it
    #: Whether the web scout is on this run at all. False turns the tool off
    #: AND takes the web out of the coverage guard's reckoning — availability
    #: is one fact, and both consumers must read the same one or the guard
    #: demands a source the model has no way to reach.
    web_enabled: bool = False
    steps_left: int = 0
    full_reads_left: int = 0
    summary_reads_left: int = 0
    hops_left: int = 0
    searches_left: int = 0
    web_searches_left: int = 0
    source_searches_left: int = 0
    figures_left: int = 0
    read_cache: dict[tuple[str, str], str] = field(default_factory=dict)
    expanded: set[tuple[str, str]] = field(default_factory=set)
    #: Needs already handed to a scout, lower-cased. Keyed by the *need* now
    #: rather than by (query, year_from, year_to): the researcher no longer
    #: writes queries — the scout does, and it may write several per need.
    searched: set[str] = field(default_factory=set)
    web_searched: set[str] = field(default_factory=set)
    figures_shown: dict[tuple[str, int], int] = field(default_factory=dict)
    cited_ids: list[str] = field(default_factory=list)
    queue: list[events.Event] = field(default_factory=list)
    #: How many times ``search_sources`` actually reached retrieval this run,
    #: and how many passages came back in total. Both are *observed facts*, not
    #: model self-report — they drive the "did it look?" output guard and the
    #: derived provenance the UI shows. A run with ``searches_run`` at 0 never
    #: consulted the student's library, whatever the answer claims.
    source_searches_run: int = 0
    source_hits: int = 0
    #: How many times ``find_papers`` ran a scout. Counted for the
    #: same reason: an answer that went to Semantic Scholar and an answer that
    #: came from the model's own weights are very different things to report,
    #: and without this they were indistinguishable in the provenance record.
    paper_searches_run: int = 0
    #: The same observed-fact counters for the web, kept separate because
    #: "went to the literature" and "went to the web" are different claims
    #: about an answer's footing (see ``events.Provenance``).
    web_searches_run: int = 0
    web_pages_found: int = 0

    def source_id(self, number: int) -> str | None:
        """Resolve a model-written ``[Sn]`` index to a real source id.

        Args:
            number: The 1-based index as the model wrote it.

        Returns:
            The source id, or None when the index is out of range (a
            hallucinated number comes back to the model as text, not a raise).
        """
        if 1 <= number <= len(self.sources):
            return str(self.sources[number - 1]["id"])
        return None

    def emit(self, event: events.Event) -> None:
        """Queue a trace/discovery event for the stream bridge to flush.

        Args:
            event: The typed event to queue.
        """
        self.queue.append(event)

    def drain(self) -> list[events.Event]:
        """Take (and clear) everything queued since the last drain.

        Returns:
            The queued events, oldest first.
        """
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


def _oa_pdf_url(node: Node, provider: Provider) -> str | None:
    """The paper's open-access PDF URL, cheapest source first.

    An arXiv id needs no lookup (``arxiv.org/pdf`` is always OA); a hydrated
    node may carry ``oa_pdf`` already; otherwise the shared resolver asks the
    graph's provider (cached).

    Args:
        node: The numbered-list node.
        provider: The graph's academic-data backend.

    Returns:
        The URL, or None when the paper has no known OA PDF.
    """
    if node.arxiv_id:
        return pdf_service.arxiv_pdf_url(node.arxiv_id)
    if node.oa_pdf:
        return node.oa_pdf
    return pdf_service.resolve_oa_pdf(node.id, provider)


def _node_figures(node: Node, provider: Provider) -> list[dict]:
    """The paper's showable figures, as ``{"image", "caption"}`` dicts.

    One list, one numbering — ``_figure_list`` prints it and ``show_figure``
    indexes into it, so the number the model reads is always the figure it
    gets. ar5iv figures (with their real captions) when the paper has a
    render; otherwise floats mined from its open-access PDF — figures,
    tables, and algorithm boxes alike. Image URLs come back ready for the
    browser (same-origin proxy / PDF-figure route). Empty on any failure —
    figures are a nicety, not the read.

    Args:
        node: The numbered-list node.
        provider: The graph's academic-data backend.

    Returns:
        The figure dicts, in display order.
    """
    if node.arxiv_id:
        try:
            result = figures_mod.get_figures(node.arxiv_id)
        except Exception:
            log.warning("figure list fetch failed for %s", node.arxiv_id, exc_info=True)
            result = {}
        figs = result.get("figures") or []
        if figs:
            return [
                {
                    "image": "/api/figure_proxy?src="
                    + urllib.parse.quote(figure["image"], safe=""),
                    "caption": figure.get("caption") or "",
                }
                for figure in figs
            ]
    url = _oa_pdf_url(node, provider)
    if not url:
        return []
    try:
        mined = pdf_service.get_pdf_floats(url)
    except Exception:
        log.warning("PDF float mining failed for %s", node.id, exc_info=True)
        return []
    token = mined.get("token")
    return [
        {
            "image": f"/api/pdf_figure/{token}/{position}",
            "caption": entry.get("caption") or "",
        }
        for position, entry in enumerate(mined.get("floats") or [])
    ]


def _figure_list(node: Node, provider: Provider, index: int) -> str:
    """A full read's "Figures" block, so the model can show_figure the right
    one. Empty when the paper has none extractable — figures are a nicety,
    not the read.
    """
    figs = _node_figures(node, provider)
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


def _paper_text(node: Node, detail: str, index: int, provider: Provider) -> str:
    """The text handed back for one paper read.

    Discovered neighbors arrive without abstract/tldr, so those hydrate on
    demand — from the graph's provider (OpenAlex fills the abstract from its
    inverted index; it has no TL;DR). A full read tries the ar5iv render
    first, then falls back to the paper's open-access PDF (journal papers,
    and the arXiv papers ar5iv couldn't convert) — either way truncated to
    the ``fulltext_max_chars`` budget. Only when neither exists does it
    degrade to the summary form with a note.
    """
    abstract, tldr = node.abstract, node.tldr
    if abstract is None and tldr is None:
        if provider == "openalex":
            hydrated = openalex.get_paper(node.id)
        else:
            lookup = f"ARXIV:{node.arxiv_id}" if node.arxiv_id else node.id
            hydrated = s2.get_paper(lookup)
        if hydrated:
            abstract = hydrated.get("abstract")
            tldr = hydrated.get("tldr")
            if not node.oa_pdf and hydrated.get("oa_pdf"):
                node.oa_pdf = hydrated["oa_pdf"]

    header = f"Title: {node.title}" + (f" ({node.year})" if node.year else "")
    if detail == "full":
        limit = BUDGETS["fulltext_max_chars"]
        if node.arxiv_id:
            text = fulltext.get_fulltext(node.arxiv_id)
            if text.get("available") and text.get("text"):
                body = text["text"][:limit]
                tail = "\n\n[...truncated]" if len(text["text"]) > limit else ""
                figs = _figure_list(node, provider, index)
                return f"{header}\nTL;DR: {tldr or '—'}\n\nFull text:\n{body}{tail}{figs}"
        oa_url = _oa_pdf_url(node, provider)
        if oa_url:
            pdf_text = pdf_service.get_pdf_text(oa_url)
            if pdf_text.get("available") and pdf_text.get("text"):
                body = pdf_text["text"][:limit]
                tail = "\n\n[...truncated]" if len(pdf_text["text"]) > limit else ""
                figs = _figure_list(node, provider, index)
                return (
                    f"{header}\nTL;DR: {tldr or '—'}\n\n"
                    f"Full text (extracted from the paper's PDF):\n{body}{tail}{figs}"
                )

    parts = [header]
    if tldr:
        parts.append(f"TL;DR: {tldr}")
    parts.append(f"Abstract: {abstract}" if abstract else "Abstract: (unavailable)")
    if detail == "full":
        parts.append("(No full text available for this paper — summary only.)")
    return "\n".join(parts)


def read_paper(
    ctx: RunContext[ResearcherDeps], index: int, detail: Literal["summary", "full"]
) -> str:
    """Read one of the numbered papers to ground your answer.

    Args:
        ctx: The run context carrying the researcher's deps (framework-injected).
        index: The [n] index of the paper from the numbered list.
        detail: "summary" for its abstract + TL;DR (cheap); "full" for the
            full text — from ar5iv, or extracted from the paper's open-access
            PDF when there's no arXiv render — use sparingly, it has a
            smaller budget. A full read also lists the paper's figures (and
            for PDF-mined papers, tables and algorithms) for show_figure.

    Returns:
        The paper's text — title + TL;DR + abstract (summary), or the full
        text plus its figure list (full) — or a budget/validity message.
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
        text = _paper_text(node, detail, index, deps.provider)
        deps.read_cache[cache_key] = text
        setattr(deps, budget_attr, getattr(deps, budget_attr) - 1)
    deps.emit(events.ReadTrace(ok=True, index=index, title=node.title, detail=detail))
    _record_cited(deps, node.id)
    return text


def expand_node(ctx: RunContext[ResearcherDeps], index: int, relation: traversal.Relation) -> str:
    """Pull one hop of neighbors for a numbered paper and add them to the
    graph as new numbered papers you can then read.

    Args:
        ctx: The run context carrying the researcher's deps (framework-injected).
        index: The [n] index of the paper to expand from.
        relation: "references" (papers it cites), "citations" (papers citing
            it), or "similar" (related work).

    Returns:
        The newly numbered neighbors (title + year each), or a
        budget/validity message.
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
        hits = traversal.neighbors(node.id, relation, BUDGETS["expand_limit"], deps.provider)
    except _TRAVERSAL_ERRORS as exc:
        log.warning("expand_node failed for %r (%s): %s", node.id, relation, exc)
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


async def find_papers(ctx: RunContext[ResearcherDeps], need: str) -> str:
    """Send a scout to find papers across the whole academic corpus — NOT limited
    to the graph's citation neighborhood. Say what you need in your own words,
    including any recency requirement ("work from the last two years on X"); the
    scout writes and re-writes the queries itself and reports back. Whatever it
    finds gets numbered and added for you to read.

    Args:
        ctx: The run context carrying the researcher's deps (framework-injected).
        need: What you're looking for, in plain words — a description, not a
            query string.

    Returns:
        The newly numbered papers (title + year each) plus the scout's own
        account of the search, or a budget/validity message.
    """
    deps = ctx.deps
    need = need.strip()
    if not need:
        deps.emit(events.SearchTrace(ok=False, query=need, reason="empty_query"))
        return "Invalid find_papers call (empty need)."
    if not _spend_step(deps):
        deps.emit(events.SearchTrace(ok=False, query=need, reason="steps_exhausted"))
        return STEPS_EXHAUSTED
    if deps.searches_left <= 0:
        deps.emit(events.SearchTrace(ok=False, query=need, reason="budget_exhausted"))
        return "Search budget exhausted — answer with what you've found."
    if need.lower() in deps.searched:
        deps.emit(events.SearchTrace(ok=True, query=need, found=0))
        return f'Already searched for "{need}" — see the numbered papers above.'
    deps.searched.add(need.lower())
    deps.searches_left -= 1
    deps.paper_searches_run += 1

    result = await papers.scout(need, deps.provider, deps.known_ids)

    # Index assignment happens HERE and nowhere else. The scout returns raw
    # provider nodes precisely so it cannot number them: `[n]` must mean the
    # same paper to the prose, the citation resolver and the frontend, and
    # that invariant only holds while one agent owns the list.
    new_nodes = []
    lines = []
    for found in result.found:
        if found["id"] in deps.known_ids:
            continue
        deps.known_ids.add(found["id"])
        discovered = events.DiscoveredNode(
            **found, rels=["search"], is_seed=False, idx=len(deps.nodes) + 1
        )
        deps.nodes.append(discovered)
        new_nodes.append(discovered)
        lines.append(f"[{discovered.idx}] ({discovered.year or 'n.d.'}) {discovered.title}")

    # The trace shows the scout's LAST query rather than the need: the reader
    # is watching a search happen, and "quantum error correction 2024–" is
    # what a search looks like. The need is the researcher's words, not the
    # search's.
    deps.emit(
        events.SearchTrace(
            ok=True, query=result.queries[-1] if result.queries else need, found=len(lines)
        )
    )
    if new_nodes:
        # No edges: a topic search links its hits to no specific paper.
        deps.emit(events.Discovery(nodes=new_nodes, edges=[]))
        found_text = f"{len(lines)} new paper(s) added:\n" + "\n".join(lines)
    else:
        found_text = "no new papers."
    return f"Scout searched for \"{need}\" — {found_text}\n\nScout's note: {result.summary}"


async def search_web(ctx: RunContext[ResearcherDeps], need: str) -> str:
    """Send a scout to search the open web — announcements, release notes,
    project pages, documentation, benchmarks. Use it for anything where the
    news breaks before the paper does, and for checking whether something
    described in a paper actually shipped. Cite what it returns as inline
    markdown links.

    Args:
        ctx: The run context carrying the researcher's deps (framework-injected).
        need: What you're looking for, in plain words — a description, not a
            query string.

    Returns:
        The scout's summary plus each page it found with its URL, or a
        budget/validity message.
    """
    deps = ctx.deps
    need = need.strip()
    if not need:
        deps.emit(events.WebSearchTrace(ok=False, need=need))
        return "Invalid search_web call (empty need)."
    if not _spend_step(deps):
        deps.emit(events.WebSearchTrace(ok=False, need=need))
        return STEPS_EXHAUSTED
    if deps.web_searches_left <= 0:
        deps.emit(events.WebSearchTrace(ok=False, need=need))
        return "Web-search budget spent — answer with what you've gathered."
    if need.lower() in deps.web_searched:
        deps.emit(events.WebSearchTrace(ok=True, need=need, found=0))
        return f'Already searched the web for "{need}" — see above.'
    deps.web_searched.add(need.lower())
    deps.web_searches_left -= 1
    deps.web_searches_run += 1

    findings = await web.scout(need)
    deps.web_pages_found += len(findings.sources)
    deps.emit(events.WebSearchTrace(ok=True, need=need, found=len(findings.sources)))
    if not findings.sources:
        return f"Web scout found nothing usable. Scout's note: {findings.summary}"
    pages = "\n".join(f"- [{src.title}]({src.url}) — {src.note}" for src in findings.sources)
    return (
        f"Web scout on \"{need}\":\n{findings.summary}\n\nPages (cite these as "
        f"markdown links):\n{pages}"
    )


def show_figure(ctx: RunContext[ResearcherDeps], index: int, figure: int) -> str:
    """Place one of a paper's own figures (image + caption — from ar5iv, or
    mined from its open-access PDF, where tables and algorithm boxes count
    too) into your answer. Only for a paper you've read in full — the full
    read lists its figures. The result gives you a <<FIG n>> marker: put it
    on its own line in your prose exactly where the figure belongs.

    Args:
        ctx: The run context carrying the researcher's deps (framework-injected).
        index: The [n] index of the paper the figure comes from.
        figure: The figure's number as listed in the full read (1-based).

    Returns:
        The ``<<FIG n>>`` marker to place in your prose, or a
        budget/validity message.
    """
    deps = ctx.deps
    node = _node_at(deps, index)
    if node is None or figure < 1:
        deps.emit(events.FigureTrace(ok=False, index=index, title=None, figure=figure))
        return f"Invalid show_figure call (index={index}, figure={figure})."
    if not _spend_step(deps):
        deps.emit(events.FigureTrace(ok=False, index=index, title=node.title, figure=figure))
        return STEPS_EXHAUSTED
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

    # Same list (and numbering) the full read printed — ar5iv render or
    # mined OA-PDF floats, with browser-ready image URLs either way.
    figs = _node_figures(node, deps.provider)
    if not figs:
        deps.emit(events.FigureTrace(ok=False, index=index, title=node.title, figure=figure))
        return f'"{node.title}" has no extractable figures to show.'
    if figure > len(figs):
        deps.emit(events.FigureTrace(ok=False, index=index, title=node.title, figure=figure))
        return f'"{node.title}" has only {len(figs)} figure(s); {figure} doesn\'t exist.'

    slot = len(deps.figures_shown) + 1
    deps.figures_shown[shown_key] = slot
    deps.figures_left -= 1
    chosen = figs[figure - 1]
    # The float's own designation ("Figure 3", "Table 2") heads the card and
    # the chip; the caption travels without it so it isn't shown twice.
    label, caption_text = captions.split_label(chosen.get("caption") or "")
    deps.emit(
        events.FigureTrace(ok=True, index=index, title=node.title, figure=figure, label=label)
    )
    deps.emit(
        events.Figure(
            image=chosen["image"],
            caption=caption_text,
            title=node.title,
            index=index,
            figure=figure,
            slot=slot,
            label=label,
        )
    )
    return (
        f'Attached Figure {figure} of "{node.title}" to your answer. Place the '
        f"marker <<FIG {slot}>> on its own line in your prose at exactly the "
        f"point where this figure belongs."
    )


def show_source_figure(
    ctx: RunContext[ResearcherDeps], source: int, page: int, figure: int = 1
) -> str:
    """Place a figure/table from one of the student's OWN uploaded sources
    into your answer — the library twin of show_figure. Use it when a
    passage you're citing (search_sources tags each with its marker)
    refers to a figure the student would benefit from seeing. The result
    gives you a <<FIG n>> marker: put it on its own line in your prose
    exactly where the figure belongs.

    Args:
        ctx: The run context carrying the researcher's deps (framework-injected).
        source: Which source, as its number in "Your library" — the ``3`` of
            ``[S3]``.
        page: The 1-based page the figure is on (usually the cited
            passage's page).
        figure: Which figure on that page, 1-based, when it has several.

    Returns:
        The ``<<FIG n>>`` marker to place in your prose, or a
        budget/validity message (a page with no figures lists the source's
        pages that do have them).
    """
    deps = ctx.deps
    if not _spend_step(deps):
        deps.emit(events.FigureTrace(ok=False, index=None, title=None, figure=figure))
        return STEPS_EXHAUSTED
    source_id = deps.source_id(source)
    if source_id is None:
        deps.emit(events.FigureTrace(ok=False, index=None, title=None, figure=figure))
        return f"No source [S{source}] in your library — check the numbered list."
    # Everything past the step charge — resolution, dedupe, slot, events —
    # lives in agents/library_figures.py.
    return library_figures.attach_source_figure(deps, source_id, page, figure)


def search_sources(ctx: RunContext[ResearcherDeps], query: str, source: int | None = None) -> str:
    """Semantic search over the student's OWN uploaded sources (books, PDFs,
    web pages) — not the citation graph. Returns the most relevant passages
    with source title and page; attribute them inline in your prose.

    Args:
        ctx: The run context carrying the researcher's deps (framework-injected).
        query: What to look for — a concept or question, not an id.
        source: Restrict to one source, as its number in "Your library" —
            the ``3`` of ``[S3]`` (optional; omit to search everything).

    Returns:
        The most relevant passages, each tagged with the ``[Sn, p.N]`` marker
        to cite it by, or a budget/validity message.
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
    elif source is not None:
        pinned = deps.source_id(source)
        if pinned is None:
            deps.emit(events.SourceSearchTrace(ok=False, query=query))
            return f"No source [S{source}] in your library — check the numbered list."
        source_ids = [pinned]
    else:
        source_ids = None
    try:
        hits = retrieval.search(query, source_ids=source_ids)
    except Exception as exc:
        log.exception("search_sources failed")
        deps.emit(events.SourceSearchTrace(ok=False, query=query))
        return f"Couldn't search your sources: {exc}"

    # Counted the moment retrieval returns, hits or not: the guard downstream
    # asks whether the library was *consulted*, which an empty result answers
    # just as well as a full one.
    deps.source_searches_run += 1
    deps.source_hits += len(hits)

    deps.emit(events.SourceSearchTrace(ok=True, query=query, found=len(hits)))
    if not hits:
        return f'No passages in your library matched "{query}".'
    return f'Passages from your library for "{query}":\n\n' + prompts.format_passages(
        hits, deps.sources
    )
