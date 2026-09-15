"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
AI-teacher routes: one endpoint per agent, each streaming typed events.

POST /api/route        -> which assistant a typed message wants (JSON, not SSE)
POST /api/lecture      -> streamed AI lecture over the visible graph
POST /api/ask          -> the research agent, streamed over the visible graph
POST /api/ask_sources  -> streamed chat with no graph open (library + search)

Each endpoint validates the request, builds typed inputs, and hands off to
the agent that serves it; the typed event stream comes back as SSE
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

from ..agents import events, streams
from ..agents.orchestrators import lecturer, researcher, router
from ..config import config
from ..services import search as search_service
from ..services.graph import Node, Provider, resolve_provider
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


def _opt_filters(payload: dict, provider: Provider) -> dict:
    """Parse the optional paper-discovery filters from a request body.

    The chat bar carries one set of filters for both of its modes, so the same
    year window and field restriction a direct search would apply also reach
    the researcher — which forwards them to every scout it sends out. They
    scope *discovery* only; citation hops ignore them (see ``ResearcherDeps``).

    Args:
        payload: The parsed JSON body.
        provider: The resolved graph provider, for validating field values
            against the right vocabulary.

    Returns:
        ``{year_from, year_to, fields}`` ready to splat into
        ``researcher.answer``. Absent, blank, or non-numeric years become
        None; unknown field values are dropped.
    """

    def year(name: str) -> int | None:
        """Read one optional year from the payload.

        Args:
            name: The key to read (``year_from`` / ``year_to``).

        Returns:
            The year as an int, or None when absent or unparseable.
        """
        raw = payload.get(name)
        if isinstance(raw, int):
            return raw
        try:
            return int(str(raw).strip())
        except (TypeError, ValueError):
            return None

    raw_fields = payload.get("fields")
    fields = [str(value) for value in raw_fields] if isinstance(raw_fields, list) else []
    return {
        "year_from": year("year_from"),
        "year_to": year("year_to"),
        "fields": search_service.valid_fields(provider, fields),
    }


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
    matching. ``streams.terminated`` guarantees the stream ends with ``Done`` or
    ``Error``; a turn is persisted only when it ended with ``Done`` (a failed
    answer must not poison the follow-up context), with figure markers
    stripped and the window trimmed to ``config.server.history_turns`` pairs.

    Args:
        workflow: The agent's event stream, already terminated.
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
    except Exception:  # `terminated` catches the workflow's; this guards serialization
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


@bp.post("/api/route")
def api_route() -> ResponseReturnValue:
    """Say which assistant a typed message wants, before anything is streamed.

    The one endpoint here that is **not** SSE, because it produces a decision
    rather than an answer: the client uses it to pick between
    ``/api/lecture`` and ``/api/ask`` and then streams from the one it picked.
    Two round trips rather than one, deliberately — folding the choice into a
    single streaming endpoint would mean a second implementation of both
    workflows' event relays, to save a few milliseconds on localhost.

    Body:
        ``{message: str}`` — the message as typed, mentions and all.

    Returns:
        ``{target: 'lecture'|'answer', framing: 'summary'|'history'}``, always
        HTTP 200. A blank message, a missing key, a dead model and an
        unparseable classification all come back as the researcher (see
        ``router.route``): this endpoint sits in front of every message the
        reader sends, so failing it would break asking questions in order to
        protect a routing nicety.
    """
    payload = request.get_json(silent=True) or {}
    message = payload.get("message")
    decision = router.route(message if isinstance(message, str) else "")
    return jsonify(decision.model_dump())


@bp.post("/api/lecture")
def api_lecture() -> ResponseReturnValue:
    """Stream a lecture over the reader's scoped graph as SSE ``beat`` events.

    Body:
        ``{seed: {node fields}, nodes: [scoped node objects], framing?:
        summary|history, target?: {node fields}}``. ``nodes`` is the subject
        of the lecture — whatever the reader has on screen after their filters
        and selection — so the route passes it through untouched. ``framing``
        is the reader's one remaining choice (how to tell it, not which papers
        to tell it about); an unknown value falls back to ``summary`` rather
        than 400-ing, since a framing is a preference and refusing the whole
        lecture over one is a worse answer. A ``target`` asks for the bridge
        lecture instead. Since v7.17.0 there is no ``mode``: an old client
        still sending one is ignored rather than refused, since the field no
        longer selects anything.

    Returns:
        An SSE stream of ``beat`` frames ``{heading, text, node_ids}``,
        ending with ``done`` or ``error``. A lecture narrates the scoped
        nodes as-is — it never expands the graph, so no ``trace`` or
        ``discovery`` frames appear. HTTP 400 for missing/malformed nodes.
    """
    payload = request.get_json(silent=True) or {}
    raw_nodes = payload.get("nodes")
    if not isinstance(raw_nodes, list) or not raw_nodes:
        return jsonify({"error": "nodes must be a non-empty list"}), 400
    raw_target = payload.get("target")
    framing: lecturer.Framing = "history" if payload.get("framing") == "history" else "summary"
    try:
        seed = _node(payload.get("seed") or {})
        nodes = [_node(raw) for raw in raw_nodes]
        target = _node(raw_target) if raw_target else None
    except ValidationError:
        return jsonify({"error": "seed/nodes are malformed"}), 400

    return sse_response(
        _relay(
            streams.terminated(
                lecturer.lecture(seed=seed, nodes=nodes, target=target, framing=framing)
            )
        )
    )


