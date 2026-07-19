"""Readable body text straight out of a PDF file.

The pymupdf twin of the ar5iv reader (``integrations/arxiv/fulltext.py``) for
papers that only exist as PDFs. Quality is honest-but-lower: a PDF has no
semantic markup, so headers/footers ride along and equations come out as
whatever Unicode the font encoded — good enough to ground an answer in a
paper's methods and numbers, which is the researcher's use case.
"""

from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger(__name__)


def extract_text(path: str | Path) -> str:
    """Extract a PDF's text, pages joined by blank lines.

    Args:
        path: Filesystem path to the PDF.

    Returns:
        The text, or ``""`` when the file is unparseable or has no
        extractable text (a scanned/image-only PDF) — never raises, since
        the caller treats empty as "unavailable" like a missing ar5iv render.
    """
    import fitz

    try:
        doc = fitz.open(path)
    except Exception:
        log.warning("pymupdf couldn't open %s", path, exc_info=True)
        return ""
    try:
        pages = []
        for page_index in range(doc.page_count):
            page_text = doc.load_page(page_index).get_text("text").strip()
            if page_text:
                pages.append(page_text)
        return "\n\n".join(pages)
    except Exception:
        log.warning("text extraction failed for %s", path, exc_info=True)
        return ""
    finally:
        doc.close()
