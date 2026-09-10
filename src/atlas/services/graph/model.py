"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
The typed domain models the services produce — currently the graph objects.

Split out of ``graph.py`` so the *shape* of a graph (this file) reads separately
from the assembly logic that builds it. ``build_graph`` returns a ``Graph``;
callers that need JSON serialize with ``model_dump()`` / ``model_dump_json()``,
and the cache stores/re-validates the same models.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class Node(BaseModel):
    """A paper in the graph: the normalized S2 node plus its graph annotations.

    The first twelve fields mirror ``semantic_scholar.nodes.node()`` exactly
    (``extra="forbid"`` keeps them in lockstep — if that shape drifts, node
    construction fails loudly rather than silently dropping data). ``rels`` and
    ``is_seed`` are added during assembly.

    ``fields_of_study`` defaults to ``[]`` so snapshots cached before it
    existed (and light neighbor nodes, which don't request it) still validate.
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
    fields_of_study: list[str] = []
    venue: str | None = None
    """The publication venue's display name (arXiv, Nature, NeurIPS…) — a
    detail-tier field like the abstract, so neighbors carry None until the
    panel hydrates them. Defaults so pre-venue cached snapshots validate."""
    oa_pdf: str | None = None
    """The paper's open-access PDF URL (S2 ``openAccessPdf`` / an OpenAlex
    location's ``pdf_url``) — where PDF mining (full text + figures without
    an ar5iv render) reads from. Detail-tier on S2 (neighbors carry None
    until hydration); OpenAlex fills it at neighbor tier too. Defaults so
    pre-oa_pdf cached snapshots validate."""
    rels: list[str]
    is_seed: bool


class Edge(BaseModel):
    """A directed edge between two nodes, tagged by relation.

    Direction encodes citation semantics: an edge always points from the citing
    paper to the cited one — so a ``citation`` edge runs citer -> seed, while a
    ``reference`` edge runs seed -> cited. ``influential`` (S2's "highly
    influential citation" flag) is carried on the citing relation only.

    **``citation`` is every citer, since v7.17.0.** There used to be a third
    type, ``latest``, splitting the recent frontier off from the all-time
    landmarks — two relations because they arrive from two different queries
    (see ``build.py``). Both queries still run and still shape what gets
    fetched; what went is the *distinction on the wire*, because it forced the
    app's own definition of "landmark" onto a reader who has citation counts,
    a year filter and a citation-count filter and can judge for themselves.
    Old cached snapshots and saved sessions still carry ``latest`` edges;
    ``routes/agents.py`` folds them into ``citation`` on the way in, and the
    frontend draws an unrecognised type in a neutral colour.
    """

    model_config = ConfigDict(extra="forbid")

    source: str
    target: str
    type: Literal["reference", "citation"]
    influential: bool | None = None
    rank: int = 0
    """0-based position within this edge's relation, in the relation's own
    order (references by influence, citations by the order the traversal
    produced them — the landmark pool by citation count, then the recent-years
    pool). The frontend ships the whole ranked set
    and the per-relation count slider reveals a prefix — ``rank < slider`` — so
    raising a slider shows more without a re-query. Defaults to 0 so snapshots
    cached before this field validate."""


class Seed(BaseModel):
    """A compact summary of the seed paper, for the graph header."""

    model_config = ConfigDict(extra="forbid")

    arxiv_id: str | None
    id: str
    title: str


class Counts(BaseModel):
    """Per-relation traversal sizes plus the final deduped node count.

    ``citations`` is every citer the build shipped — the landmark pool and the
    recent-years pool together, which since v7.17.0 are one relation (see
    ``Edge``). It was two fields until then.
    """

    model_config = ConfigDict(extra="forbid")

    references: int
    citations: int
    nodes: int


class Graph(BaseModel):
    """A seed paper's assembled neighborhood graph — the app's central object."""

    model_config = ConfigDict(extra="forbid")

    seed: Seed
    nodes: list[Node]
    edges: list[Edge]
    counts: Counts
    citation_source: Literal["corpus", "live"] | None = None
    """Where an **s2** graph's citer relations came from: ``"corpus"`` (the
    offline citations corpus — landmarks citation-sorted across all history) or
    ``"live"`` (the recency-biased live endpoint the corpus couldn't replace for
    this seed). ``None`` for OpenAlex graphs (not applicable) and for snapshots
    cached before this field existed. The frontend keys the provider note off it
    so the user knows which citation source is behind the Field Landmarks."""
