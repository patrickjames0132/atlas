"""A thin TTL cache for dynamically-fetched artifacts (graph snapshots now;
lecture scripts and mindmaps later).

arXiv Atlas deliberately does NOT store a paper corpus — millions of papers are
many TB and the ecosystem (Semantic Scholar / arXiv) already hosts them. This is
just a small key -> JSON-blob table so we can respect Semantic Scholar's tight
rate limit and avoid re-fetching the same neighborhood on every view. It lives in
the same SQLite file as the (legacy) digest tables but is otherwise independent.
"""

from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from typing import Any, Iterator, Optional

from . import config

_SCHEMA = """
CREATE TABLE IF NOT EXISTS cache (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    created_at REAL NOT NULL
);
"""


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    config.ensure_dirs()
    conn = sqlite3.connect(config.DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute(_SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


def get(key: str, max_age: Optional[float] = None) -> Optional[Any]:
    """Return the cached JSON value for `key`, or None if missing/expired.

    `max_age` is in seconds; None means never expire.
    """
    with _connect() as conn:
        row = conn.execute(
            "SELECT value, created_at FROM cache WHERE key = ?", (key,)
        ).fetchone()
    if not row:
        return None
    if max_age is not None and (time.time() - row["created_at"]) > max_age:
        return None
    try:
        return json.loads(row["value"])
    except (ValueError, TypeError):
        return None


def set(key: str, value: Any) -> None:
    """Store `value` (JSON-serializable) under `key`, stamped with the time now."""
    with _connect() as conn:
        conn.execute(
            "INSERT INTO cache (key, value, created_at) VALUES (?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value, "
            "created_at = excluded.created_at",
            (key, json.dumps(value), time.time()),
        )


def delete(key: str) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM cache WHERE key = ?", (key,))
