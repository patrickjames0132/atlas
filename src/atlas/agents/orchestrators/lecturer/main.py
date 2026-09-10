"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
The lecturer: a streamed lecture over the visible graph, in typed beats.

The model produces a ``list[LectureBeat]`` as structured output — heading,
one tight narration paragraph, and the numbered-list indices to light up.
The beats stream out as the model writes them: the run is driven through
``streams.drive`` (the shared sync event bridge), the output tool's argument
JSON is partial-parsed as it grows, and each beat is emitted the moment the
model starts the next one. This replaces the old newline-delimited-JSON
protocol and its fence-stripping parser outright — the shape is enforced by
Pydantic, not begged for in the prompt.

(Why the bridge and not ``run_stream_sync().stream_output()``: the sync
convenience wrapper delivered the whole lecture in one burst at the end
against the live API — verified with frame timestamps. See ``streams.py``.)

**The scope is the subject** (v7.17.0): the lecture narrates the node set
handed in — what the reader has filtered or hand-picked on screen — exactly
as given, and never expands the graph (pulling new papers in is the
researcher's job, on explicit questions). The four mode buttons that used to
each carve their own slice out of that set are gone; see ``_story_nodes``.
Two shapes are still read off the request rather than chosen: a ``target``
makes it a bridge lecture, and a scope of nothing but the seed makes it a
solo one, which teaches that paper in chapters and is the only shape
grounded in the seed's **full text** (ar5iv, equations kept as LaTeX) and
retrieved library passages. Lectures are illustrated either way, from a
deterministic pre-fetched **figure pool** whose entries beats can attach.
No tools involved — all fetched (cached) before the run. Model failures
propagate — the caller ends the event stream with ``Error``.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

import logging
import urllib.parse
from typing import Iterator

from pydantic import BaseModel, ConfigDict, ValidationError
from pydantic_ai import Agent
from pydantic_ai.messages import (
    PartDeltaEvent,
    PartStartEvent,
    ToolCallPart,
    ToolCallPartDelta,
)
from pydantic_ai.run import AgentRunResultEvent
from pydantic_core import from_json

from ....integrations.arxiv import figures as figures_mod
from ....integrations.arxiv import fulltext as fulltext_mod
from ....services.graph import Node
from ....services.sources import retrieval
from ... import events, factory, prompts, streams
from .config import (
    AGENT_ID,
    BRIDGE_INTENT,
    HISTORY_INTENT,
    SKILLS,
    SOLO_INTENT,
    SUMMARY_INTENT,
    SYSTEM_PROMPT,
    Framing,
)

log = logging.getLogger(__name__)


class LectureBeat(BaseModel):
    """One beat as the model emits it: numbered-list indices, not node ids
    (the model never sees ids — ``prompts.idx_to_id`` maps them back), plus
    optionally the number of a pooled figure to show with the beat (the
    prompt lists the lecture's figure pool; a lecture with an empty pool maps any
    value to nothing).
    """

    model_config = ConfigDict(extra="forbid")

    heading: str
    text: str
    nodes: list[int]
    figure: int | None = None


# No model at construction: it is passed per run by `factory.model_for`, so a
# blank config can't stop the app booting and a settings edit needs no restart.
agent: Agent[None, list[LectureBeat]] = Agent(
    output_type=list[LectureBeat],
    instructions=[SYSTEM_PROMPT, *(prompts.skill(name) for name in SKILLS)],
)


# The many-paper figure pool: how many papers (beyond the seed)
# contribute figures, and how many figures each may contribute. Bounded so
# the pre-lecture ar5iv fetches (cached, but a cold run pays them) and the
# prompt's figure list stay small.
_FIGURE_PAPERS = 4
_FIGURES_PER_PAPER = 3

# How much of the seed's full text a solo lecture reads. Bounded so the
# prompt stays a sane size; the ar5iv reader caches the whole text, this just
# caps what's fed at request time (the paper's front matter — problem, method,
# results — leads, which is what the chapters teach from).
_SEED_FULLTEXT_CHARS = 12000

def _paper_figures(paper: Node) -> list[dict]:
    """One paper's ar5iv figures, for the lecture's figure pool.

    Deterministic grounding, not a tool: fetched (cached) before the run so
    the prompt can list the captions and beats can attach one. Empty for a
    non-arXiv paper or on any fetch failure — figures are a nicety; the
    lecture happens with or without them.
    """
    if not paper.arxiv_id:
        return []
    try:
        result = figures_mod.get_figures(paper.arxiv_id)
    except Exception:
        log.warning("figure fetch failed for %s", paper.arxiv_id, exc_info=True)
        return []
    return result.get("figures") or []


def _figure_pool(lead: Node, nodes: list[Node], solo: bool) -> list[dict]:
    """The figures a lecture may attach to its beats, as a flat numbered pool.

    The pool's shape follows the **scope**, not a mode the reader picked. A
    solo lecture shows its subject paper's own figures, untitled — there is
    only one paper in play, so attribution would be noise. A many-paper
    lecture draws from the seed plus the ``_FIGURE_PAPERS`` most-cited arXiv
    papers on the list, ``_FIGURES_PER_PAPER`` figures each, every entry
    titled with its source paper so both the model and the beat card can
    attribute it.

    Args:
        lead: The paper whose figures lead the pool — the solo subject, or
            the seed for a many-paper lecture.
        nodes: The scoped nodes the story's papers are drawn from.
        solo: The scope is a single paper (see ``_solo_subject``).

    Returns:
        ``[{"image", "caption", "title"}]`` entries (``title`` None when solo).
    """
    if solo:
        return [{**figure, "title": None} for figure in _paper_figures(lead)]
    others = sorted(
        (node for node in nodes if node.arxiv_id and node.id != lead.id),
        key=lambda node: node.citation_count or 0,
        reverse=True,
    )[:_FIGURE_PAPERS]
    pool: list[dict] = []
    for paper in ([lead] if lead.arxiv_id else []) + others:
        for figure in _paper_figures(paper)[:_FIGURES_PER_PAPER]:
            pool.append({**figure, "title": paper.title})
    return pool


def _paper_passages(paper: Node) -> list[dict]:
    """Library passages about the lecture's subject paper, for a solo lecture.

    The same hybrid retrieval ``search_sources`` uses, queried with the paper's
    title — extra context the lecture MAY draw on (attributed inline). Empty
    when the library is empty/unavailable or on any failure.

    Args:
        paper: The paper the solo lecture is about.

    Returns:
        The retrieved passages, or an empty list.
    """
    query = (paper.title or "").strip()
    if not query:
        return []
    try:
        return retrieval.search(query)
    except Exception:
        log.warning("passage retrieval failed", exc_info=True)
        return []


def _paper_fulltext(paper: Node) -> str:
    """The subject paper's readable full text, for a solo lecture to teach from.

    The same ar5iv reader the researcher uses — equations preserved as LaTeX
    (``keep_math``) so the chapters can quote the paper's actual math —
    truncated to ``_SEED_FULLTEXT_CHARS``. Empty for a non-arXiv paper, when
    ar5iv has no render, or on any failure: the lecture still runs from the
    abstract, figures, and library passages.

    Args:
        paper: The paper the solo lecture is about.

    Returns:
        The truncated full text, or an empty string when unavailable.
    """
    if not paper.arxiv_id:
        return ""
    try:
        result = fulltext_mod.get_fulltext(paper.arxiv_id)
    except Exception:
        log.warning("fulltext fetch failed for %s", paper.arxiv_id, exc_info=True)
        return ""
    if not result.get("available"):
        return ""
    return (result.get("text") or "")[:_SEED_FULLTEXT_CHARS]


def _span_line(nodes: list[Node]) -> str:
    """The story's concrete year range, as a full-span reminder for the prompt.

    The numbers behind the ``_SPAN_NUDGE`` words — computed from the actual
    node set so the model is told the real endpoints it must reach. Empty when
    fewer than two distinct years are present (nothing to span).

    Args:
        nodes: The scoped story nodes.

    Returns:
        A one-line reminder like ``The numbered list spans 1998–2024; …``, or
        an empty string.
    """
    years = {node.year for node in nodes if node.year is not None}
    if len(years) < 2:
        return ""
    return (
        f"The numbered list spans {min(years)}–{max(years)}; make sure your beats "
        "reach both ends of that range."
    )


def _prompt(
    seed: Node,
    nodes: list[Node],
    subject: Node | None,
    target: Node | None,
    framing: Framing,
    figures: list[dict],
    passages: list[dict],
    fulltext: str,
) -> str:
    """Assemble the lecture request: the intent, the paper header, the numbered
    paper list, and — for a solo lecture — the subject's full text, figure
    list, and retrieved library passages.

    Which intent leads is decided **structurally** from the request rather than
    from a mode the reader chose: a ``target`` means the bridge lecture, a
    single scoped paper means the solo one, and anything else is a many-paper
    lecture whose framing the reader picked. Only a *history*-framed many-paper
    lecture gets the era-banded list and the span line, because it is the only
    shape telling a story across time — a summary orders its beats by idea, and
    handing it a timeline invited beats about the timeline itself.

    Args:
        seed: The seed paper, named as the graph's centre for a many-paper
            lecture.
        nodes: The scoped nodes, in display order.
        subject: The single scoped paper for a solo lecture, else None.
        target: The bridge target, or None for an ordinary lecture.
        framing: The reader's choice of summary or history.
        figures: The figure pool (see ``_figure_pool``; may be empty).
        passages: Retrieved library passages (solo lecture only).
        fulltext: The subject's full text (solo lecture only; empty otherwise).

    Returns:
        The full user prompt.
    """
    if target:
        intent = BRIDGE_INTENT
        header = f"SEED paper: {seed.title}\nTARGET paper: {target.title}"
    elif subject is not None:
        intent = SOLO_INTENT
        header = f"SUBJECT paper: {subject.title}"
    else:
        intent = HISTORY_INTENT if framing == "history" else SUMMARY_INTENT
        header = f"SEED paper: {seed.title}"
    banded = target is None and subject is None and framing == "history"
    if banded:
        # Oldest-first, banded by era, with the concrete year span spelled out —
        # the rendering + reminder half of the full-span guardrail.
        paper_section = (
            "Papers on the graph (numbered, oldest first, banded by era):\n"
            + prompts.node_lines_by_era(nodes)
        )
        span = _span_line(nodes)
        if span:
            paper_section += f"\n\n{span}"
    else:
        paper_section = f"Papers on the graph (numbered):\n{prompts.node_lines(nodes)}"
    sections = [intent, header, paper_section]
    if fulltext:
        sections.append(
            "Full text of the SUBJECT paper (read it and teach from it — quote "
            "its actual equations, quantities, and numbers):\n" + fulltext
        )
    if figures:
        figure_lines = []
        for number, figure in enumerate(figures, 1):
            source = f"[{figure['title']}] " if figure.get("title") else ""
            caption = (figure.get("caption") or "(no caption)")[:200]
            figure_lines.append(f"{number}. {source}{caption}")
        pool_name = (
            "Figures of the SUBJECT paper" if subject is not None else "Figures from the papers"
        )
        sections.append(
            f"{pool_name} (attach one to a beat by setting the beat's "
            "`figure` to its number):\n" + "\n".join(figure_lines)
        )
    if passages:
        # Same numbered-library protocol as the answer agents: the beat cites
        # [Sn, p.N], never a title it might reword (see prompts.source_lines).
        library = prompts.source_order(passages)
        sections.append(
            "The student's own library:\n"
            + prompts.source_lines(library)
            + "\n\nPassages from it (optional extra context — cite by the "
            "marker each is tagged with when you draw on one):\n"
            + prompts.format_passages(passages, library)
        )
    sections.append("Now deliver the lecture.")
    return "\n\n".join(sections)


def _partial_beats(args_json: str) -> list[LectureBeat]:
    """Parse the beats already complete inside a partially-streamed args JSON.

    The output tool's args stream as ``{"response": [{beat}, {beat}, ...``;
    ``allow_partial`` tolerates the truncated tail, and validation stops at
    the first element that doesn't (yet) have a beat's full shape.
    """
    try:
        parsed = from_json(args_json, allow_partial="trailing-strings")
    except ValueError:
        return []
    items = parsed.get("response") if isinstance(parsed, dict) else None
    if not isinstance(items, list):
        return []
    beats: list[LectureBeat] = []
    for item in items:
        try:
            beats.append(LectureBeat.model_validate(item))
        except ValidationError:
            break  # the trailing, still-generating element
    return beats


def _beat(beat: LectureBeat, nodes: list[Node], figures: list[dict]) -> events.Beat:
    """Convert a model beat to the event the frontend consumes: indices
    mapped back to node ids, and a valid ``figure`` number resolved to the
    pooled figure's proxied image + caption + source paper (an out-of-range
    or spurious number — including any when the pool is empty — just means no
    figure, never a failure).

    ``node_ids`` is the union of the model's chosen papers and every paper it
    cites inline, so lighting a beat lights everything it talks about.
    """
    figure = None
    if beat.figure is not None and 1 <= beat.figure <= len(figures):
        chosen = figures[beat.figure - 1]
        figure = events.BeatFigure(
            # Same-origin proxy — the frontend can't hotlink ar5iv directly.
            image="/api/figure_proxy?src=" + urllib.parse.quote(chosen["image"], safe=""),
            caption=chosen.get("caption") or "",
            number=beat.figure,
            title=chosen.get("title"),
        )
    text = beat.text.strip()
    # Resolve the beat's inline [n] markers against the same numbered list so
    # the frontend can make them clickable.
    graph_refs = prompts.graph_refs_from_text(nodes, text)
    # **Light up every paper the beat actually discusses**, not just the handful
    # the model put in `nodes`. The prompt asks for 1-4 there — the beat's
    # focus — but a beat covering a broad scope routinely cites a dozen more
    # inline, and those were silently unlit: the reader clicked a beat naming
    # sixteen papers and watched three of them glow. The model's own picks lead
    # (they are the emphasis, and `idx_to_id` already dropped hallucinated
    # indices), then any cited paper it didn't list, in first-mention order.
    # Deduped, order-preserving: ``idx_to_id`` maps indices one-for-one, so a
    # model that lists the same paper twice (or picks one it also cites inline)
    # would otherwise light it twice and inflate the beat card's paper count.
    node_ids: list[str] = []
    for node_id in [*prompts.idx_to_id(nodes, beat.nodes), *graph_refs.values()]:
        if node_id not in node_ids:
            node_ids.append(node_id)
    return events.Beat(
        heading=beat.heading.strip(),
        text=text,
        node_ids=node_ids,
        graph_refs=graph_refs,
        figure=figure,
    )


def _chronological(nodes: list[Node]) -> list[Node]:
    """The nodes sorted oldest-first, undated ones last.

    The ordering half of the full-span guardrail: the lecturer numbers the
    story in this order and (via ``prompts.node_lines_by_era``) bands it by
    era, so a beat's papers read left-to-right in time instead of by citation
    count. ``node_lines``/``idx_to_id`` stay consistent because the same
    ordered list is both numbered and mapped back.

    Args:
        nodes: The story's nodes, in arbitrary order.

    Returns:
        The nodes sorted by year ascending, undated papers pushed to the end.
    """
    return sorted(nodes, key=lambda node: (node.year is None, node.year or 0))


def _solo_subject(nodes: list[Node]) -> Node | None:
    """The single paper a solo lecture is about, or None for a many-paper one.

    **Any paper, not just the seed** — select one node anywhere on the graph
    and the lecture is a deep read of that node. The old INTUITION mode could
    only ever teach the seed, so learning about a paper you found meant
    re-seeding the whole graph on it first; scoping already says which paper
    you mean.

    Args:
        nodes: The scoped nodes.

    Returns:
        The one scoped paper, or None when there is more than one.
    """
    return nodes[0] if len(nodes) == 1 else None


def _story_nodes(seed: Node, nodes: list[Node]) -> list[Node]:
    """The nodes a lecture narrates: **whatever the reader has scoped**.

    **This is where four lectures became one (v7.17.0).** Each mode used to
    own a slice of the graph — HISTORY the seed's references, EVOLUTION its
    landmark citers, FRONTIER the recent bands — and this function threw away
    the caller's node list to rebuild that slice from the edges. The reader's
    own filtering and hand-picked selection (``selectGroundingNodes`` on the
    frontend) was therefore *overridden* by whichever button they pressed:
    selecting five papers and asking for a lecture narrated something else
    entirely.

    Now the scope IS the request, and this function adds nothing to it. In
    particular it does **not** slot the seed in: a reader who selects one
    paper wants a lecture on that paper, and quietly adding the seed would
    turn it into a two-paper story about something they didn't ask about.
    The seed is the fallback for an empty scope only, because a lecture has to
    be about something.

    Args:
        seed: The seed paper — the fallback subject when nothing is scoped.
        nodes: The scoped nodes, as the caller sees them on screen.

    Returns:
        The scoped nodes oldest-first, or just the seed when the scope is empty.
    """
    if not nodes:
        return [seed]
    return _chronological(nodes)


def lecture(
    seed: Node,
    nodes: list[Node],
    target: Node | None = None,
    framing: Framing = "summary",
) -> Iterator[events.Beat | events.SourceRefs]:
    """Stream a lecture over the reader's scoped graph as typed beats.

    **One lecture, whose subject is the scope** (v7.17.0). There is no mode
    argument: what the lecture is *about* is what the caller sent, which is
    what the reader has on screen. Two shapes are read off the request rather
    than named by it — a ``target`` selects the bridge lecture, and a scope of
    exactly one paper selects the solo lecture, a deep read of that paper.

    ``framing`` is the one thing the scope cannot express and so the one thing
    the reader still chooses: the same set of papers is a fair subject for a
    themed summary or a chronological history, and only they know which they
    wanted.

    Args:
        seed: The seed paper — the subject only when the scope is empty.
        nodes: The scoped graph nodes — the lecture's entire world, narrated
            as-is (it never expands the graph). Callers send what is on
            screen: visible after filters, narrowed to the hand-picked
            selection when there is one.
        target: The bridge target paper, or None for an ordinary lecture.
        framing: ``summary`` (themes) or ``history`` (a chronological arc).
            Ignored for a bridge lecture, which has its own shape.

    Yields:
        One ``events.SourceRefs`` first when a solo lecture retrieved library
        passages (resolving the ``[Sn]`` markers its beats may cite), then
        ``events.Beat`` per beat, as soon as each is complete — a beat is
        final once the model starts the next one, so narration begins before
        the lecture ends. Beats with blank text are dropped. A beat may carry
        one figure from the pool (the subject paper's own when solo; the
        story's most-cited papers' otherwise).

    Raises:
        Exception: Model/stream failures propagate — the caller ends the
            event stream with ``Error``.
    """
    nodes = _story_nodes(seed, nodes)
    # A scope of one paper is a request to teach that paper — any paper, not
    # just the seed. It gets that paper's own figures plus the two groundings
    # that only make sense with a single subject: its full text and the
    # reader's library passages about it (see _solo_subject / config.SOLO_INTENT).
    subject = _solo_subject(nodes)
    # A bridge lecture shows no figures — it argues a conceptual link between
    # two named papers rather than walking a set of them, so a figure pool
    # would be illustrating papers the lecture may never reach.
    figures = [] if target else _figure_pool(subject or seed, nodes, subject is not None)
    passages = _paper_passages(subject) if subject and not target else []
    fulltext = _paper_fulltext(subject) if subject and not target else ""

    emitted = 0
    args_buffer = ""
    output_part: int | None = None
    final: list[LectureBeat] | None = None

    def flush(beats: list[LectureBeat]) -> Iterator[events.Beat]:
        nonlocal emitted
        for beat in beats[emitted:]:
            emitted += 1
            if beat.text.strip():
                yield _beat(beat, nodes, figures)

    # The library a beat may cite, resolved up front like the answer agents'
    # (see researcher.main) so [Sn, p.N] renders as a real title from the
    # first beat onward.
    if passages:
        yield events.SourceRefs(
            refs={
                key: events.SourceRef(**ref)
                for key, ref in prompts.source_refs(prompts.source_order(passages), "").items()
            }
        )

    prompt = _prompt(seed, nodes, subject, target, framing, figures, passages, fulltext)
    for event in streams.drive(agent, prompt, model=factory.model_for(AGENT_ID)):
        if isinstance(event, PartStartEvent) and isinstance(event.part, ToolCallPart):
            if event.part.tool_name == streams.OUTPUT_TOOL:
                output_part = event.index
                args = event.part.args
                args_buffer = args if isinstance(args, str) else ""
        elif (
            isinstance(event, PartDeltaEvent)
            and event.index == output_part
            and isinstance(event.delta, ToolCallPartDelta)
            and isinstance(event.delta.args_delta, str)
        ):
            args_buffer += event.delta.args_delta
        elif isinstance(event, AgentRunResultEvent):
            final = event.result.output
            continue
        else:
            continue
        # The last parsed beat may still be mid-generation — emit up to it.
        partial = _partial_beats(args_buffer)
        yield from flush(partial[:-1])

    # The validated final output flushes whatever the partial view hadn't.
    if final is not None:
        yield from flush(final)
