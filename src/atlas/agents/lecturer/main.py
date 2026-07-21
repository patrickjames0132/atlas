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

Mode picks the story (``history`` / ``intuition`` / ``evolution`` /
``bridge``); every mode narrates the visible node set exactly as handed in —
the lecturer never expands the graph (pulling new papers in is the
researcher's job, on explicit questions). Lectures are illustrated: each
storytelling mode gets a deterministic pre-fetched **figure pool** (the
seed's own ar5iv figures for intuition; the story's landmark papers' for
history/evolution) whose entries beats can attach; intuition additionally
grounds in the seed's **full text** (ar5iv, equations kept as LaTeX — it
reads the paper and teaches it in chapters) and retrieved library passages.
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

from ...integrations.arxiv import figures as figures_mod
from ...integrations.arxiv import fulltext as fulltext_mod
from ...services.graph import Node
from ...services.sources import retrieval
from .. import events, factory, prompts, streams
from ..models import LectureMode
from .config import AGENT_ID, MODE_INTENTS, SKILLS, SYSTEM_PROMPT

log = logging.getLogger(__name__)


class LectureBeat(BaseModel):
    """One beat as the model emits it: numbered-list indices, not node ids
    (the model never sees ids — ``prompts.idx_to_id`` maps them back), plus
    optionally the number of a pooled figure to show with the beat (the
    prompt lists the mode's figure pool; a mode with an empty pool maps any
    value to nothing).
    """

    model_config = ConfigDict(extra="forbid")

    heading: str
    text: str
    nodes: list[int]
    figure: int | None = None


agent: Agent[None, list[LectureBeat]] = Agent(
    factory.build_model(AGENT_ID),
    output_type=list[LectureBeat],
    instructions=[SYSTEM_PROMPT, *(prompts.skill(name) for name in SKILLS)],
)


# The story modes' figure pool: how many landmark papers (beyond the seed)
# contribute figures, and how many figures each may contribute. Bounded so
# the pre-lecture ar5iv fetches (cached, but a cold run pays them) and the
# prompt's figure list stay small.
_FIGURE_PAPERS = 4
_FIGURES_PER_PAPER = 3

# How much of the seed's full text the intuition lecture reads. Bounded so the
# prompt stays a sane size; the ar5iv reader caches the whole text, this just
# caps what's fed at request time (the paper's front matter — problem, method,
# results — leads, which is what the chapters teach from).
_SEED_FULLTEXT_CHARS = 12000

# The chronological, many-paper modes: their numbered list is sorted oldest
# first and banded by era, and they carry the full-span guardrail. HISTORY and
# EVOLUTION are arcs; FRONTIER is a thematic survey but still oriented forward
# in time, so it gets the same temporal scaffolding (era-banded list + span
# line). Intuition (seed only) and bridge (a two-paper conceptual link) are not
# banded.
_CHRONOLOGICAL_MODES = frozenset(
    {LectureMode.HISTORY, LectureMode.EVOLUTION, LectureMode.FRONTIER}
)


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


def _figure_pool(seed: Node, nodes: list[Node], mode: LectureMode) -> list[dict]:
    """The figures a lecture may attach to its beats, as a flat numbered pool.

    Intuition stays on the seed, so its pool is the seed's own figures
    (untitled — there's only one paper in play). History, evolution, and the
    current frontier tell a many-paper story, so their pool draws from the seed
    plus the ``_FIGURE_PAPERS`` most-cited arXiv papers among the (already
    mode-scoped) visible nodes, ``_FIGURES_PER_PAPER`` figures each — every
    entry titled with its source paper so both the model and the beat card
    can attribute it. Bridge shows no figures.

    Args:
        seed: The seed paper (its figures lead every pool).
        nodes: The mode-scoped visible nodes the landmarks are drawn from.
        mode: The lecture mode (decides the pool's shape).

    Returns:
        ``[{"image", "caption", "title"}]`` entries (``title`` None for the
        intuition pool).
    """
    if mode is LectureMode.INTUITION:
        return [{**figure, "title": None} for figure in _paper_figures(seed)]
    if mode not in (LectureMode.HISTORY, LectureMode.EVOLUTION, LectureMode.FRONTIER):
        return []
    landmarks = sorted(
        (node for node in nodes if node.arxiv_id and not node.is_seed),
        key=lambda node: node.citation_count or 0,
        reverse=True,
    )[:_FIGURE_PAPERS]
    pool: list[dict] = []
    for paper in ([seed] if seed.arxiv_id else []) + landmarks:
        for figure in _paper_figures(paper)[:_FIGURES_PER_PAPER]:
            pool.append({**figure, "title": paper.title})
    return pool


def _seed_passages(seed: Node) -> list[dict]:
    """Library passages about the seed, for the intuition lecture.

    The same hybrid retrieval the librarian grounds in, queried with the
    seed's title — extra context the lecture MAY draw on (attributed
    inline). Empty when the library is empty/unavailable or on any failure.
    """
    query = (seed.title or "").strip()
    if not query:
        return []
    try:
        return retrieval.search(query)
    except Exception:
        log.warning("seed passage retrieval failed", exc_info=True)
        return []