def _resumed_history(payload: dict, stored: list[dict]) -> list[dict]:
    """The conversation history to answer against, preferring the server's own.

    ``_QA_SESSIONS`` lives in memory and is keyed by a client-generated id, so
    it is empty in exactly the case a **retry** cares about: the reader
    reloaded the page (or reopened a saved exploration) after an answer failed,
    and the id they now hold is one this process has never seen. The transcript
    is still on their screen, so the client can supply what the server lost.

    The server's own copy wins whenever it has one — it is authoritative, and
    it already excludes failed turns, since history is only written on success.
    The client's copy is a fallback, accepted only in the shape the model
    expects and capped by the same ``history_turns`` budget so a crafted body
    cannot stuff the context window.

    Args:
        payload: The request body, which may carry ``history``.
        stored: What this process holds for the session (possibly empty).

    Returns:
        The history to pass to the agent; ``[]`` when neither side has one.
    """
    if stored:
        return stored
    raw = payload.get("history")
    if not isinstance(raw, list):
        return []
    clean = [
        {"role": turn["role"], "content": turn["content"]}
        for turn in raw
        if isinstance(turn, dict)
        and turn.get("role") in {"user", "assistant"}
        and isinstance(turn.get("content"), str)
        and turn["content"].strip()
    ]
    keep = config.server.history_turns * 2
    return clean[-keep:] if keep else []


@bp.post("/api/ask")
def api_ask() -> ResponseReturnValue:
    """Answer a question grounded in the visible graph, streamed as SSE.

    The researcher reads papers via tool use; conversation history is keyed by
    ``session_id`` so follow-ups keep context, persisted only on success.

    Body:
        ``{question, session_id, seed, nodes, provider?, source_ids?,
        history?}`` — ``provider`` (``s2``/``openalex``) matches the graph's
        backend so the researcher's expand/search/hydrate use it;
        ``source_ids`` scopes the library search to a subset of uploaded
        sources. ``history`` is the client's own copy of the conversation,
        used **only** when this process holds none for the session — see
        ``_resumed_history``.

        A ``lectures`` field used to ride along here, carrying every lecture
        the reader had played so the researcher could build on it. It went in
        v7.21.0 with the frontend's lecture slot: a lecture is a chat turn
        now, so it reaches the agent through ``history`` like any other turn.

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
    provider = resolve_provider(payload.get("provider"))
    history = _resumed_history(payload, _QA_SESSIONS.get(session_id, []) if session_id else [])

    return sse_response(
        _relay(
            streams.terminated(
                researcher.answer(
                    question=question,
                    seed=seed,
                    nodes=nodes,
                    history=history,
                    source_ids=source_ids,
                    provider=provider,
                    **_opt_filters(payload, provider),
                )
            ),
            store=_QA_SESSIONS,
            session_id=session_id,
            question=question,
        )
    )


@bp.post("/api/ask_sources")
def api_ask_sources() -> ResponseReturnValue:
    """Answer a question purely from the user's local library, streamed as SSE.

    The graph-free chat — the same researcher as ``/api/ask``, run with no
    seed and no numbered papers, so it reaches for the library (and, if it
    needs to, Semantic Scholar) through its tools rather than having
    passages pushed at it. History is keyed by ``session_id`` in its own
    store, kept separate from the graph chat's.

    Body:
        ``{question, session_id, provider?, source_ids?}`` — ``provider``
        (``s2``/``openalex``) is the backend the agent's paper search runs
        against, sent by the header's Data source dropdown exactly as
        ``/api/ask`` does; ``source_ids`` scopes retrieval to a subset of
        sources.

    Returns:
        An SSE stream: a ``source_refs`` frame when a library is in play,
        ``trace`` frames as the agent searches, ``token`` prose interleaved
        with any ``figure`` frames, then ``cited`` + ``provenance``, then
        ``done`` or ``error``. HTTP 400 when the question is missing.
    """
    payload = request.get_json(silent=True) or {}
    question = (payload.get("question") or "").strip()
    if not question:
        return jsonify({"error": "question is required"}), 400
    session_id = payload.get("session_id") or ""
    source_ids = _opt_source_ids(payload)
    # The graph-free chat has no graph to inherit a backend from, so the
    # provider rides on the request like everything else here. Omitting it
    # (as this route did until v6.14.0) doesn't leave the agent backend-less
    # — it silently pins it to the default, which is how a chat under the
    # OpenAlex dropdown ended up searching Semantic Scholar and handing back
    # citations no OpenAlex seed build could resolve.
    provider = resolve_provider(payload.get("provider"))
    history = _resumed_history(
        payload, _SOURCES_SESSIONS.get(session_id, []) if session_id else []
    )

    return sse_response(
        _relay(
            streams.terminated(
                researcher.answer(
                    question=question,
                    history=history,
                    source_ids=source_ids,
                    provider=provider,
                    **_opt_filters(payload, provider),
                )
            ),
            store=_SOURCES_SESSIONS,
            session_id=session_id,
            question=question,
        )
    )
