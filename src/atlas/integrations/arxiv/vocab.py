"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
The arXiv category taxonomy — arXiv's fine-grained subject vocabulary.

The ~155 arXiv category codes (``cs.LG``, ``math.PR``, …) with their display
names (``cs.LG`` → "Machine Learning"), sourced from
https://arxiv.org/category_taxonomy and bundled beside this module as
``taxonomy.json``. Lives in the ``arxiv`` package (with ar5iv + ``ID_RE``)
because it's arXiv-specific — for **labelling an arXiv paper's own category
tags** in the detail panel (``name_for``). Semantic Scholar's parallel (coarser)
vocabulary is ``semantic_scholar.vocab``.

(The area-tree ``groups()`` and ``valid_codes()`` accessors were removed in
v5.1.0 — they fed the retired arXiv-category *search filter*; only per-paper
tag labelling remains.)

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
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


@lru_cache(maxsize=1)
def _names_by_code() -> dict[str, str]:
    """Build the code -> display-name map once, from the bundled taxonomy.

    Returns:
        Every category code mapped to its human-readable name.
    """
    return {
        category["code"]: category["name"]
        for group in _data()["groups"]
        for category in group["categories"]
    }


def name_for(code: str) -> str | None:
    """Look up a category code's display name (``cs.LG`` -> "Machine Learning").

    For labelling a paper's *own* category tags in the detail panel — the
    codes themselves come from arXiv's per-paper metadata, not from here.

    Args:
        code: An arXiv category code.

    Returns:
        The display name, or None when the code isn't in the bundled taxonomy
        (arXiv occasionally retires/renames categories; an unrecognized code
        still displays, just without a label).
    """
    return _names_by_code().get(code)