def _seed_fulltext(seed: Node) -> str:
    """The seed paper's readable full text, for the intuition lecture to teach from.

    The same ar5iv reader the researcher uses — equations preserved as LaTeX
    (``keep_math``) so the chapters can quote the paper's actual math — truncated
    to ``_SEED_FULLTEXT_CHARS``. Empty for a non-arXiv seed, when ar5iv has no
    render, or on any failure: the intuition lecture still runs from the
    abstract, figures, and library passages.

    Args:
        seed: The seed paper.

    Returns:
        The truncated full text, or an empty string when unavailable.
    """
    if not seed.arxiv_id:
        return ""
    try:
        result = fulltext_mod.get_fulltext(seed.arxiv_id)
    except Exception:
        log.warning("seed fulltext fetch failed for %s", seed.arxiv_id, exc_info=True)
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
        nodes: The mode-scoped story nodes.

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
    mode: LectureMode,
    target: Node | None,
    figures: list[dict],
    passages: list[dict],
    fulltext: str,
) -> str:
    """Assemble the lecture request: mode intent, seed/target header, the
    numbered paper list (era-banded for the chronological modes), and — intuition
    mode — the seed's full text, figure list, and retrieved library passages.

    Args:
        seed: The seed paper.
        nodes: The visible graph nodes, in display order (oldest-first for the
            chronological modes).
        mode: Which story to tell.
        target: The bridge target (bridge mode only), or None.
        figures: The mode's figure pool (see ``_figure_pool``; may be empty).
        passages: Retrieved library passages (empty outside intuition mode).
        fulltext: The seed's full text (intuition mode only; empty otherwise).

    Returns:
        The full user prompt.
    """
    header = f"SEED paper: {seed.title}"
    if mode == "bridge" and target:
        header += f"\nTARGET paper: {target.title}"
    if mode in _CHRONOLOGICAL_MODES:
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
    sections = [MODE_INTENTS[mode], header, paper_section]
    if fulltext:
        sections.append(
            "Full text of the SEED paper (read it and teach from it — quote its "
            "actual equations, quantities, and numbers):\n" + fulltext
        )
    if figures:
        figure_lines = []
        for number, figure in enumerate(figures, 1):
            source = f"[{figure['title']}] " if figure.get("title") else ""
            caption = (figure.get("caption") or "(no caption)")[:200]
            figure_lines.append(f"{number}. {source}{caption}")
        pool_name = (
            "Figures of the SEED paper"
            if mode is LectureMode.INTUITION
            else "Figures from the story's papers"
        )
        sections.append(
            f"{pool_name} (attach one to a beat by setting the beat's "
            "`figure` to its number):\n" + "\n".join(figure_lines)
        )
    if passages:
        sections.append(
            "Passages from the student's own library (optional extra "
            "context — attribute inline when you draw on one):\n"
            + prompts.format_passages(passages)
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
    or spurious number — including any in a mode whose pool is empty — just
    means no figure, never a failure).
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
    return events.Beat(
        heading=beat.heading.strip(),
        text=text,
        node_ids=prompts.idx_to_id(nodes, beat.nodes),
        # Resolve the beat's inline [n] markers against the same numbered list
        # (the mode-filtered story nodes) so the frontend can make them clickable.
        refs=prompts.refs_from_text(nodes, text),
        figure=figure,
    )


def lecture(
    seed: Node,
    nodes: list[Node],
    mode: LectureMode = LectureMode.HISTORY,
    target: Node | None = None,
) -> Iterator[events.Beat]:
    """Stream a lecture over the visible graph as typed beats.

    Args:
        seed: The seed paper.
        nodes: The visible graph nodes — the lecture's entire world; the
            lecturer narrates them as-is and never expands the graph.
        mode: ``history``, ``intuition``, ``evolution``, or ``bridge``.
        target: The bridge target paper (bridge mode only), or None.

    Yields:
        ``events.Beat`` per beat, as soon as each is complete — a beat is
        final once the model starts the next one, so narration begins before
        the lecture ends. Beats with blank text are dropped. A beat may
        carry one figure from the mode's pool (the seed's own in intuition;
        the story's landmark papers' in history/evolution).

    Raises:
        Exception: Model/stream failures propagate — the caller ends the
            event stream with ``Error``.
    """
    # Every storytelling mode gets a figure pool (the seed's own figures for
    # intuition; the story's landmark papers' for history/evolution — see
    # _figure_pool); library passages and the seed's full text ground the
    # intuition lecture only (it reads the paper and teaches it in chapters).
    figures = _figure_pool(seed, nodes, mode)
    passages = _seed_passages(seed) if mode is LectureMode.INTUITION else []
    fulltext = _seed_fulltext(seed) if mode is LectureMode.INTUITION else ""

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

    prompt = _prompt(seed, nodes, mode, target, figures, passages, fulltext)
    for event in streams.drive(agent, prompt):
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
