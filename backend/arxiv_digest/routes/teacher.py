"""AI-teacher routes: a streamed lecture over the visible graph, grounded/agentic
Q&A, and the offline library chat. All three stream Server-Sent Events.

POST /api/lecture      -> streamed AI lecture over the visible graph
POST /api/ask          -> streamed grounded Q&A over the visible graph
POST /api/ask_sources  -> streamed chat answered purely from the local library
"""

from __future__ import annotations

import json
from typing import Iterator

from flask import Blueprint, Response, current_app, jsonify, request
from flask.typing import ResponseReturnValue

from .. import config
from .. import teacher as teacher_service
from ..library import sources

bp = Blueprint("teacher", __name__)

# Session-scoped Q&A history, kept in memory (cleared on restart — fine for v1).
# Maps a client-generated session id -> [{role, content}, ...].
_QA_SESSIONS: dict[str, list[dict]] = {}
# Separate history store for the offline library chat (Phase 3d) — same shape,
# kept apart so a graph Q&A and a library chat don't cross-contaminate context.
_SOURCES_SESSIONS: dict[str, list[dict]] = {}


def _opt_source_ids(payload: dict) -> "list[str] | None":
    """Parse the optional ``source_ids`` scope from a request body.

    Args:
        payload: The parsed JSON body.

    Returns:
        The library source ids to scope the answer to. ``None`` when the key is
        absent or malformed — no scope, so the whole library is searched. A
        **present** ``source_ids`` array yields exactly its string entries,
        including an **empty list** — an explicit "no sources selected" that
        searches nothing rather than everything.
    """
    raw = payload.get("source_ids")
    if not isinstance(raw, list):
        return None
    return [s for s in raw if isinstance(s, str) and s]


