"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
``integrations.openalex`` — the hybrid citation backbone.

Since v4.0.0 OpenAlex supplies the graph's **citation** relation (landmark +
latest): a server-sorted ``cites:`` query returns a seed's most-cited citers
directly, which retires S2's newest-first reference-list mining. S2 still owns
the seed resolve, references, the *Similar* relation, and TL;DRs — the two are
matched by DOI / arXiv id, and OpenAlex citer nodes are normalized to
S2-resolvable ids so the existing paper routes hydrate and re-seed them.

Public API mirrors ``semantic_scholar``'s shape so a caller reads the same:

    from ..integrations import openalex
    work = openalex.resolve_work(arxiv_id=..., title=..., year=...)
    landmark, latest = openalex.citation_relations(openalex.bare_work_id(work))

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

from . import vocab
from .client import OpenAlexError
from .nodes import bare_openalex_id, node
from .search import search_papers
from .traversal import (
    bare_work_id,
    citation_relations,
    citations,
    get_paper,
    landmark_max_year,
    references,
    related_works,
    resolve_seed_work,
    resolve_work,
)

__all__ = [
    "OpenAlexError",
    "bare_openalex_id",
    "bare_work_id",
    "citation_relations",
    "citations",
    "get_paper",
    "landmark_max_year",
    "node",
    "references",
    "related_works",
    "resolve_seed_work",
    "resolve_work",
    "search_papers",
    "vocab",
]
