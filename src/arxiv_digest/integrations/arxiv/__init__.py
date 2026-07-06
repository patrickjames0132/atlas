"""Everything the app derives directly from arXiv itself.

Three things live here, all arXiv-specific and all for arXiv papers only:

* **arXiv-id detection** (``ID_RE``, at the package root below) — recognizing a
  bare or URL-wrapped arXiv id, so a pasted id/link routes to that exact paper
  instead of a keyword hunt.
* **ar5iv rendering** — a paper's figures + full body text, extracted from
  ar5iv (https://ar5iv.org, arXiv's LaTeX→HTML renderer):
  * ``client``   — the shared HTTP fetch (``fetch_html``), the image-proxy
    fetch + host allowlist (``fetch_image`` / ``is_ar5iv_url``), and the cache
    TTL.
  * ``figures``  — ``{image, caption}`` pairs from the render's ``<figure>``s.
  * ``fulltext`` — the render stripped to readable body text; also
    ``html_to_text``, a generic helper reused by the web-page source ingester.
* **the arXiv category taxonomy** (``vocab`` — ``groups`` / ``valid_codes`` over
  the bundled ``taxonomy.json``): the ~155 arXiv category codes, for labelling
  an arXiv paper's own tags. S2's parallel vocabulary is ``semantic_scholar.vocab``.

This package was ``ar5iv`` until we consolidated all arXiv-derived code into one
place (2026-07-05): the ar5iv renderer plus ``ID_RE``, which used to sit in the
separate ``arxiv_client`` package. That package (arXiv *search*) was retired in
favour of Semantic Scholar search and deleted, along with the PyPI ``arxiv``
dependency it was the only user of — so ``ID_RE`` moved here rather than
disappearing with it.
"""

from __future__ import annotations

import re

from . import vocab
from .client import fetch_image, is_ar5iv_url
from .figures import get_figures
from .fulltext import get_fulltext, html_to_text

# A bare arXiv id (new-style "2406.12345" / "2406.12345v2", or old-style
# "hep-th/9901001"), optionally wrapped in an arxiv.org URL. Group 1 is the bare
# id. Lets a search box accept a pasted id or link and fetch that exact paper
# instead of a keyword hunt; also used by services/graph.py and routes/graph.py
# to detect an id pasted into a re-seed action, outside of search entirely.
ID_RE = re.compile(
    r"(?:https?://)?(?:arxiv\.org/(?:abs|pdf)/)?"
    r"(\d{4}\.\d{4,5}(?:v\d+)?|[a-z-]+(?:\.[A-Z]{2})?/\d{7}(?:v\d+)?)",
    re.IGNORECASE,
)

def looks_arxiv(ref: str) -> bool:
    """Distinguish an arXiv id from a raw Semantic Scholar paperId.

    A paper reference can arrive as either — an arXiv id (from the search box
    or a pasted link) or a raw S2 ``paperId`` (from clicking a node in an
    existing graph). S2's lookup needs them addressed differently (an arXiv id
    must be prefixed ``ARXIV:``), so callers sniff which one they're holding.

    Args:
        ref: The paper reference the user (or a re-seed click) supplied.

    Returns:
        True when ``ref`` is *entirely* an arXiv id (new- or old-style, with or
        without a version suffix). ``fullmatch`` — not ``search`` — because a
        bare S2 paperId must NOT be mistaken for one.
    """
    return bool(ID_RE.fullmatch(ref))


__all__ = [
    "ID_RE",
    "fetch_image",
    "get_figures",
    "get_fulltext",
    "html_to_text",
    "is_ar5iv_url",
    "looks_arxiv",
    "vocab",
]
