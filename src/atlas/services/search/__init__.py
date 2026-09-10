"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
Seed discovery over the local snapshot cache.

The logic lives in ``discovery`` (``local_search``); this re-exports it so
callers use ``search.local_search(...)`` directly. Live search moved to the
paper scout in v7.6.0 — see ``discovery``.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

from .discovery import (
    cached_nodes,
    display_hits,
    local_search,
    mention_hits,
    merge_mentions,
    rank_mentions,
    valid_fields,
)
from .naming import has_exact_title_match, paper_by_name

__all__ = [
    "cached_nodes",
    "display_hits",
    "has_exact_title_match",
    "local_search",
    "mention_hits",
    "merge_mentions",
    "paper_by_name",
    "rank_mentions",
    "valid_fields",
]
