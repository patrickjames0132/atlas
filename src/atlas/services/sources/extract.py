"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
Turn a raw source into clean, chunked text ready to embed.

Two extractors — ``extract_pdf`` (pymupdf, page-aware) and ``fetch_url`` (a web
page reduced to readable text) — plus ``chunk_text``, which splits extracted
text into the overlapping windows the embedder indexes.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

import re
import urllib.error
import urllib.request
from pathlib import Path

from ...config import config
from ...integrations.arxiv import html_to_text
from .errors import SourceError


def chunk_text(text: str, size: int, overlap: int) -> list[str]:
    """Split text into overlapping windows for embedding.

    Windows are ~``size`` chars, breaking on a space near each boundary so
    chunks don't cut mid-word; whitespace is collapsed first. Consecutive
    windows share ``overlap`` chars so a sentence straddling a boundary stays
    findable from either side.

    Args:
        text: The raw text to split.
        size: Target window size in characters.
        overlap: Characters of overlap carried between consecutive windows.

    Returns:
        The chunk strings, in order; empty when ``text`` is blank.
    """
    text = " ".join(text.split())
    if not text:
        return []
    if len(text) <= size:
        return [text]
    chunks: list[str] = []
    length = len(text)
    start = 0
    while start < length:
        end = min(start + size, length)
        if end < length:
            space_pos = text.rfind(" ", start + size - overlap, end)
            if space_pos > start:
                end = space_pos
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= length:
            break
        start = max(end - overlap, start + 1)
    return chunks


def extract_pdf(path: str | Path) -> tuple[list[tuple[int, str]], int]:
    """Extract per-page text from a PDF.

    Args:
        path: Filesystem path to the PDF.

    Returns:
        A ``(pages, total)`` tuple: ``pages`` is ``[(page_no, text)]`` for pages
        that had extractable text (1-based numbering), ``total`` is the
        document's full page count.

    Raises:
        SourceError: For a scanned/image-only PDF (no extractable text — OCR
            isn't supported yet), or when no text was found at all.
        fitz.FileDataError: When the file isn't a readable PDF.
    """
    import fitz  # pymupdf

    doc = fitz.open(path)
    try:
        total = doc.page_count
        pages: list[tuple[int, str]] = []
        for index in range(total):
            text = doc.load_page(index).get_text("text")
            if text and text.strip():
                pages.append((index + 1, text))
    finally:
        doc.close()
    if total >= 3 and sum(len(text) for _, text in pages) < 100:
        raise SourceError(
            "This PDF appears to be scanned/image-only — no extractable text. "
            "OCR isn't supported yet."
        )
    if not pages:
        raise SourceError("No extractable text found in this PDF.")
    return pages, total


_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)


def fetch_url(url: str) -> tuple[str, str | None]:
    """Fetch a web page and reduce it to readable text.

    Args:
        url: The page URL.

    Returns:
        A ``(readable_text, page_title)`` tuple; the title is None when the page
        declares none.

    Raises:
        SourceError: On network failure or when no readable text could be
            extracted.
    """
    request = urllib.request.Request(url, headers={"User-Agent": "atlas/1.1"})
    try:
        with urllib.request.urlopen(request, timeout=config.providers.s2.timeout) as response:
            raw = response.read()
    except (urllib.error.URLError, urllib.error.HTTPError) as exc:
        raise SourceError(f"Couldn't fetch {url}: {exc}") from exc
    html = raw.decode("utf-8", errors="replace")
    text = html_to_text(html)
    if not text.strip():
        raise SourceError(f"No readable text extracted from {url}.")
    match = _TITLE_RE.search(html)
    title = " ".join(match.group(1).split()) if match else None
    return text, title
