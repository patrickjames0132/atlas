"""The arXiv category taxonomy — arXiv-specific enrichment for arXiv papers.

The ~155 arXiv category codes (``cs.LG``, ``math.PR``, …) in 8 top-level areas,
each a ``{code, name}`` pair (``cs.LG`` → "Machine Learning"), sourced from
https://arxiv.org/category_taxonomy and bundled as ``taxonomy.json``. Kept for
arXiv papers only — same spirit as the ar5iv package. This describes *what*
categories exist; a given paper's own categories come from arXiv metadata, not
Semantic Scholar.

* ``loader``     — loads + memoizes the bundled ``taxonomy.json`` (data access).
* ``categories`` — the query API: ``groups()`` (the areas tree) and
  ``valid_codes()`` (the validation set).

The odd one out among the integrations: static bundled data, so no HTTP client
and no cache — but split into a package the same transport-vs-domain way as its
neighbours so they all read alike.
"""

from __future__ import annotations

from .categories import groups, valid_codes

__all__ = ["groups", "valid_codes"]
