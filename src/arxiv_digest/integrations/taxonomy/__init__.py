"""The app's controlled subject vocabularies — one submodule per source.

* ``arxiv`` — arXiv's ~155 fine-grained category codes (``groups()``,
  ``valid_codes()``), bundled from ``taxonomy.json``. arXiv-specific; for
  labelling an arXiv paper's own category tags.
* ``s2``    — Semantic Scholar's ~20 coarse fields of study (``fields()``,
  ``valid_fields()``), an inline list. What the live S2 seed-search filter uses.

Access is namespaced by source — ``taxonomy.arxiv.groups()``,
``taxonomy.s2.fields()`` — so the two vocabularies never blur together. (Note
``taxonomy.arxiv`` is just the category list; the separate top-level
``integrations.arxiv`` package is the ar5iv renderer + id regex. Different
things, told apart by their full import path.)

The odd one out among the integrations: static/inline data, no HTTP, no cache.
"""

from __future__ import annotations

from . import arxiv, s2

__all__ = ["arxiv", "s2"]
