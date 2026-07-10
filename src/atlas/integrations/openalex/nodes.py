"""Normalizing a raw OpenAlex *work* into the app's graph-node shape — the
OpenAlex twin of ``semantic_scholar/nodes.py``, producing the **same** node dict
so the graph, teacher, and frontend consume one shape regardless of source.

Two OpenAlex-specific translations happen here, both flagged by the spike:

* **Cross-source id.** A citation node must be re-seedable and hydratable
  through the app's existing S2-backed paper routes, so :func:`node` sets the
  node ``id`` to an **S2-resolvable** form — ``DOI:<doi>`` when the work has a
  DOI (nearly every landmark citer does), else ``ARXIV:<id>``, else the bare
  OpenAlex ``W…`` id as a last resort. Clicking such a node hits
  ``/api/paper/<id>`` → ``s2.get_paper`` → S2 resolves the prefix and returns
  the abstract **and TL;DR** OpenAlex itself can't supply (the hybrid's whole
  point). ``arxiv_id`` is filled from the work's arXiv location when present, so
  arXiv links/figures still work.
* **Abstracts** arrive as an inverted index (``{word: [positions]}``), not
  plain text — :func:`reconstruct_abstract` rebuilds the string. Neighbor
  traversals skip it (hydrated lazily on click, like S2's ``NEIGHBOR_FIELDS``).
"""

from __future__ import annotations

from ..arxiv import extract_id

# OpenAlex ``select`` field lists — the analogue of S2's three field tiers,
# trimming the (large) default work object to what a graph node needs.
# ``ids`` carries the OpenAlex id + DOI; ``locations`` is where an arXiv landing
# page (hence the arXiv id) lives.
NEIGHBOR_SELECT = (
    "id,ids,doi,title,display_name,publication_year,publication_date,"
    "cited_by_count,authorships,locations"
)
# Detail adds the inverted-index abstract (heavy — only for a focused node).
DETAIL_SELECT = NEIGHBOR_SELECT + ",abstract_inverted_index"


def bare_openalex_id(work_url: str | None) -> str | None:
    """``"https://openalex.org/W123"`` → ``"W123"`` (None-safe).

    Public (no underscore) because ``traversal`` uses it to build ``cites:``
    filters — per the package convention, anything called across submodules
    isn't single-file-private.
    """
    if not work_url:
        return None
    return work_url.rstrip("/").rsplit("/", 1)[-1]


def _bare_doi(doi_url: str | None) -> str | None:
    """Strip a DOI down to its bare ``10.…`` form.

    OpenAlex reports DOIs as full URLs (``https://doi.org/10.1038/248030a0``);
    S2's ``DOI:`` id prefix wants just the ``10.…`` part.
    """
    if not doi_url:
        return None
    lowered = doi_url.strip()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if lowered.lower().startswith(prefix):
            return lowered[len(prefix) :]
    return lowered or None


def arxiv_id_from_work(work: dict) -> str | None:
    """Extract a bare arXiv id from a work's locations, if any.

    OpenAlex has **no clean arXiv-id field** (the spike's friction point): the id
    only appears inside a location's ``landing_page_url`` (``arxiv.org/abs/…``)
    or the arXiv-minted DOI (``10.48550/arXiv.…``). We scan locations for an
    arXiv source and pull the id out of whichever URL carries it, reusing
    ``arxiv.extract_id`` (the same abs/pdf-URL parser the routes use).

    Args:
        work: A raw OpenAlex work object (must include ``locations``).

    Returns:
        The bare, version-stripped arXiv id, or None when the work isn't on
        arXiv / no id can be parsed.
    """
    for location in work.get("locations") or []:
        source = location.get("source") or {}
        display_name = (source.get("display_name") or "").lower()
        landing = location.get("landing_page_url") or ""
        pdf_url = location.get("pdf_url") or ""
        # Only trust URLs from the arXiv source (a random landing page that
        # merely mentions "arxiv" shouldn't be mined for an id).
        if "arxiv" not in display_name and "arxiv.org" not in landing:
            continue
        for candidate in (landing, pdf_url):
            found = extract_id(candidate)
            if found:
                return found
        # The arXiv-minted DOI (10.48550/arXiv.<id>) also carries the id.
        doi = _bare_doi(location.get("doi"))
        if doi and doi.lower().startswith("10.48550/arxiv."):
            return doi.split(".", 2)[-1]
    return None


