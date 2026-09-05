"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
Exploration routes: save the conversation (plus a reference to whichever
graph was open) as the reader works, and reopen it later.

GET   /api/sessions            -> list saved explorations (metadata only)
POST  /api/sessions            -> save an exploration (new, or overwrite by id)
GET   /api/sessions/<id>       -> full exploration to restore
PATCH /api/sessions/<id>       -> rename an exploration
DEL   /api/sessions/<id>       -> delete an exploration
POST  /api/sessions/title      -> name an exploration after its conversation

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

from flask import Blueprint, Response, current_app, jsonify, request
from flask.typing import ResponseReturnValue

from ..agents.orchestrators import summarizer
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
    """Save an exploration (the conversation, plus a reference to its graph).

    This is the autosave's endpoint: the frontend re-POSTs the same ``id`` on
    every settled event, so the common case is an overwrite, not a create.

    Body:
        The frontend's exploration blob — ``{name, seed, graph_ref, layout,
        discovered_nodes, discovered_edges, chat, lectures, activeMode}``,
        plus an optional ``id``. A body with an ``id`` overwrites that
        exploration; without one, a new one is created. The blob is
        deliberately unvalidated — it's frontend-owned, and the store treats
        it as opaque.

        **A graphless body is valid and must stay that way.** Since the
        landing chat became the front door a reader can hold a long
        conversation before any graph exists, and refusing to store it is
        exactly the data loss the autosave was built to end. This route used
        to 400 on an empty ``nodes`` list, which made that conversation
        unsavable.

    Returns:
        The stored metadata row as JSON on success; ``{error}`` with HTTP 400
        when the body isn't a JSON object, or 500 when the store fails.
    """
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "body must be a JSON object"}), 400
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


@bp.patch("/api/sessions/<session_id>")
def api_sessions_rename(session_id: str) -> ResponseReturnValue:
    """Rename a saved session, leaving its snapshot untouched.

    A name is metadata, so editing it shouldn't require holding the whole
    workspace — which re-saving through ``POST`` does, and which is only
    possible for the session currently open.

    Args:
        session_id: The saved session's id.

    Returns:
        JSON ``{renamed: bool}`` — False when no such session existed (like
        delete, absence is not a 404). HTTP 400 when ``name`` is missing or
        not a string; a *blank* name is fine and falls back to
        "Untitled exploration".
    """
    payload = request.get_json(silent=True) or {}
    name = payload.get("name")
    if not isinstance(name, str):
        return jsonify({"error": "name is required"}), 400
    return jsonify({"renamed": sessions_service.rename_session(session_id, name)})


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


@bp.post("/api/sessions/title")
def api_sessions_title() -> ResponseReturnValue:
    """Name an exploration after the conversation held in it.

    Deliberately its **own** route rather than a step inside ``POST
    /api/sessions``: the save is an autosave on a 2-second debounce, and
    folding a model call into it would put provider latency on the path that
    has to be cheap enough to run all afternoon. The frontend calls this once,
    when an exploration first has content worth naming, and sends the result
    with subsequent saves like any other name.

    Body:
        ``{turns: [str, ...]}`` — the conversation's opening turns, oldest
        first, already flattened to plain text.

    Returns:
        JSON ``{title: str}`` on success. ``{title: null}`` with HTTP 200
        when the conversation can't be named — no key, the provider is down,
        or there is nothing to name yet. **That is not an error**: the caller
        has a free fallback (the reader's own first message), and failing a
        save because a nicety was unavailable would be the wrong trade.
        HTTP 400 only when ``turns`` isn't a list of strings.
    """
    payload = request.get_json(silent=True) or {}
    turns = payload.get("turns")
    if not isinstance(turns, list) or any(not isinstance(turn, str) for turn in turns):
        return jsonify({"error": "turns must be a list of strings"}), 400
    return jsonify({"title": summarizer.title_for_conversation(turns)})
