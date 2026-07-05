"""ar5iv (https://ar5iv.org) — arXiv's LaTeX→HTML renderer.

Semantic Scholar gives abstracts and TL;DRs but not a paper's figures or its
full body text. ar5iv fills both gaps by rendering the paper's own LaTeX
source to HTML, which this package fetches once and extracts two different
things from:

* ``client``   — the shared HTTP fetch (``fetch_html``), the image-proxy
  fetch + host allowlist (``fetch_image`` / ``is_ar5iv_url``), and the
  shared cache TTL. One external service, one transport layer.
* ``figures``  — pulls ``{image, caption}`` pairs out of the render's
  ``<figure>`` elements, for the detail panel.
* ``fulltext`` — strips the render down to readable body text, for the
  agentic Q&A tool that reads a paper's actual content. Also holds
  ``html_to_text``, a generic HTML-to-text helper reused by the (separate,
  non-ar5iv) web-page source ingester.

This package merges what were two independent modules in the original app
(``figures.py`` and ``fulltext.py``) — they already shared a fetch function
and a TTL constant via one reaching into the other's internals; now both
get it from ``client`` instead. Because of that merge, callers' imports
change (``from ..integrations import figures`` / ``fulltext`` becomes
``from ..integrations import ar5iv``), unlike the semantic_scholar/
arxiv_client splits, which preserved their external interface exactly.
"""

from __future__ import annotations

from .client import fetch_image, is_ar5iv_url
from .figures import get_figures
from .fulltext import get_fulltext, html_to_text

__all__ = ["fetch_image", "get_figures", "get_fulltext", "html_to_text", "is_ar5iv_url"]
