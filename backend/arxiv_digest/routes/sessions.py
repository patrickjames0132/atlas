"""Saved-session routes (Phase 4): save the current workspace (graph + teacher
transcript) and reopen it later without rebuilding the graph.

GET  /api/sessions       -> list saved sessions (metadata only)
POST /api/sessions       -> save the current workspace (new, or overwrite by id)
GET  /api/sessions/<id>  -> full saved session to restore
DEL  /api/sessions/<id>  -> delete a saved session
"""

from __future__ import annotations

from flask import Blueprint, Response, current_app, jsonify, request

from .. import sessions as sessions_service

bp = Blueprint("sessions", __name__)


@bp.get("/api/sessions")
def api_sessions_list() -> Response:
    """List the user's saved sessions (metadata only — no graph/chat payload)."""
    return jsonify({"sessions": sessions_service.list_sessions()})


@bp.post("/api/sessions")
def api_sessions_save() -> Response:
    """Save the current workspace (graph + teacher transcript). A body with an
    ``id`` overwrites that saved session; without one, a new session is created.
    Returns the stored metadata row."""
    payload = request.get_json(silent=True) or {}
    nodes = payload.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        return jsonify({"error": "nodes must be a non-empty list"}), 400
    session_id = payload.get("id") or None
    try:
        record = sessions_service.save_session(payload, session_id=session_id)
    except Exception as exc:
        current_app.logger.exception("session save failed")
        return jsonify({"error": str(exc)}), 500
    return jsonify(record)


@bp.get("/api/sessions/<session_id>")
def api_sessions_get(session_id: str) -> Response:
    """The full saved session (graph + transcript) to restore into the explorer."""
    record = sessions_service.get_session(session_id)
    if not record:
        return jsonify({"error": "no such session"}), 404
    return jsonify(record)


@bp.delete("/api/sessions/<session_id>")
def api_sessions_delete(session_id: str) -> Response:
    """Delete a saved session."""
    return jsonify({"deleted": sessions_service.delete_session(session_id)})
