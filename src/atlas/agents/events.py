"""The typed event stream every agent workflow emits.

A workflow (a lecture, a Q&A turn, a library chat) doesn't return one value —
it *streams*: narration arrives beat by beat, an agent's tool steps surface as
they happen, discovered papers merge into the live graph mid-answer. This
module defines that stream's vocabulary as Pydantic models, replacing the old
teacher's ad-hoc ``("kind", data)`` tuples, so every payload shape is declared,
validated, and greppable in one place.

Two discriminated unions tie it together:

* ``Trace`` — the "watch the agent work" events, discriminated by ``action``
  (one variant per thing an agent can do: read, expand, search, ...).
* ``Event`` — everything a workflow may yield, discriminated by ``type``.
  The routes layer (Phase 5) serializes each event as an SSE frame named by
  its ``type``; the frontend switches on the same tag.

``Discovery`` reuses the graph's own ``Node``/``Edge`` models (via
``DiscoveredNode``) so a paper an agent finds mid-answer has exactly the same
shape as one ``build_graph`` produced — the frontend merges them into one
canvas and can't tell the difference.
"""

from __future__ import annotations

from typing import Annotated, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field

from ..services.graph import Edge, Node


class BeatFigure(BaseModel):
    """A real paper figure attached to a lecture beat: a same-origin proxied
    image URL, the paper's own caption, and the figure's number in the
    lecture's figure list. ``title`` names the source paper when the lecture
    drew from several (history/evolution); None when every figure is the
    seed's own (intuition).
    """

    model_config = ConfigDict(extra="forbid")

    image: str
    caption: str
    number: int
    title: str | None = None


class Beat(BaseModel):
    """One lecture beat: a signpost heading, one tight narration paragraph,
    the nodes to light up on the graph while it's spoken, and optionally one
    of the seed paper's own figures to show inline (intuition mode).
    """

    model_config = ConfigDict(extra="forbid")

    type: Literal["beat"] = "beat"
    heading: str
    text: str
    node_ids: list[str]
    # Map from an inline ``[n]`` marker in ``text`` to the node id it points at,
    # resolved against the same numbered list the lecturer saw. Lets the
    # frontend make each ``[n]`` clickable. Resolved here (not frontend-side)
    # because a lecture's numbered list is the mode-filtered ``_story_nodes``,
    # which the frontend never sees.
    refs: dict[str, str] = Field(default_factory=dict)
    figure: BeatFigure | None = None


class Token(BaseModel):
    """A chunk of streamed answer prose, emitted as the model produces it."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["token"] = "token"
    text: str


class DiscoveredNode(Node):
    """A paper an agent found mid-workflow, ready to merge into the live graph.

    Exactly a graph ``Node`` plus two annotations: ``discovered`` marks it as
    agent-found (the frontend styles these differently), and ``idx`` is the
    number the model knows it by — set when a researcher tool added it to the
    numbered list. (``None`` is tolerated for saved sessions from the era
    when lecture backfills discovered un-numbered papers.)
    """

    idx: int | None = None
    discovered: Literal[True] = True


class Discovery(BaseModel):
    """Papers (and the edges linking them) to merge into the live graph.

    Emitted when the researcher's expansion or search tools find papers not
    yet on screen — only the researcher ever grows the graph; lectures
    narrate it as-is. A free-text search discovery carries no edges — a
    topic search links its hits to no specific paper.
    """

    model_config = ConfigDict(extra="forbid")

    type: Literal["discovery"] = "discovery"
    nodes: list[DiscoveredNode]
    edges: list[Edge]


class Figure(BaseModel):
    """A real figure the researcher attached to its answer — a paper's
    (``show_figure``) or one from the user's own uploaded library
    (``show_source_figure``).

    The frontend interleaves the image at the ``<<FIG slot>>`` marker the
    model placed in its prose (falling back to the end of the answer if the
    marker never appears). ``index``/``figure`` echo which paper and which of
    its figures this is — ``index`` is None for a library figure, which
    belongs to no numbered paper (``title`` then names the source); ``image``
    is the URL to fetch the image from.
    """

    model_config = ConfigDict(extra="forbid")

    type: Literal["figure"] = "figure"
    image: str
    caption: str
    title: str | None
    index: int | None
    figure: int
    slot: int
    label: str | None = None
    """The float's own designation parsed off its caption ("Figure 12.4",
    "Table 2") — what the card heading and trace chips display, with
    ``caption`` holding the remaining text. None when the caption carries no
    designation (the frontend then numbers attachments by slot); absent on
    pre-v5.28 saved sessions."""


class Cited(BaseModel):
    """The final citation event: the node ids the answer draws on, for the
    frontend to highlight. Emitted exactly once, after the prose.
    """

    model_config = ConfigDict(extra="forbid")

    type: Literal["cited"] = "cited"
    node_ids: list[str]


class Done(BaseModel):
    """The workflow finished cleanly. Always the last event on success."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["done"] = "done"


