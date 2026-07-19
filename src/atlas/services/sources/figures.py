"""Figures out of the user's own uploaded PDFs — the library twin of
``services/pdf``'s open-access mining.

Since v5.28.0 an uploaded PDF's original file is kept beside its indexed text
(``store.pdf_path``), so the same caption-anchored extractor that mines
journal papers (``services.pdf.floats``) can mine the user's own material:
one **figure manifest** per source (kind, page, caption, region — cached in
SQLite; no pixels stored), with images rendered on demand by the
``/api/sources/<id>/figure/<n>`` route.

What differs from the OA pipeline is only addressing: no URL, no download —
the file is local and owned by us, keyed by source id. URL sources and
sources ingested before the file was kept have no PDF on disk and degrade to
"no figures", never an error.
"""

from __future__ import annotations

import logging

from ...config import config
from ...storage import cache
from ..pdf import floats
from ..pdf.errors import PdfError
from . import store

log = logging.getLogger(__name__)

# Same reasoning as the OA-PDF caches: the file is immutable, but the mining
# heuristics improve — a month TTL rolls better extraction out by itself
# (docs/pdf-mining.md tells the full story).
CACHE_TTL = 60 * 60 * 24 * 30

# How a wrong-page miss lists the extractable candidates (see
# resolve_page_figure): enough caption to judge relevance, few enough
# entries to stay a steering message rather than a dump.
_MAX_CANDIDATES = 8
_CANDIDATE_CAPTION = 80


def get_source_figures(source_id: str, *, refresh: bool = False) -> dict:
    """The figure manifest mined from a source's stored PDF, cached.

    Args:
        source_id: The source's id.
        refresh: When True, bypass the cached manifest and re-mine.

    Returns:
        ``{"available": bool, "floats": [...]}`` — each entry as
        ``services.pdf.floats.extract_floats`` describes it. ``available``
        is False (empty list) for URL sources, sources ingested before the
        PDF was kept, and PDFs where nothing anchors; misses are cached.
    """
    # v3: v1 manifests were mined with paper-sized caps (80 pages / 12
    # floats) that silently truncated textbooks; v2 still dropped
    # small-piece line drawings (backup diagrams). Key bumps remine.
    key = f"srcfloats:v3:{source_id}"
    if not refresh:
        cached = cache.get(key, CACHE_TTL)
        if cached is not None:
            return cached
    path = store.pdf_path(source_id)
    if not path.exists():
        result = {"available": False, "floats": []}
        cache.set(key, result)
        return result
    mined = floats.extract_floats(
        path,
        max_floats=config.pdf.library_documents.max_floats,
        max_pages=config.pdf.library_documents.max_pages,
    )
    result = {"available": bool(mined), "floats": mined}
    cache.set(key, result)
    return result


def resolve_page_figure(source_id: str, page: int, figure: int) -> tuple[dict | None, str]:
    """Resolve "figure N on page P of source S" against the mined manifest.

    The shared core of the researcher's and the librarian's
    ``show_source_figure`` tools: both address figures the way passages are
    cited (source + page), and both need the same steerable error text when
    the address misses; only budgets/traces/events differ, and those stay in
    each agent's wrapper.

    Args:
        source_id: The source's id.
        page: The 1-based page the figure should be on.
        figure: Which figure on that page, 1-based.

    Returns:
        ``(resolution, "")`` on success — ``resolution`` carrying ``title``,
        ``manifest_index`` (the entry's 0-based index, i.e. the figure
        route's ``<n>``), and ``entry`` (the manifest entry) — or
        ``(None, message)`` with model-steerable text: unknown source,
        nothing extractable, a page without figures (listing the pages that
        have them), or a figure number past the page's count.
    """
    source = store.get_source(source_id)
    if source is None or page < 1 or figure < 1:
        return None, (
            f"Invalid figure request (source_id={source_id!r}, page={page}, figure={figure})."
        )
    title = source["title"]
    mined = get_source_figures(source_id)
    entries = mined.get("floats") or []
    if not entries:
        return None, (
            f'"{title}" has no extractable figures (URL sources and older uploads have none).'
        )
    on_page = [
        (position, entry) for position, entry in enumerate(entries) if entry["page"] == page
    ]
    if not on_page:
        # List the extractable candidates WITH captions, so the model can
        # judge whether any is actually the figure it wants — a bare page
        # list invites grabbing an unrelated figure and mislabeling it
        # (docs/bugs.md: the backup-diagrams incident). Nearest pages first:
        # in a 500-page textbook the useful candidates are the ones around
        # the cited page, not chapter 1's.
        nearest = sorted(entries, key=lambda entry: abs(entry["page"] - page))
        shown = sorted(nearest[:_MAX_CANDIDATES], key=lambda entry: entry["page"])
        candidates = "; ".join(
            f'p.{entry["page"]} "{(entry.get("caption") or "")[:_CANDIDATE_CAPTION]}"'
            for entry in shown
        )
        more = " …" if len(entries) > _MAX_CANDIDATES else ""
        return None, (
            f'No extractable figures on page {page} of "{title}" (uncaptioned '
            f"inline diagrams can't be extracted). Its extractable figures: "
            f"{candidates}{more}. Only attach one if its caption matches what "
            f"you want to show — otherwise explain in prose instead."
        )
    if figure > len(on_page):
        return None, (
            f'Page {page} of "{title}" has only {len(on_page)} figure(s); '
            f"{figure} doesn't exist."
        )
    manifest_index, entry = on_page[figure - 1]
    return {"title": title, "manifest_index": manifest_index, "entry": entry}, ""


def render_source_figure(source_id: str, index: int) -> bytes:
    """Render one of a source's manifest entries to PNG.

    Args:
        source_id: The source's id.
        index: 0-based index into the source's figure manifest.

    Returns:
        PNG bytes.

    Raises:
        PdfError: When the source has no stored PDF, the index is out of
            range, or rendering fails.
    """
    mined = get_source_figures(source_id)
    entries = mined.get("floats") or []
    if not 0 <= index < len(entries):
        raise PdfError(f"figure index {index} out of range for source {source_id!r}")
    entry = entries[index]
    path = store.pdf_path(source_id)
    if not path.exists():
        raise PdfError(f"no stored PDF for source {source_id!r}")
    return floats.render_float(path, entry["page"], entry["region"])
