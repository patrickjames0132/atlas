"""The full arXiv category taxonomy (loaded from taxonomy.json).

Sourced from https://arxiv.org/category_taxonomy: the ~155 arXiv category codes
(``cs.LG``, ``math.PR``, …) grouped into 8 top-level areas, each entry a
``{code, name}`` pair (``cs.LG`` → "Machine Learning").

arXiv-specific enrichment, kept for arXiv papers only — same spirit as the
ar5iv package. This module only describes *what* categories exist; a given
paper's own categories come from arXiv metadata, not Semantic Scholar. See the
integrations README for who consumes it.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_TAXONOMY_PATH = Path(__file__).resolve().parent / "taxonomy.json"


@lru_cache(maxsize=1)
def _data() -> dict:
    """Load and memoize the taxonomy JSON.

    Returns:
        The parsed taxonomy document (its ``groups`` key holds the areas).

    Raises:
        FileNotFoundError: When taxonomy.json is missing.
        json.JSONDecodeError: When the file isn't valid JSON.
    """
    return json.loads(_TAXONOMY_PATH.read_text())


def groups() -> list[dict]:
    """List the taxonomy's top-level areas.

    Returns:
        Categories grouped by top-level area; each category is
        ``{"code", "name"}``.
    """
    return _data()["groups"]


@lru_cache(maxsize=1)
def valid_codes() -> frozenset[str]:
    """Collect every valid category code.

    Returns:
        A frozenset of all category codes, for validating user selections.
    """
    return frozenset(
        category["code"]
        for group in _data()["groups"]
        for category in group["categories"]
    )
