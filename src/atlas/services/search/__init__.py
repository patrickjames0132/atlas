"""Seed discovery: a live relevance search across Semantic Scholar, plus an
instant search over the local snapshot cache.

The logic lives in ``discovery`` (``live_search`` + ``local_search``); this
re-exports it so callers use ``search.live_search(...)`` directly.
"""

from __future__ import annotations

from .discovery import live_search, local_search

__all__ = ["live_search", "local_search"]
