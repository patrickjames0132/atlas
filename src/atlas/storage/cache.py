"""A thin TTL cache for dynamically-fetched artifacts (graph snapshots, ar5iv
full text and figures, Hugging Face code links).

arXiv Atlas deliberately does NOT store a paper corpus — millions of papers
are many TB and the ecosystem (Semantic Scholar / arXiv) already hosts them.
This is just a small key -> JSON-blob table so the app can respect Semantic
Scholar's tight rate limit and avoid re-fetching the same neighborhood on
every view.

Freshness is entirely the caller's decision: every value here is stamped
with when it was written, but nothing in this module decides what counts as
stale. Each caller passes its own ``max_age`` to ``get()`` — a graph
snapshot and an ar5iv figure have very different TTLs, and both share this
one table.
"""

from __future__ import annotations

import json
import time
from typing import Any

from ..config import config
from . import utils

_SCHEMA = """
CREATE TABLE IF NOT EXISTS cache (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    created_at REAL NOT NULL
);
"""


def _connect() -> utils.ConnectionContext:
    """Open a connection to the cache table (data dir + schema ensured)."""
    return utils.connect(config.storage.digest_db, _SCHEMA)


def get(key: str, max_age: float | None = None) -> Any | None:
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