def resolvable_id(work: dict, arxiv_id: str | None) -> str | None:
    """The node id to use — an S2-resolvable prefix so the existing paper routes
    can hydrate and re-seed it (see the module docstring).

    Priority: ``DOI:<doi>`` (universal, every landmark citer has one) →
    ``ARXIV:<id>`` → bare OpenAlex ``W…`` (last resort; hydration/re-seed via S2
    won't work for these, but they're rare and still render).

    Args:
        work: The OpenAlex work object.
        arxiv_id: The work's arXiv id, when one was extracted.

    Returns:
        The id string, or None when the work has no usable id at all.
    """
    doi = _bare_doi(work.get("doi"))
    if doi:
        return f"DOI:{doi}"
    if arxiv_id:
        return f"ARXIV:{arxiv_id}"
    return bare_openalex_id(work.get("id"))


def reconstruct_abstract(inverted_index: dict | None) -> str | None:
    """Rebuild plain-text abstract from OpenAlex's inverted index.

    OpenAlex ships abstracts as ``{word: [positions]}`` (a copyright-dodge). We
    invert it back: place each word at each of its positions, then join in
    position order.

    Args:
        inverted_index: The ``abstract_inverted_index`` value, or None.

    Returns:
        The reconstructed abstract, or None when absent/empty.
    """
    if not inverted_index:
        return None
    placed: list[tuple[int, str]] = []
    for word, positions in inverted_index.items():
        for position in positions or []:
            placed.append((position, word))
    if not placed:
        return None
    placed.sort()
    return " ".join(word for _position, word in placed)


def _authors(work: dict) -> str | None:
    """Comma-joined author display names from ``authorships`` (None when empty)."""
    names = [
        (authorship.get("author") or {}).get("display_name", "")
        for authorship in work.get("authorships") or []
    ]
    joined = ", ".join(name for name in names if name)
    return joined or None


def node(work: dict | None) -> dict | None:
    """Normalize a raw OpenAlex work into the app's graph-node dict.

    Produces the identical key set to ``semantic_scholar.nodes.node`` so both
    sources are interchangeable downstream: ``id, arxiv_id, title, abstract,
    tldr, year, month, pub_date, citation_count, authors, url,
    fields_of_study``. ``tldr`` is always None (OpenAlex has none — S2 supplies
    it on click via the DOI-resolvable id); ``fields_of_study`` is ``[]`` for
    the graph render (it hydrates through S2, same as an S2 neighbor node).

    Args:
        work: A raw OpenAlex work object, or None.

    Returns:
        The node dict, or None when ``work`` is empty or has no usable id.
    """
    if not work:
        return None
    arxiv_id = arxiv_id_from_work(work)
    node_id = resolvable_id(work, arxiv_id)
    if not node_id:
        return None
    pub_date = work.get("publication_date")
    month: int | None = None
    if isinstance(pub_date, str) and len(pub_date) >= 7:
        try:
            parsed_month = int(pub_date[5:7])
            month = parsed_month if 1 <= parsed_month <= 12 else None
        except ValueError:
            month = None
    if arxiv_id:
        url = f"https://arxiv.org/abs/{arxiv_id}"
    else:
        doi = _bare_doi(work.get("doi"))
        url = f"https://doi.org/{doi}" if doi else (work.get("id") or "")
    return {
        "id": node_id,
        "arxiv_id": arxiv_id,
        "title": work.get("title") or work.get("display_name") or "(untitled)",
        "abstract": reconstruct_abstract(work.get("abstract_inverted_index")),
        "tldr": None,
        "year": work.get("publication_year"),
        "month": month,
        "pub_date": pub_date if isinstance(pub_date, str) and pub_date else None,
        "citation_count": work.get("cited_by_count"),
        "authors": _authors(work),
        "url": url,
        "fields_of_study": [],
    }
