"""The full arXiv category taxonomy (loaded from taxonomy.json).

Sourced from https://arxiv.org/category_taxonomy.

NOTE: retained but currently DORMANT (no importers) after the v1.4.0 legacy
teardown. Kept deliberately for near-term Atlas features — filtering the graph by
field, the "bridge these topics" mode, or category-scoped seed discovery.
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
        cat["code"] for g in _data()["groups"] for cat in g["categories"]
    )
