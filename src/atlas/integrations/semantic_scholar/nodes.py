"""Normalizing a raw Semantic Scholar paper object into the app's graph-node
shape — the single place that shape is defined.

Every S2 response — batch hydration, references, citations, recommendations,
search — funnels through ``node()``. Everything downstream (graph assembly,
the teacher, the frontend) consumes the dict it produces.
"""

from __future__ import annotations

# Rich fields for a focused node (the seed, or a clicked node). Requested via
# the un-throttled batch endpoint.
DETAIL_FIELDS = (
    "paperId,externalIds,title,abstract,tldr,year,publicationDate,"
    "citationCount,referenceCount,authors.name"
)
# Lighter fields for the many neighbors in a traversal — no abstract/tldr,
# which we hydrate lazily when a node is opened. publicationDate gives month
# granularity for the timeline layout.
NEIGHBOR_FIELDS = "paperId,externalIds,title,year,publicationDate,citationCount"
# Search hits render in a pick-a-paper list where authorship is how humans
# recognize a paper — worth the extra field there, but not for the ~65
# anonymous dots of a graph traversal.
SEARCH_FIELDS = NEIGHBOR_FIELDS + ",authors.name"


def node(paper: dict | None) -> dict | None:
    """Normalize a raw S2 paper object into the app's graph-node dict.

    Args:
        paper: A paper object as returned by S2, or None (S2 uses null for
            ids it can't resolve).

    Returns:
        A node dict with keys ``id, arxiv_id, title, abstract, tldr, year,
        month, pub_date, citation_count, authors, url`` — or None when
        ``paper`` is empty or carries no ``paperId``. ``month`` (1–12) is
        parsed from S2's ``publicationDate`` so the timeline can place
        papers between year lines; it is None when only the year is known.
    """
    if not paper or not paper.get("paperId"):
        return None
    external_ids = paper.get("externalIds") or {}
    arxiv_id = external_ids.get("ArXiv")
    tldr_obj = paper.get("tldr")
    tldr = tldr_obj.get("text") if isinstance(tldr_obj, dict) else None
    pub_date = paper.get("publicationDate")
    month: int | None = None
    if isinstance(pub_date, str) and len(pub_date) >= 7:
        try:
            parsed_month = int(pub_date[5:7])
            month = parsed_month if 1 <= parsed_month <= 12 else None
        except ValueError:
            month = None
    authors = ", ".join(
        author.get("name", "") for author in (paper.get("authors") or []) if author.get("name")
    )
    if arxiv_id:
        url = f"https://arxiv.org/abs/{arxiv_id}"
    else:
        url = f"https://www.semanticscholar.org/paper/{paper['paperId']}"
    return {
        "id": paper["paperId"],
        "arxiv_id": arxiv_id,
        "title": paper.get("title") or "(untitled)",
        "abstract": paper.get("abstract"),
        "tldr": tldr,
        "year": paper.get("year"),
        "month": month,
        "pub_date": pub_date if isinstance(pub_date, str) and pub_date else None,
        "citation_count": paper.get("citationCount"),
        "authors": authors or None,
        "url": url,
    }


def from_papers(papers: list) -> list[dict]:
    """Normalize a raw list of S2 paper objects into ``{"node": ...}`` entries.

    Shared by callers that don't need anything beyond the plain node — e.g.
    recommendations and free-text search results. (Citation traversal adds
    its own ``"influential"`` flag, so it builds this shape itself.)

    Args:
        papers: Raw paper objects as returned by S2.

    Returns:
        A list of ``{"node": <node dict>}`` entries, skipping papers S2
        couldn't resolve.
    """
    out = []
    for paper in papers:
        normalized = node(paper)
        if normalized:
            out.append({"node": normalized})
    return out
