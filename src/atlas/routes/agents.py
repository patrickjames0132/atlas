"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
AI-teacher routes: every workflow streams through the agents orchestrator.

POST /api/lecture      -> streamed AI lecture over the visible graph
POST /api/ask          -> the research agent, streamed over the visible graph
POST /api/ask_sources  -> streamed chat answered purely from the local library

Each endpoint validates the request, builds typed inputs, and hands off to
``orchestrator.run(intent, ...)``; the typed event stream comes back as SSE
frames named by each event's ``type`` tag (``model_dump`` minus the tag),
always terminated by ``done`` or ``error``. Conversation history lives HERE
(a locked design decision — agents receive history, they never store it):
two in-memory stores, one per chat, persisted only on success.

(This module is ``routes/agents.py``, the route face of the ``agents``
package — a deliberate name-cousin, different full paths.)

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

import logging
import re
from typing import Iterable, Iterator

from flask import Blueprint, jsonify, request
from flask.typing import ResponseReturnValue
from pydantic import ValidationError

from ..agents import events, orchestrator
from ..agents.models import Intent, LectureMode, PlayedBeat, PlayedLecture
from ..config import config
from ..services.graph import Node, resolve_provider
from .sse import sse, sse_response

bp = Blueprint("agents", __name__)

# Module logger, NOT current_app.logger: the SSE generators below run during
# response iteration, after the request/app context is gone — touching
# current_app there raises RuntimeError and kills the stream before the
# `error` event the frontend waits for can be sent.
log = logging.getLogger(__name__)

# Session-scoped Q&A history, kept in memory (cleared on restart — fine for a
# local single-user app). Maps a client-generated session id ->
# [{role, content}, ...]. The library chat gets its own store so a graph Q&A
# and a library chat never cross-contaminate context.
_QA_SESSIONS: dict[str, list[dict]] = {}
_SOURCES_SESSIONS: dict[str, list[dict]] = {}

# Inline-figure markers (<<FIG n>>) are stripped from the PERSISTED history:
# they stream to the frontend (which replaces them with the image) but must
# not re-enter the model's context on follow-ups — a model that sees
# "<<FIG 1>>" already sitting in its previous answer skips placing the fresh
# marker for this turn's figure, and the image falls back to the end of the
# bubble.
_FIG_MARKER_RE = re.compile(r"[ \t]*<<FIG \d+>>\n?")


def _opt_source_ids(payload: dict) -> list[str] | None:
    """Parse the optional ``source_ids`` scope from a request body.

    Args:
        payload: The parsed JSON body.

    Returns:
        The library source ids to scope the answer to. ``None`` when the key
        is absent or malformed — no scope, so the whole library is searched.
        A **present** ``source_ids`` array yields exactly its string entries,
        including an **empty list** — an explicit "no sources selected" that
        searches nothing rather than everything.
    """
    raw = payload.get("source_ids")
    if not isinstance(raw, list):
        return None
    return [source_id for source_id in raw if isinstance(source_id, str) and source_id]


def _opt_lectures(payload: dict) -> list[PlayedLecture] | None:
    """Parse the optional already-played ``lectures`` from a request body.

    Tolerant like the node parsing: the frontend sends
    ``[{title, beats: [{heading, text}]}]`` from its transcript cache, and this
    picks exactly those fields, skipping any entry missing a title or with no
    usable beats. A malformed ``lectures`` value (or none) yields ``None`` — the
    researcher simply runs without the extra context.

    Args:
        payload: The parsed JSON body.

    Returns:
        The played lectures to hand the researcher, or ``None`` when the key is
        absent, malformed, or empty after cleaning.
    """
    raw = payload.get("lectures")
    if not isinstance(raw, list):
        return None
    lectures: list[PlayedLecture] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        title = entry.get("title")
        raw_beats = entry.get("beats")
        if not isinstance(title, str) or not title or not isinstance(raw_beats, list):
            continue
        beats = [
            PlayedBeat(heading=str(beat.get("heading") or ""), text=str(beat.get("text") or ""))
            for beat in raw_beats
            if isinstance(beat, dict) and (beat.get("text") or beat.get("heading"))
        ]
        if beats:
            lectures.append(PlayedLecture(title=title, beats=beats))
    return lectures or None


