"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
Open-access PDF mining: full text and figures for papers ar5iv can't serve.

The package's public surface, re-exported from its submodules:

* ``resolve_oa_pdf`` / ``prime`` / ``arxiv_pdf_url`` — where a paper's OA
  PDF lives (``resolve.py``).
* ``get_pdf_text`` / ``get_pdf_floats`` / ``render_figure`` — the cached
  mining API (``mine.py``).
* ``PdfError`` — the package's one exception (``errors.py``).

See this package's README for the design story, and ``docs/pdf-mining.md``
for the storage rationale (why the PDF is the cache, everything else derived).

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from .errors import PdfError
from .mine import get_pdf_floats, get_pdf_text, render_figure
from .resolve import arxiv_pdf_url, prime, resolve_oa_pdf

__all__ = [
    "PdfError",
    "arxiv_pdf_url",
    "get_pdf_floats",
    "get_pdf_text",
    "prime",
    "render_figure",
    "resolve_oa_pdf",
]