class Error(BaseModel):
    """The workflow failed. Always the last event on failure — the frontend
    shows ``message`` in the panel instead of hanging on a dead stream.
    """

    model_config = ConfigDict(extra="forbid")

    type: Literal["error"] = "error"
    message: str


# --- Trace variants: one per thing an agent can be watched doing -------------


class ReadTrace(BaseModel):
    """The researcher read (or failed to read) a numbered paper."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["trace"] = "trace"
    action: Literal["read"] = "read"
    ok: bool
    index: int | None
    title: str | None
    detail: Literal["summary", "full"]


class ExpandTrace(BaseModel):
    """The researcher pulled one hop of neighbors for a numbered paper.

    ``relation`` is ``str | None`` (not a Literal): a failed call may carry
    whatever invalid relation the model asked for, reported as-is.
    """

    model_config = ConfigDict(extra="forbid")

    type: Literal["trace"] = "trace"
    action: Literal["expand"] = "expand"
    ok: bool
    index: int | None
    title: str | None
    relation: str | None
    found: int | None = None


class SearchTrace(BaseModel):
    """The researcher ran a free-text Semantic Scholar search.

    ``reason`` distinguishes *why* a failed search never turned anything up —
    "the budget ran out" and "Semantic Scholar errored" read very differently
    to someone debugging a stuck answer. ``None`` on success, and also on
    saved sessions from before this field existed (the frontend falls back to
    a generic "Tried" for those).
    """

    model_config = ConfigDict(extra="forbid")

    type: Literal["trace"] = "trace"
    action: Literal["search"] = "search"
    ok: bool
    query: str
    found: int | None = None
    year_from: int | None = None
    year_to: int | None = None
    reason: Literal["empty_query", "steps_exhausted", "budget_exhausted", "error"] | None = None


class SourceSearchTrace(BaseModel):
    """The researcher searched the user's own uploaded library."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["trace"] = "trace"
    action: Literal["search_sources"] = "search_sources"
    ok: bool
    query: str
    found: int | None = None


class FigureTrace(BaseModel):
    """An agent attached (or failed to attach) a figure — a paper's
    (researcher) or an uploaded source's (researcher/librarian).
    """

    model_config = ConfigDict(extra="forbid")

    type: Literal["trace"] = "trace"
    action: Literal["figure"] = "figure"
    ok: bool
    index: int | None
    title: str | None
    figure: int | None
    label: str | None = None
    """The attached float's own designation ("Figure 12.4") for the chip
    text; None on failures and label-less captions (the chip then falls
    back to the per-paper/per-page number in ``figure``)."""


class RetrievalTrace(BaseModel):
    """The librarian's pre-answer retrieval: how many passages matched and
    the distinct source titles they came from.
    """

    model_config = ConfigDict(extra="forbid")

    type: Literal["trace"] = "trace"
    action: Literal["retrieval"] = "retrieval"
    found: int
    sources: list[str]


Trace: TypeAlias = Annotated[
    ReadTrace
    | ExpandTrace
    | SearchTrace
    | SourceSearchTrace
    | FigureTrace
    | RetrievalTrace,
    Field(discriminator="action"),
]
"""Any "watch the agent work" event, discriminated by ``action``."""

Event: TypeAlias = Annotated[
    Beat | Token | Discovery | Figure | Cited | Done | Error | Trace,
    Field(discriminator="type"),
]
"""Anything a workflow may yield, discriminated by ``type`` (traces nest their
own ``action`` discriminator underneath)."""
