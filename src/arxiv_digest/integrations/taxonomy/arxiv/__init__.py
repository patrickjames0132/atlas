"""The arXiv category taxonomy — arXiv's fine-grained subject vocabulary.

The ~155 arXiv category codes (``cs.LG``, ``math.PR``, …) in 8 top-level areas,
each a ``{code, name}`` pair (``cs.LG`` → "Machine Learning"), sourced from
https://arxiv.org/category_taxonomy and bundled inside this package as
``taxonomy.json`` — the data is arXiv-specific, so it lives here rather than at
the shared ``taxonomy`` root. Kept for labelling an arXiv paper's own category
tags. The S2 fields-of-study vocabulary lives in the sibling ``s2`` package.

(Not to be confused with the top-level ``integrations.arxiv`` package — that's
the ar5iv renderer + id regex. This is ``integrations.taxonomy.arxiv``, just the
category list.)

The query logic lives in ``vocab.py``; this package re-exports its public API.
"""

from __future__ import annotations

from .vocab import groups, valid_codes

__all__ = ["groups", "valid_codes"]
