"""Saved sessions & workspaces.

Save the current **graph** (seed + every node/edge on screen, including ones
the agent discovered/expanded/searched) together with the **teacher
transcript** (chat + lecture beats), then reopen it later without rebuilding
the graph from Semantic Scholar — a restore costs no rate-limited API calls
and keeps the exact papers you had explored.

This is a small key/blob store, separate from the ephemeral 1-day graph
cache in digest.db — saved sessions are durable user data with their own
lifecycle, so they live in their own ``sessions.db`` (like the bring-your-
own sources). The heavy state is JSON in the ``data`` column; a few metadata
columns are lifted out so the list view renders without parsing every blob.
"""

from __future__ import annotations

import json
import time
from uuid import uuid4

from ..config import config
from . import utils

_SCHEMA = """
CREATE TABLE IF NOT EXISTS saved_sessions (
    id         TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    seed_id    TEXT,                          -- S2 paperId of the seed
    seed_title TEXT,                          -- for the list view
    n_nodes    INTEGER NOT NULL DEFAULT 0,    -- papers on the saved graph
    data       TEXT NOT NULL,                 -- full JSON blob (graph + transcript)
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
"""


def _connect() -> utils.ConnectionContext:
    """Open a connection to the sessions store (data dir + schema ensured)."""
    return utils.connect(config.storage.sessions_db, _SCHEMA)


def list_sessions() -> list[dict]:
    """List every saved session as lightweight metadata, newest-updated first.

    The heavy ``data`` blob is not parsed here — the list view only needs a
    name, the seed it explored, how big the graph is, and when it was touched.

    Returns:
        A list of dicts with keys ``id, name, seed_id, seed_title, n_nodes,
        created_at, updated_at``.

    Raises:
        sqlite3.Error: On database failures.
    """
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, name, seed_id, seed_title, n_nodes, created_at, updated_at "
            "FROM saved_sessions ORDER BY updated_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def get_session(session_id: str) -> dict | None:
    """Fetch one full saved session.

    Args:
        session_id: The saved session's id.

    Returns:
        The metadata row plus the parsed ``data`` payload (the graph +
        transcript blob; ``{}`` when the stored blob fails to parse), or None
        when no such session exists.

    Raises:
        sqlite3.Error: On database failures.
    """
    with _connect() as conn:
        row = conn.execute(
            "SELECT id, name, seed_id, seed_title, n_nodes, data, created_at, updated_at "
            "FROM saved_sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
    if not row:
        return None
    try:
        data = json.loads(row["data"])
    except (ValueError, TypeError):
        data = {}
    return {
        "id": row["id"],
        "name": row["name"],
        "seed_id": row["seed_id"],
        "seed_title": row["seed_title"],
        "n_nodes": row["n_nodes"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "data": data,
    }


def save_session(payload: dict, session_id: str | None = None) -> dict:
    """Create a saved session, or overwrite an existing one in place.

    Args:
        payload: The frontend's session blob — ``{name, seed, layout, nodes,
            edges, chat, beats, hist_trace}``. Stored verbatim in ``data``;
            a few fields are lifted into columns for the list view. A blank
            name becomes ``"Untitled session"``.
        session_id: When given, overwrite that session (re-saving a workspace
            the user already stored — ``created_at`` is preserved); when
            omitted, a new session with a fresh id is created.

    Returns:
        The stored metadata row: ``{id, name, seed_id, seed_title, n_nodes,
        created_at, updated_at}``.

    Raises:
        TypeError: When ``payload`` isn't JSON-serializable.
        sqlite3.Error: On database failures.
    """
    name = (payload.get("name") or "").strip() or "Untitled session"
    seed = payload.get("seed") or {}
    nodes = payload.get("nodes") or []
    now = time.time()
    blob = json.dumps(payload)

    with _connect() as conn:
        existing = None
        if session_id:
            existing = conn.execute(
                "SELECT created_at FROM saved_sessions WHERE id = ?", (session_id,)
            ).fetchone()
        sid = session_id or uuid4().hex
        created_at = existing["created_at"] if existing else now
        conn.execute(
            "INSERT INTO saved_sessions "
            "(id, name, seed_id, seed_title, n_nodes, data, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET "
            "name = excluded.name, seed_id = excluded.seed_id, "
            "seed_title = excluded.seed_title, n_nodes = excluded.n_nodes, "
            "data = excluded.data, updated_at = excluded.updated_at",
            (
                sid,
                name,
                seed.get("id"),
                seed.get("title"),
                len(nodes),
                blob,
                created_at,
                now,
            ),
        )
    return {
        "id": sid,
        "name": name,
        "seed_id": seed.get("id"),
        "seed_title": seed.get("title"),
        "n_nodes": len(nodes),
        "created_at": created_at,
        "updated_at": now,
    }


def delete_session(session_id: str) -> bool:
    """Remove a saved session.

    Args:
        session_id: The saved session's id.

    Returns:
        True when a row was actually deleted, False when no such session
        existed.

    Raises:
        sqlite3.Error: On database failures.
    """
    with _connect() as conn:
        cur = conn.execute("DELETE FROM saved_sessions WHERE id = ?", (session_id,))
        return cur.rowcount > 0