def _node(raw: dict) -> Node:
    """Build a typed ``Node`` from a frontend node payload.

    Strict about the core shape, tolerant about baggage: exactly the model's
    fields are picked out of the dict (the force-graph renderer mutates node
    objects with simulation fields — ``x``, ``vy``, ``index``, ... — and
    ``extra="forbid"`` would reject every real payload), and the graph
    annotations default (``rels``/``is_seed``) since discovered nodes may
    not carry them.

    Args:
        raw: One node dict from the request body.

    Returns:
        The validated ``Node``.

    Raises:
        ValidationError: When the core fields are missing/malformed.
    """
    data = {name: raw[name] for name in Node.model_fields if name in raw}
    data.setdefault("rels", [])
    data.setdefault("is_seed", False)
    return Node.model_validate(data)


def _relay(
    workflow: Iterable[events.Event],
    *,
    store: dict[str, list[dict]] | None = None,
    session_id: str = "",
    question: str = "",
) -> Iterator[str]:
    """Serialize a workflow's typed events as SSE frames, persisting on success.

    Frame name = the event's ``type`` tag; payload = ``model_dump`` minus the
    tag — one rule for every event, replacing the old per-kind tuple
    matching. The orchestrator guarantees the stream ends with ``Done`` or
    ``Error``; a turn is persisted only when it ended with ``Done`` (a failed
    answer must not poison the follow-up context), with figure markers
    stripped and the window trimmed to ``config.server.history_turns`` pairs.

    Args:
        workflow: The orchestrator's event stream.
        store: The history store to persist into (None = no persistence —
            lectures aren't chat).
        session_id: The client's session key; blank disables persistence.
        question: The user's question, persisted as the ``user`` turn.

    Yields:
        SSE frame strings.
    """
    answer_parts: list[str] = []
    succeeded = False
    try:
        for event in workflow:
            if isinstance(event, events.Token):
                answer_parts.append(event.text)
            succeeded = isinstance(event, events.Done)
            yield sse(event.type, event.model_dump(exclude={"type"}))
    except Exception:  # the orchestrator catches its own; this guards serialization
        log.exception("agent stream failed")
        yield sse("error", {"message": "The teacher hit an unexpected error."})
        return
    if succeeded and store is not None and session_id:
        answer = _FIG_MARKER_RE.sub("", "".join(answer_parts)).strip()
        convo = store.setdefault(session_id, [])
        convo.append({"role": "user", "content": question})
        convo.append({"role": "assistant", "content": answer})
        keep = config.server.history_turns * 2
        if len(convo) > keep:
            del convo[:-keep]


@bp.post("/api/lecture")
def api_lecture() -> ResponseReturnValue:
    """Stream a lecture over the visible graph as SSE ``beat`` events.

    Body:
        ``{seed: {node fields}, nodes: [visible node objects], mode:
        history|intuition|evolution|bridge, target?: {node fields}}``.

    Returns:
        An SSE stream of ``beat`` frames ``{heading, text, node_ids}``,
        ending with ``done`` or ``error``. A lecture narrates the visible
        nodes as-is — it never expands the graph, so no ``trace`` or
        ``discovery`` frames appear. HTTP 400 for missing/malformed nodes or
        an unknown mode.
    """
    payload = request.get_json(silent=True) or {}
    raw_nodes = payload.get("nodes")
    if not isinstance(raw_nodes, list) or not raw_nodes:
        return jsonify({"error": "nodes must be a non-empty list"}), 400
    raw_mode = payload.get("mode") or "history"
    try:
        mode = LectureMode(raw_mode)
    except ValueError:
        return jsonify({"error": f"unknown lecture mode {raw_mode!r}"}), 400
    raw_target = payload.get("target")
    try:
        seed = _node(payload.get("seed") or {})
        nodes = [_node(raw) for raw in raw_nodes]
        target = _node(raw_target) if raw_target else None
    except ValidationError:
        return jsonify({"error": "seed/nodes are malformed"}), 400

    return sse_response(
        _relay(orchestrator.run(Intent.LECTURE, seed=seed, nodes=nodes, mode=mode, target=target))
    )


