"""The arXiv category taxonomy — arXiv's fine-grained subject vocabulary.

The ~155 arXiv category codes (``cs.LG``, ``math.PR``, …) in 8 top-level areas,
each a ``{code, name}`` pair (``cs.LG`` → "Machine Learning"), sourced from
https://arxiv.org/category_taxonomy and bundled next to this module as
``taxonomy.json``. arXiv-specific — kept for labelling an arXiv paper's own
category tags. The S2 fields-of-study vocabulary lives in the sibling ``s2``
module.

(Not to be confused with the top-level ``integrations.arxiv`` package — that's
the ar5iv renderer + id regex. This is ``integrations.taxonomy.arxiv``, just the
category list.)
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_PATH = Path(__file__).resolve().parent / "taxonomy.json"


@lru_cache(maxsize=1)
def _data() -> dict:
    """Load and memoize the bundled taxonomy JSON.

    Returns:
        The parsed taxonomy document (its ``groups`` key holds the areas), read
        once per process. Private — only this module reads it.

    Raises:
        FileNotFoundError: When taxonomy.json is missing.
        json.JSONDecodeError: When the file isn't valid JSON.
    """
    return json.loads(_PATH.read_text())


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
