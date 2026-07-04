"""SQLite persistence.

* ``cache``    — a thin TTL key/JSON-blob cache for dynamically-fetched
  artifacts (graph snapshots, ar5iv text/figures), in ``digest.db``.
* ``sessions`` — the durable saved-sessions store (Phase 4), in its own
  ``sessions.db`` since saved workspaces have their own lifecycle and are
  never TTL-evicted.

(The bring-your-own-sources library also persists to SQLite, but it lives in
``library/`` — its vector index and ingestion pipeline make it a subsystem,
not just a table.)
"""
