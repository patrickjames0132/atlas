"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
SQLite persistence.

* ``cache``    — a thin TTL key/JSON-blob cache for dynamically-fetched
  artifacts (graph snapshots, ar5iv text/figures), in ``digest.db``.
* ``sessions`` — the durable saved-sessions store, in its own
  ``sessions.db`` since saved workspaces have their own lifecycle and are
  never TTL-evicted.

(The bring-your-own-sources subsystem also persists to SQLite, in its own
``sources.db`` — its vector index and ingestion pipeline make it a
subsystem, not just a table.)

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""
