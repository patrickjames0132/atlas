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

from .. import config

_SCHEMA = """
CREATE TABLE IF NOT EXISTS cache (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    created_at REAL NOT NULL
);
"""


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    """Open a connection to the cache table, committing on clean exit.

    Ensures the data directory and schema exist first.

    Yields:
        An open ``sqlite3.Connection`` with ``Row`` as its row factory.

    Raises:
        sqlite3.Error: On database failures (locked file, corrupt db, …).
    """
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
    """Look up a cached JSON value.

    Args:
        key: The cache key.
        max_age: Expiry window in seconds; None means never expire.

    Returns:
        The parsed JSON value, or None when the key is missing, the entry is
        older than ``max_age``, or the stored blob fails to parse.

    Raises:
        sqlite3.Error: On database failures.
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
    """Store a value, stamped with the time now (upserting any existing entry).

    Args:
        key: The cache key.
        value: A JSON-serializable value.

    Returns:
        None.

    Raises:
        TypeError: When ``value`` isn't JSON-serializable.
        sqlite3.Error: On database failures.
    """
    with _connect() as conn:
        conn.execute(
            "INSERT INTO cache (key, value, created_at) VALUES (?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value, "
            "created_at = excluded.created_at",
            (key, json.dumps(value), time.time()),
        )


def delete(key: str) -> None:
    """Remove a cache entry (a no-op when the key doesn't exist).

    Args:
        key: The cache key.

    Returns:
        None.

    Raises:
        sqlite3.Error: On database failures.
    """
    with _connect() as conn:
        conn.execute("DELETE FROM cache WHERE key = ?", (key,))


def scan(prefix: str) -> list[tuple[str, Any, float]]:
    """Fetch every entry whose key starts with a prefix — expired ones included.

    Callers decide what staleness means; e.g. local search still wants papers
    from old snapshots. SQL LIKE wildcards in the prefix are escaped so they
    match literally.

    Args:
        prefix: The literal key prefix (e.g. ``"graph:"``).

    Returns:
        A list of ``(key, parsed value, created_at)`` tuples. Rows whose blob
        fails to parse are skipped.

    Raises:
        sqlite3.Error: On database failures.
    """
    like = prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    with _connect() as conn:
        rows = conn.execute(
            "SELECT key, value, created_at FROM cache WHERE key LIKE ? ESCAPE '\\'",
            (like,),
        ).fetchall()
    out: list[tuple[str, Any, float]] = []
    for row in rows:
        try:
            out.append((row["key"], json.loads(row["value"]), row["created_at"]))
        except (ValueError, TypeError):
            continue
    return out
