"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
Saved-session routes: save the current workspace (graph + teacher
transcript) and reopen it later without rebuilding the graph.

GET  /api/sessions       -> list saved sessions (metadata only)
POST /api/sessions       -> save the current workspace (new, or overwrite by id)
GET  /api/sessions/<id>  -> full saved session to restore
DEL  /api/sessions/<id>  -> delete a saved session

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

from flask import Blueprint, Response, current_app, jsonify, request
from flask.typing import ResponseReturnValue

from ..storage import sessions as sessions_service

bp = Blueprint("sessions", __name__)


@bp.get("/api/sessions")
def api_sessions_list() -> Response:
    """List the user's saved sessions.

    Returns:
        JSON ``{sessions: [...]}`` — metadata rows only (no graph/chat
        payload), newest-updated first.
    """
    return jsonify({"sessions": sessions_service.list_sessions()})


@bp.post("/api/sessions")
def api_sessions_save() -> ResponseReturnValue:
    """Save the current workspace (graph + teacher transcript).

    Body:
        The frontend's session blob — ``{name, seed, layout, nodes, edges,
        chat, beats, hist_trace}``, plus an optional ``id``. A body with an
        ``id`` overwrites that saved session; without one, a new session is
        created. Beyond ``nodes``, the blob is deliberately unvalidated —
        it's frontend-owned, and the store treats it as opaque.

    Returns:
        The stored metadata row as JSON on success; ``{error}`` with HTTP 400
        when ``nodes`` is missing/empty, or 500 when the store fails.
    """
    payload = request.get_json(silent=True) or {}
    nodes = payload.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        return jsonify({"error": "nodes must be a non-empty list"}), 400
    session_id = payload.get("id") or None
    try:
        record = sessions_service.save_session(payload, session_id=session_id)
    except Exception:
        current_app.logger.exception("session save failed")
        return jsonify({"error": "Could not save the session."}), 500
    return jsonify(record)


@bp.get("/api/sessions/<session_id>")
def api_sessions_get(session_id: str) -> ResponseReturnValue:
    """Fetch the full saved session (graph + transcript) to restore.

    Args:
        session_id: The saved session's id.

    Returns:
        The full session record as JSON; ``{error}`` with HTTP 404 when no
        such session exists.
    """
    record = sessions_service.get_session(session_id)
    if not record:
        return jsonify({"error": "no such session"}), 404
    return jsonify(record)


@bp.delete("/api/sessions/<session_id>")
def api_sessions_delete(session_id: str) -> Response:
    """Delete a saved session.

    Args:
        session_id: The saved session's id.

    Returns:
        JSON ``{deleted: bool}`` — False when no such session existed
        (delete is idempotent, not a 404).
    """
    return jsonify({"deleted": sessions_service.delete_session(session_id)})