@bp.post("/api/ask")
def api_ask() -> ResponseReturnValue:
    """Answer a question grounded in the visible graph, streamed as SSE.

    The researcher reads papers via tool use; conversation history is keyed by
    ``session_id`` so follow-ups keep context, persisted only on success.

    Body:
        ``{question, session_id, seed, nodes, provider?, source_ids?, lectures?}``
        — ``provider`` (``s2``/``openalex``) matches the graph's backend so the
        researcher's expand/search/hydrate use it; ``source_ids`` scopes the
        library search to a subset of uploaded sources; ``lectures`` are the
        lectures already played this session (``[{title, beats: [{heading,
        text}]}]``), folded in as context the answer may build on.

    Returns:
        An SSE stream: ``trace`` frames (tool steps), ``discovery`` frames
        (papers + edges to merge into the live graph), ``figure`` frames,
        ``token`` prose, one ``cited`` frame (``{node_ids}``), then ``done``
        or ``error``. HTTP 400 when the question or nodes are
        missing/malformed.
    """
    payload = request.get_json(silent=True) or {}
    question = (payload.get("question") or "").strip()
    if not question:
        return jsonify({"error": "question is required"}), 400
    raw_nodes = payload.get("nodes")
    if not isinstance(raw_nodes, list) or not raw_nodes:
        return jsonify({"error": "nodes must be a non-empty list"}), 400
    try:
        seed = _node(payload.get("seed") or {})
        nodes = [_node(raw) for raw in raw_nodes]
    except ValidationError:
        return jsonify({"error": "seed/nodes are malformed"}), 400
    session_id = payload.get("session_id") or ""
    source_ids = _opt_source_ids(payload)
    lectures = _opt_lectures(payload)
    provider = resolve_provider(payload.get("provider"))
    history = _QA_SESSIONS.get(session_id, []) if session_id else []

    return sse_response(
        _relay(
            orchestrator.run(
                Intent.RESEARCH,
                question=question,
                seed=seed,
                nodes=nodes,
                history=history,
                source_ids=source_ids,
                lectures=lectures,
                provider=provider,
            ),
            store=_QA_SESSIONS,
            session_id=session_id,
            question=question,
        )
    )


@bp.post("/api/ask_sources")
def api_ask_sources() -> ResponseReturnValue:
    """Answer a question purely from the user's local library, streamed as SSE.

    The offline library chat — no graph required, and no availability gate:
    retrieval self-degrades (lexical-only without the embedder), and an
    empty library gets the librarian's friendly no-hits answer rather than
    a refusal. History is keyed by ``session_id`` in its own store.

    Body:
        ``{question, session_id, source_ids?}`` — ``source_ids`` scopes
        retrieval to a subset of sources.

    Returns:
        An SSE stream: one retrieval ``trace`` frame, then ``token`` prose —
        interleaved with figure ``trace``/``figure`` frames when the
        librarian attaches a figure from an uploaded PDF — then ``done`` or
        ``error``. HTTP 400 when the question is missing.
    """
    payload = request.get_json(silent=True) or {}
    question = (payload.get("question") or "").strip()
    if not question:
        return jsonify({"error": "question is required"}), 400
    session_id = payload.get("session_id") or ""
    source_ids = _opt_source_ids(payload)
    history = _SOURCES_SESSIONS.get(session_id, []) if session_id else []

    return sse_response(
        _relay(
            orchestrator.run(
                Intent.LIBRARIAN, question=question, history=history, source_ids=source_ids
            ),
            store=_SOURCES_SESSIONS,
            session_id=session_id,
            question=question,
        )
    )
