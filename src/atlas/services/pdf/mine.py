"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
The package's cached high-level API: text and floats for one PDF URL.

Layers ``fetch`` (the on-disk PDF cache) under ``text``/``floats`` (the
pymupdf miners) and memoizes results in the SQLite cache, so a paper costs
one download and one mining pass no matter how many reads, panel opens, or
figure renders follow. Misses ("no text", "no floats") are cached too — a
PDF that yields nothing shouldn't be re-mined on every panel open.

Two cache keys per PDF, plus a reverse index:

* ``pdftext:<token>`` / ``pdffloats:<token>`` — the mined results.
* ``pdfurl:<token>`` — token → URL, written whenever mining succeeds. The
  figure route works from tokens alone (the browser never supplies a URL),
  so this reverse lookup is what lets it re-fetch a pruned PDF — and its
  absence for an unknown token is what keeps the route from being an open
  proxy.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

from ...config import config
from ...storage import cache
from . import fetch, floats, text
from .errors import PdfError

# Published PDFs are immutable; cache their mined text/floats for a month
# (same reasoning and TTL as the ar5iv extractors).
CACHE_TTL = 60 * 60 * 24 * 30


def get_pdf_text(url: str, *, refresh: bool = False) -> dict:
    """Fetch a PDF (cached) and extract its readable text (cached).

    Args:
        url: The PDF's absolute URL.
        refresh: When True, bypass the mined-text cache and re-extract.

    Returns:
        ``{"available": bool, "text": str}`` — ``available`` is False (empty
        text) when the download or extraction fails; that miss is cached.
        The text is cached whole; callers truncate to their own budget.
    """
    key = f"pdftext:{fetch.url_token(url)}"
    if not refresh:
        cached = cache.get(key, CACHE_TTL)
        if cached is not None:
            return cached
    try:
        path = fetch.fetch_pdf(url)
    except PdfError:
        result = {"available": False, "text": ""}
        cache.set(key, result)
        return result
    extracted = text.extract_text(path)
    result = {"available": bool(extracted), "text": extracted}
    cache.set(key, result)
    cache.set(f"pdfurl:{fetch.url_token(url)}", url)
    return result


def get_pdf_floats(url: str, *, refresh: bool = False) -> dict:
    """Fetch a PDF (cached) and mine its caption-anchored floats (cached).

    Args:
        url: The PDF's absolute URL.
        refresh: When True, bypass the cached figure manifest and re-mine.

    Returns:
        ``{"available": bool, "token": str, "floats": [...]}`` — each float
        as ``extract_floats`` describes it. ``available`` is False (empty
        list) when the download fails or nothing anchors; misses are cached.
        ``token`` is the stable id the figure route uses to name renders of
        this PDF (``/api/pdf_figure/<token>/<index>``).
    """
    token = fetch.url_token(url)
    key = f"pdffloats:{token}"
    if not refresh:
        cached = cache.get(key, CACHE_TTL)
        if cached is not None:
            return cached
    try:
        path = fetch.fetch_pdf(url)
    except PdfError:
        result = {"available": False, "token": token, "floats": []}
        cache.set(key, result)
        return result
    mined = floats.extract_floats(
        path, max_floats=config.pdf.research_papers.max_floats, max_pages=config.pdf.research_papers.max_pages
    )
    result = {"available": bool(mined), "token": token, "floats": mined}
    cache.set(key, result)
    cache.set(f"pdfurl:{token}", url)
    return result


def render_figure(token: str, index: int) -> bytes:
    """Render one manifest entry to PNG, addressed by token + list index.

    The route's workhorse: resolves the token back to its URL (only tokens
    this app itself minted resolve — an invented one has no ``pdfurl`` entry),
    re-fetches the PDF if the LRU pruned it, and renders the float's region.

    Args:
        token: The PDF's ``url_token`` as reported by ``get_pdf_floats``.
        index: 0-based index into that PDF's figure manifest.

    Returns:
        PNG bytes.

    Raises:
        PdfError: For an unknown token, an out-of-range index, or a failed
            fetch/render.
    """
    url = cache.get(f"pdfurl:{token}")
    if not isinstance(url, str) or not url:
        raise PdfError(f"unknown PDF token {token!r}")
    mined = get_pdf_floats(url)
    entries = mined.get("floats") or []
    if not 0 <= index < len(entries):
        raise PdfError(f"float index {index} out of range for token {token!r}")
    entry = entries[index]
    path = fetch.fetch_pdf(url)
    return floats.render_float(path, entry["page"], entry["region"])
