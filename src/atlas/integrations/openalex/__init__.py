"""``integrations.openalex`` — the hybrid citation backbone.

Since v4.0.0 OpenAlex supplies the graph's **citation** relation (landmark +
latest): a server-sorted ``cites:`` query returns a seed's most-cited citers
directly, which retires S2's newest-first reference-list mining. S2 still owns
the seed resolve, references, the *Similar* relation, and TL;DRs — the two are
matched by DOI / arXiv id, and OpenAlex citer nodes are normalized to
S2-resolvable ids so the existing paper routes hydrate and re-seed them.

Public API mirrors ``semantic_scholar``'s shape so a caller reads the same:

    from ..integrations import openalex
    work = openalex.resolve_work(arxiv_id=..., title=..., year=...)
    landmark, latest = openalex.citation_relations(
        openalex.bare_work_id(work), landmark_limit=..., latest_limit=...
    )
"""

from __future__ import annotations

from .client import OpenAlexError
from .nodes import bare_openalex_id, node
from .traversal import (
    UNBOUNDED_LANDMARK_CAP,
    bare_work_id,
    citation_relations,
    citations,
    landmark_max_year,
    references,
    resolve_seed_work,
    resolve_work,
)

__all__ = [
    "UNBOUNDED_LANDMARK_CAP",
    "OpenAlexError",
    "bare_openalex_id",
    "bare_work_id",
    "citation_relations",
    "citations",
    "landmark_max_year",
    "node",
    "references",
    "resolve_seed_work",
    "resolve_work",
]
