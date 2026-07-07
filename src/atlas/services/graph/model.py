"""The typed domain models the services produce — currently the graph objects.

Split out of ``graph.py`` so the *shape* of a graph (this file) reads separately
from the assembly logic that builds it. ``build_graph`` returns a ``Graph``;
callers that need JSON serialize with ``model_dump()`` / ``model_dump_json()``,
and the cache stores/re-validates the same models.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class Node(BaseModel):
    """A paper in the graph: the normalized S2 node plus its graph annotations.

    The first eleven fields mirror ``semantic_scholar.nodes.node()`` exactly
    (``extra="forbid"`` keeps them in lockstep — if that shape drifts, node
    construction fails loudly rather than silently dropping data). ``rels`` and
    ``is_seed`` are added during assembly.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    arxiv_id: str | None
    title: str
    abstract: str | None
    tldr: str | None
    year: int | None
    month: int | None
    pub_date: str | None
    citation_count: int | None
    authors: str | None
    url: str
    rels: list[str]
    is_seed: bool


class Edge(BaseModel):
    """A directed edge between two nodes, tagged by relation.

    Direction encodes citation semantics: an edge always points from the citing
    paper to the cited one. ``influential`` (S2's "highly influential citation"
    flag) is carried on ``reference``/``citation`` edges and is ``None`` on
    ``similar`` edges, which aren't citations.
    """

    model_config = ConfigDict(extra="forbid")

    source: str
    target: str
    type: Literal["reference", "citation", "similar"]
    influential: bool | None = None


class Seed(BaseModel):
    """A compact summary of the seed paper, for the graph header."""

    model_config = ConfigDict(extra="forbid")

    arxiv_id: str | None
    id: str
    title: str


class Counts(BaseModel):
    """Per-relation traversal sizes plus the final deduped node count."""

    model_config = ConfigDict(extra="forbid")

    references: int
    citations: int
    similar: int
    nodes: int


class Graph(BaseModel):
    """A seed paper's assembled neighborhood graph — the app's central object."""

    model_config = ConfigDict(extra="forbid")

    seed: Seed
    nodes: list[Node]
    edges: list[Edge]
    counts: Counts