def _sse(event: str, data: object) -> str:
    """Format one Server-Sent Event frame.

    Args:
        event: The event name (``beat``, ``token``, ``trace``, …).
        data: A JSON-serializable payload.

    Returns:
        The wire-format frame: ``event:`` and ``data:`` lines terminated by a
        blank line.

    Raises:
        TypeError: When ``data`` isn't JSON-serializable.
    """
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _sse_response(generator) -> Response:
    """Wrap a generator of SSE frames as a streaming response.

    ``X-Accel-Buffering: no`` keeps nginx (if ever put in front) from
    buffering the stream; ``Cache-Control: no-cache`` stops intermediaries
    caching partial output.

    Args:
        generator: An iterator yielding SSE frame strings (from ``_sse``).

    Returns:
        A ``text/event-stream`` Flask Response streaming the frames.
    """
    return Response(
        generator,
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@bp.post("/api/lecture")
def api_lecture() -> ResponseReturnValue:
    """Stream a lecture over the visible graph as SSE ``beat`` events.

    In ``history`` mode we first walk backward through references (Phase 3e),
    emitting ``trace`` + ``nodes`` events, so the story can start at the
    field's roots; the discovered ancestors join the node set the lecture
    narrates over.

    Body:
        ``{seed: {title,...}, nodes: [visible node objects], mode:
        history|intuition|bridge, target?: {title,...}}``.

    Returns:
        An SSE stream — each ``beat`` event carries ``{heading, text,
        node_ids}`` so the frontend can reveal it and light up nodes, ending
        with ``done`` (or an ``error`` event; failures inside the stream are
        also logged). HTTP 400 when ``nodes`` is missing/empty.
    """
    payload = request.get_json(silent=True) or {}
    nodes = payload.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        return jsonify({"error": "nodes must be a non-empty list"}), 400
    seed = payload.get("seed") or {}
    mode = payload.get("mode") or "history"
    target = payload.get("target")

    def gen() -> Iterator[str]:
        """Yield the lecture's SSE frames (backfill first in history mode)."""
        try:
            enriched = nodes
            if mode == "history" and seed.get("id"):
                for kind, data in teacher_service.history_backfill(seed, nodes):
                    if kind == "nodes":
                        assert isinstance(data, dict)  # "nodes" events carry {nodes, ...}
                        enriched = enriched + data["nodes"]
                        yield _sse("nodes", data)
                    elif kind == "trace":
                        yield _sse("trace", data)
            for beat in teacher_service.lecture_beats(seed, enriched, mode=mode, target=target):
                yield _sse("beat", beat)
            yield _sse("done", {})
        except Exception as exc:  # surface to the panel AND log the traceback
            current_app.logger.exception("lecture failed")
            yield _sse("error", {"error": str(exc)})

    return _sse_response(gen())


@bp.post("/api/ask")
def api_ask() -> ResponseReturnValue:
    """Answer a question grounded in the visible graph, streamed as SSE.

    Runs the agentic Q&A (reads papers via tool use) when the API backend is
    available; otherwise the non-agentic grounded answer (e.g. under the
    claude CLI backend). Conversation history is keyed by ``session_id`` so
    follow-ups keep context; a turn is persisted only on success, capped to
    the recent window.

    Body:
        ``{question, session_id, seed, nodes, source_ids?}`` — ``source_ids``
        scopes the agent's library search to a subset of uploaded sources
        (agentic backend only).

    Returns:
        An SSE stream: with the agentic backend, ``trace`` events (tool
        steps), ``nodes`` events (``{nodes, edges}`` discoveries) as expansion
        finds papers not yet on the graph, and ``figure`` events (a paper's
        figure the agent attached to its answer); always ``token`` events
        (prose), a final ``cited`` event (``{node_ids}``), then ``done`` (or
        ``error``). HTTP 400 when the question or nodes are missing.
    """
    payload = request.get_json(silent=True) or {}
    question = (payload.get("question") or "").strip()
    if not question:
        return jsonify({"error": "question is required"}), 400
    nodes = payload.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        return jsonify({"error": "nodes must be a non-empty list"}), 400
    seed = payload.get("seed") or {}
    session_id = payload.get("session_id") or ""
    source_ids = _opt_source_ids(payload)  # scope the teacher to a subset of sources
    history = _QA_SESSIONS.get(session_id, []) if session_id else []

    # Agentic Q&A (reads papers via tool use) when the API backend is available;
    # otherwise the non-agentic grounded answer (e.g. the claude CLI backend).
    # The source scope only bears on the agentic path's library search; the
    # non-agentic grounded answer is graph-only and ignores it.
    source = (
        teacher_service.answer_agentic(question, seed, nodes, history, source_ids)
        if teacher_service.agentic_available()
        else teacher_service.answer_stream(question, seed, nodes, history)
    )

    def gen() -> Iterator[str]:
        """Yield the answer's SSE frames, persisting the turn on success."""
        answer_parts: list[str] = []
        try:
            for kind, data in source:
                if kind == "token":
                    assert isinstance(data, str)  # "token" events carry prose
                    answer_parts.append(data)
                    yield _sse("token", {"text": data})
                elif kind == "trace":
                    yield _sse("trace", data)
                elif kind == "nodes":
                    yield _sse("nodes", data)
                elif kind == "figure":
                    yield _sse("figure", data)
                elif kind == "discard":
                    # Streamed preamble turned out to precede a tool call — drop it.
                    answer_parts.clear()
                    yield _sse("discard", {})
                elif kind == "cited":
                    yield _sse("cited", {"node_ids": data})
            yield _sse("done", {})
        except Exception as exc:
            current_app.logger.exception("ask failed")
            yield _sse("error", {"error": str(exc)})
            return
        # Persist the turn only on success, capped to the recent window.
        if session_id:
            convo = _QA_SESSIONS.setdefault(session_id, [])
            convo.append({"role": "user", "content": question})
            convo.append({"role": "assistant", "content": "".join(answer_parts).strip()})
            keep = config.TEACHER_HISTORY_TURNS * 2
            if len(convo) > keep:
                del convo[:-keep]

    return _sse_response(gen())


@bp.post("/api/ask_sources")
def api_ask_sources() -> ResponseReturnValue:
    """Answer a question purely from the user's local library, streamed as SSE.

    The offline library chat — no graph required. History is keyed by
    ``session_id`` (a separate store from the graph Q&A) so follow-ups keep
    context without cross-contaminating the two chats.

    Body:
        ``{question, session_id, source_ids?}`` — ``source_ids`` scopes
        retrieval to a subset of sources.

    Returns:
        An SSE stream: one ``trace`` event (the retrieved passages), then
        ``token`` prose, then ``done`` (or ``error``). HTTP 400 when the
        question is missing or the local library is unavailable
        (embeddings/sqlite-vec didn't load).
    """
    payload = request.get_json(silent=True) or {}
    question = (payload.get("question") or "").strip()
    if not question:
        return jsonify({"error": "question is required"}), 400
    if not sources.available():
        return jsonify({"error": "Your local library is unavailable (embeddings/sqlite-vec didn't load)."}), 400

    session_id = payload.get("session_id") or ""
    source_ids = _opt_source_ids(payload)  # scope to a subset of sources (optional)
    history = _SOURCES_SESSIONS.get(session_id, []) if session_id else []

    def gen() -> Iterator[str]:
        """Yield the library answer's SSE frames, persisting the turn on success."""
        answer_parts: list[str] = []
        try:
            for kind, data in teacher_service.answer_from_sources(question, history, source_ids):
                if kind == "token":
                    assert isinstance(data, str)  # "token" events carry prose
                    answer_parts.append(data)
                    yield _sse("token", {"text": data})
                elif kind == "trace":
                    yield _sse("trace", data)
            yield _sse("done", {})
        except Exception as exc:
            current_app.logger.exception("ask_sources failed")
            yield _sse("error", {"error": str(exc)})
            return
        if session_id:
            convo = _SOURCES_SESSIONS.setdefault(session_id, [])
            convo.append({"role": "user", "content": question})
            convo.append({"role": "assistant", "content": "".join(answer_parts).strip()})
            keep = config.TEACHER_HISTORY_TURNS * 2
            if len(convo) > keep:
                del convo[:-keep]

    return _sse_response(gen())
