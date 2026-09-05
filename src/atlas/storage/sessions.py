"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
Saved explorations.

An **exploration** is a sitting at the app: the conversation you held, the
lectures you played, and a note of which graph was open while you held it.
Every exploration saves itself as you work (there is no Save button); the
frontend re-POSTs the same row on settled events, debounced.

**The conversation is the durable thing here, the graph is a reference.**
The blob carries chat, lectures and a ``graph_ref`` (the seed reference,
provider and layout needed to put the graph back) rather than the graph's
nodes and edges. Reopening rebuilds it — instantly when the 1-day snapshot
cache in digest.db is still warm, from the provider when it is not. That is
a deliberate trade Patrick made 2026-08-29: rows stay small and the chat
history is the spine, at the cost of rate-limited calls on a cold reopen and
a rebuilt graph that may differ from the one you left (citation data moves).

**One exception rides with the conversation:** the papers the *agent* pulled
in mid-chat (``discovered_nodes``/``discovered_edges``). No cache holds them
and no rebuild reproduces them — they are a product of the conversation, not
of the seed — so they are stored, and merged back over the rebuilt graph.

Explorations are durable user data with their own lifecycle, so they live in
their own ``sessions.db`` (like the bring-your-own sources), separate from
the ephemeral cache. The heavy state is JSON in the ``data`` column; a few
metadata columns are lifted out so the list view renders without parsing
every blob.

**Legacy saves still restore.** Rows written before 2026-08-29 carry the
whole graph inline (``nodes``/``edges``) and no ``graph_ref``; ``get_session``
hands the blob back as-is and the frontend uses whichever it finds, so an
old save keeps its exact papers instead of being rebuilt.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
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
    return [dict(row) for row in rows]


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


def _seed_of(payload: dict) -> dict:
    """Find the seed paper an exploration was reading, in either blob shape.

    The lifted ``seed_id``/``seed_title`` columns exist so the list view can
    render without parsing every blob, and they must keep working across the
    move to the reference shape — which put the seed one level down, inside
    ``graph_ref``. A **legacy** blob has it at the top level.

    Args:
        payload: The exploration blob, in either shape.

    Returns:
        The seed dict, or ``{}`` for a graphless exploration (which correctly
        stores NULL in both columns).
    """
    graph_ref = payload.get("graph_ref")
    if isinstance(graph_ref, dict) and isinstance(graph_ref.get("seed"), dict):
        return graph_ref["seed"]
    seed = payload.get("seed")
    return seed if isinstance(seed, dict) else {}


def _count_nodes(payload: dict) -> int:
    """Count the papers an exploration is worth showing in the list view.

    Two blob shapes have to answer this. A **legacy** save carries the whole
    graph inline, so its ``nodes`` list is the count. A **current** save
    carries only a ``graph_ref`` plus whatever the agent discovered, and the
    rebuilt graph's size is not knowable here — nothing in this process has
    fetched it — so the honest answer is the count the reference itself
    recorded when it was written (``graph_ref.n_nodes``) plus the discovered
    papers layered on top.

    The number is a **list-view hint, not a guarantee**: a rebuilt graph can
    come back a different size, because the provider's citation data moves
    between the save and the reopen. Nothing depends on it being exact.

    Args:
        payload: The exploration blob, in either shape.

    Returns:
        The paper count for the ``n_nodes`` column; 0 for a graphless
        exploration (a conversation with no graph is a valid row).
    """
    legacy_nodes = payload.get("nodes")
    if isinstance(legacy_nodes, list) and legacy_nodes:
        return len(legacy_nodes)
    graph_ref = payload.get("graph_ref") or {}
    base = graph_ref.get("n_nodes") if isinstance(graph_ref, dict) else None
    discovered = payload.get("discovered_nodes")
    count = base if isinstance(base, int) and base > 0 else 0
    if isinstance(discovered, list):
        count += len(discovered)
    return count


def save_session(payload: dict, session_id: str | None = None) -> dict:
    """Create a saved session, or overwrite an existing one in place.

    Args:
        payload: The frontend's exploration blob — ``{name, seed, graph_ref,
            layout, discovered_nodes, discovered_edges, chat, lectures,
            activeMode}``. Legacy blobs carry the whole graph inline
            (``nodes``/``edges``) and a flat ``beats``/``hist_trace``
            instead; both shapes are stored verbatim in ``data``, with a few
            fields lifted into columns for the list view. A blank name
            becomes ``"Untitled exploration"``.
        session_id: When given, overwrite that exploration (the autosave
            re-POSTing a row it already created — ``created_at`` is
            preserved); when omitted, a new exploration with a fresh id is
            created.

    Returns:
        The stored metadata row: ``{id, name, seed_id, seed_title, n_nodes,
        created_at, updated_at}``.

    Raises:
        TypeError: When ``payload`` isn't JSON-serializable.
        sqlite3.Error: On database failures.
    """
    name = (payload.get("name") or "").strip() or "Untitled exploration"
    seed = _seed_of(payload)
    now = time.time()
    node_count = _count_nodes(payload)
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
                node_count,
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
        "n_nodes": node_count,
        "created_at": created_at,
        "updated_at": now,
    }


def rename_session(session_id: str, name: str) -> bool:
    """Give a saved session a new name, leaving its snapshot untouched.

    Renaming used to mean re-saving: ``save_session`` overwrites the whole
    blob, so the only way to change a name was to hold the entire workspace
    and write it back — possible for the session you have open, impossible for
    the other twelve in a list. A name is metadata, and metadata should be
    editable without rehydrating what it describes.

    ``updated_at`` deliberately does **not** move: the list is ordered by it,
    and renaming a session is not working on it. A rename that reshuffled the
    list would lose you the thing you just labelled.

    Args:
        session_id: The saved session's id.
        name: The new name; blank falls back to ``"Untitled exploration"``, the
            same floor ``save_session`` applies.

    Returns:
        True when a row was renamed, False when no such session existed.

    Raises:
        sqlite3.Error: On database failures.
    """
    clean = (name or "").strip() or "Untitled exploration"
    with _connect() as conn:
        # The name also lives inside the stored blob (the frontend round-trips
        # it), so both copies move together — otherwise a restore would put
        # the old name back the next time the session was saved.
        row = conn.execute(
            "SELECT data FROM saved_sessions WHERE id = ?", (session_id,)
        ).fetchone()
        if row is None:
            return False
        try:
            payload = json.loads(row["data"])
        except (TypeError, ValueError, json.JSONDecodeError):
            payload = None
        if isinstance(payload, dict):
            payload["name"] = clean
            conn.execute(
                "UPDATE saved_sessions SET name = ?, data = ? WHERE id = ?",
                (clean, json.dumps(payload), session_id),
            )
        else:
            conn.execute(
                "UPDATE saved_sessions SET name = ? WHERE id = ?", (clean, session_id)
            )
        return True


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
