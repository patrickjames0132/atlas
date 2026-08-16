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

from .discovery import cached_nodes, local_search, valid_fields

__all__ = ["cached_nodes", "local_search", "valid_fields"]
