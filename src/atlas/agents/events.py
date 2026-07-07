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


class Beat(BaseModel):
    """One lecture beat: a signpost heading, one tight narration paragraph,
    and the nodes to light up on the graph while it's spoken."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["beat"] = "beat"
    heading: str
    text: str
    node_ids: list[str]


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
    numbered list, ``None`` when the history backfill found it (backfill runs
    *before* the lecturer numbers anything).
    """

    idx: int | None = None
    discovered: Literal[True] = True


class Discovery(BaseModel):
    """Papers (and the edges linking them) to merge into the live graph.

    Emitted when expansion, search, or the history backfill finds papers not
    yet on screen. A free-text search discovery carries no edges — a topic
    search links its hits to no specific paper.
    """

    model_config = ConfigDict(extra="forbid")

    type: Literal["discovery"] = "discovery"
    nodes: list[DiscoveredNode]
    edges: list[Edge]


class Figure(BaseModel):
    """A real paper figure the researcher attached to its answer.

    The frontend interleaves the image at the ``<<FIG slot>>`` marker the
    model placed in its prose (falling back to the end of the answer if the
    marker never appears). ``index``/``figure`` echo which paper and which of
    its figures this is; ``image`` is the URL to fetch the image from.
    """

    model_config = ConfigDict(extra="forbid")

    type: Literal["figure"] = "figure"
    image: str
    caption: str
    title: str | None
    index: int
    figure: int
    slot: int


class Cited(BaseModel):
    """The final citation event: the node ids the answer draws on, for the
    frontend to highlight. Emitted exactly once, after the prose."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["cited"] = "cited"
    node_ids: list[str]


class Done(BaseModel):
    """The workflow finished cleanly. Always the last event on success."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["done"] = "done"


class Error(BaseModel):
    """The workflow failed. Always the last event on failure — the frontend
    shows ``message`` in the panel instead of hanging on a dead stream."""

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
    """The researcher ran a free-text Semantic Scholar search."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["trace"] = "trace"
    action: Literal["search"] = "search"
    ok: bool
    query: str
    found: int | None = None
    year_from: int | None = None
    year_to: int | None = None


class SourceSearchTrace(BaseModel):
    """The researcher searched the user's own uploaded library."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["trace"] = "trace"
    action: Literal["search_sources"] = "search_sources"
    ok: bool
    query: str
    found: int | None = None


class FigureTrace(BaseModel):
    """The researcher attached (or failed to attach) a paper's figure."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["trace"] = "trace"
    action: Literal["figure"] = "figure"
    ok: bool
    index: int | None
    title: str | None
    figure: int | None


class BackfillTrace(BaseModel):
    """One hop of the history backfill's backward reference-walk.

    ``oldest`` is the oldest publication year among this hop's additions.
    ``error`` is set on the final empty trace when nothing older was found
    *and* at least one hop failed — "we found nothing" and "we couldn't look"
    read differently.
    """

    model_config = ConfigDict(extra="forbid")

    type: Literal["trace"] = "trace"
    action: Literal["backfill"] = "backfill"
    hop: int
    found: int
    oldest: int | None
    error: bool = False


class RetrievalTrace(BaseModel):
    """The librarian's pre-answer retrieval: how many passages matched and
    the distinct source titles they came from."""

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
    | BackfillTrace
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
