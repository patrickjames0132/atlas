"""Load the bundled arXiv taxonomy JSON — the package's data-access layer.

The taxonomy ships as a static file (``taxonomy.json``) next to this module,
sourced once from https://arxiv.org/category_taxonomy rather than fetched at
runtime. ``categories.py`` queries whatever this returns; keeping the load here
mirrors how the HTTP-backed packages isolate their transport in ``client.py``.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_PATH = Path(__file__).resolve().parent / "taxonomy.json"


@lru_cache(maxsize=1)
def data() -> dict:
    """Load and memoize the taxonomy document.

    Returns:
        The parsed taxonomy document (its ``groups`` key holds the areas), read
        and parsed once per process.

    Raises:
        FileNotFoundError: When taxonomy.json is missing.
        json.JSONDecodeError: When the file isn't valid JSON.
    """
    return json.loads(_PATH.read_text())
