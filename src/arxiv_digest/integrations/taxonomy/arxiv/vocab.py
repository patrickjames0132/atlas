"""Load and query the bundled arXiv category taxonomy.

The implementation behind the ``taxonomy.arxiv`` package: it reads the package's
bundled ``taxonomy.json`` once and answers "what areas/categories exist" and "is
this a real code". See the package ``__init__`` for the what/why.
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
