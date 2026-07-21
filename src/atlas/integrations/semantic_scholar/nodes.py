"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
Normalizing a raw Semantic Scholar paper object into the app's graph-node
shape — the single place that shape is defined.

Every S2 response — batch hydration, references, citations, recommendations,
search — funnels through ``node()``. Everything downstream (graph assembly,
the teacher, the frontend) consumes the dict it produces.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

# Rich fields for a focused node (the seed, or a clicked node). Requested via
# the un-throttled batch endpoint. ``s2FieldsOfStudy`` is S2's own
# field-of-study classification (the detail panel shows it as a second tag
# layer beside a paper's arXiv categories); ``fieldsOfStudy`` is the coarser
# legacy list we fall back to when the classifier field is absent.
DETAIL_FIELDS = (
    "paperId,externalIds,title,abstract,tldr,year,publicationDate,"
    "citationCount,referenceCount,authors.name,s2FieldsOfStudy,fieldsOfStudy,"
    "venue,publicationVenue,openAccessPdf"
)
# Lighter fields for the many neighbors in a traversal — no abstract/tldr,
# which we hydrate lazily when a node is opened. publicationDate gives month
# granularity for the timeline layout.
NEIGHBOR_FIELDS = "paperId,externalIds,title,year,publicationDate,citationCount"
# Search hits render in a pick-a-paper list where authorship is how humans
# recognize a paper — worth the extra field there, but not for the ~65
# anonymous dots of a graph traversal.
SEARCH_FIELDS = NEIGHBOR_FIELDS + ",authors.name"


def fields_of_study(paper: dict) -> list[str]:
    """Extract S2's field-of-study categories as a deduped name list.

    Prefers ``s2FieldsOfStudy`` (S2's classifier output, a list of
    ``{"category", "source"}`` — the same category can appear from more than
    one source, so names are deduped in first-seen order) and falls back to
    the coarser ``fieldsOfStudy`` (a plain list of strings) when the
    classifier field is absent or empty.

    Args:
        paper: A raw S2 paper object.

    Returns:
        The field-of-study names, deduped and order-preserving (e.g.
        ``["Computer Science", "Mathematics"]``); empty when S2 lists none or
        the fields weren't requested.
    """
    names: list[str] = []
    seen: set[str] = set()
    for entry in paper.get("s2FieldsOfStudy") or []:
        category = entry.get("category") if isinstance(entry, dict) else None
        if category and category not in seen:
            seen.add(category)
            names.append(category)
    if names:
        return names
    for category in paper.get("fieldsOfStudy") or []:
        if category and category not in seen:
            seen.add(category)
            names.append(category)
    return names


def venue_name(paper: dict) -> str | None:
    """The paper's publication venue, preferring S2's normalized record.

    ``publicationVenue`` is S2's normalized venue object (proper display
    names — "Neural Information Processing Systems"); the legacy ``venue``
    string is the fallback when the normalized record is absent. Both are
    detail-tier fields (DETAIL_FIELDS), so neighbor nodes return None until
    the panel hydrates them.

    Args:
        paper: A raw S2 paper object.

    Returns:
        The venue's display name, or None when unknown/not requested.
    """
    publication_venue = paper.get("publicationVenue")
    if isinstance(publication_venue, dict) and publication_venue.get("name"):
        return str(publication_venue["name"])
    return paper.get("venue") or None


def node(paper: dict | None) -> dict | None:
    """Normalize a raw S2 paper object into the app's graph-node dict.

    Args:
        paper: A paper object as returned by S2, or None (S2 uses null for
            ids it can't resolve).

    Returns:
        A node dict with keys ``id, arxiv_id, title, abstract, tldr, year,
        month, pub_date, citation_count, authors, url, fields_of_study,
        venue, oa_pdf`` — or None when ``paper`` is empty or carries no
        ``paperId``. ``month`` (1–12) is parsed from S2's ``publicationDate``
        so the timeline can place papers between year lines; it is None when
        only the year is known. ``fields_of_study`` is empty — and ``venue``
        and ``oa_pdf`` None — for neighbor/search nodes, which don't request
        them; all hydrate when the node is opened (DETAIL_FIELDS). ``oa_pdf``
        is S2's ``openAccessPdf`` URL — where the paper's PDF-mining
        fallback (full text and figures without an ar5iv render) reads from.
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
    open_access = paper.get("openAccessPdf")
    oa_pdf = open_access.get("url") if isinstance(open_access, dict) else None
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
        "fields_of_study": fields_of_study(paper),
        "venue": venue_name(paper),
        "oa_pdf": oa_pdf or None,
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
