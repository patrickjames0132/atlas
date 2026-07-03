"""Flask API for arXiv Atlas.

Endpoints
---------
GET  /api/health                       -> simple liveness check
GET  /api/graph?seed=&refresh=         -> neighborhood graph for a seed paper
GET  /api/paper/<arxiv_id>             -> full details for one paper (panel hydrate)
GET  /api/paper/<arxiv_id>/figures     -> the paper's figures + captions (ar5iv)
GET  /api/figure_proxy?src=            -> same-origin proxy for an ar5iv image
GET  /api/arxiv_search?q=&limit=       -> live seed search across arXiv
GET  /api/local_search?q=&limit=       -> instant seed search over the local cache
POST /api/lecture                      -> streamed AI lecture over the visible graph
POST /api/ask                          -> streamed grounded Q&A over the visible graph
GET  /api/sources                      -> list the user's local semantic library
POST /api/sources                      -> ingest a PDF upload or a {url} into the library
DEL  /api/sources/<id>                 -> remove a source from the library

In production it also serves the built React app from frontend/dist.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.parse
from pathlib import Path

from flask import Flask, jsonify, request, Response, send_from_directory
from flask_cors import CORS

from . import (
    arxiv_client,
    config,
    figures,
    graph,
    search,
    semantic_scholar,
    sources,
    teacher,
)

# The built frontend lands in frontend/dist after `npm run build`.
FRONTEND_DIST = config.PROJECT_ROOT / "frontend" / "dist"

# Emit tracebacks + client chatter to the console so failures aren't silent.
# Level is DEBUG when ARXIV_DEBUG is set, else INFO.
logging.basicConfig(
    level=logging.DEBUG if config.DEBUG else logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

app = Flask(__name__, static_folder=None)
# Books can be large — allow generous uploads for source ingestion (Phase 3d).
app.config["MAX_CONTENT_LENGTH"] = 256 * 1024 * 1024  # 256 MB
# Allow the Vite dev server (localhost:5173) to call the API during development.
CORS(app, resources={r"/api/*": {"origins": "*"}})


def _normalize_arxiv_id(raw: str) -> str:
    """Pull a bare arXiv id out of a pasted id / abs-or-pdf URL, version stripped.

    Reuses the id/URL pattern from arxiv_client so "https://arxiv.org/abs/1706.03762v5"
    and "1706.03762" both resolve to "1706.03762".
    """
    match = arxiv_client._ID_RE.search(raw or "")
    if match:
        return match.group(1).split("v")[0]
    return (raw or "").strip()


# --- API ---------------------------------------------------------------------
@app.get("/api/health")
def health() -> Response:
    return jsonify({"status": "ok", "model": config.TEACHER_MODEL})


@app.get("/api/graph")
def api_graph() -> Response:
    """The neighborhood graph for a seed paper (references + citations + similar).

    `seed` is an arXiv id or a pasted abs/pdf URL. `refresh=1` bypasses the cache.
    """
    seed = _normalize_arxiv_id(request.args.get("seed", ""))
    if not seed:
        return jsonify({"error": "missing 'seed' arXiv id"}), 400
    refresh = request.args.get("refresh", "").lower() in ("1", "true", "yes")
    try:
        result = graph.build_graph(seed, refresh=refresh)
    except semantic_scholar.S2Error as e:
        app.logger.warning("graph build failed for %s: %s", seed, e)
        return jsonify({"error": "Semantic Scholar is unavailable — try again."}), 502
    if not result:
        return jsonify({"error": f"No paper found on Semantic Scholar for {seed}."}), 404
    return jsonify(result)


@app.get("/api/paper/<path:arxiv_id>")
def api_paper(arxiv_id: str) -> Response:
    """Full details (abstract, tldr, authors) for one paper — used to hydrate a
    node's detail panel on click."""
    seed = _normalize_arxiv_id(arxiv_id)
    try:
        node = semantic_scholar.get_paper(f"ARXIV:{seed}")
    except semantic_scholar.S2Error as e:
        app.logger.warning("paper fetch failed for %s: %s", seed, e)
        return jsonify({"error": "Semantic Scholar is unavailable — try again."}), 502
    if not node:
        return jsonify({"error": f"No paper found for {seed}."}), 404
    return jsonify(node)


@app.get("/api/paper/<path:arxiv_id>/figures")
def api_figures(arxiv_id: str) -> Response:
    """A paper's figures + captions (from ar5iv) for the detail panel.

    Returns {available, figures: [{image, caption}]}. Image URLs are rewritten to
    the same-origin proxy below so the browser never hotlinks ar5iv directly.
    ar5iv gaps (no LaTeX render) come back as available:false — not an error."""
    seed = _normalize_arxiv_id(arxiv_id)
    try:
        result = figures.get_figures(seed)
    except Exception:  # ar5iv down/slow — degrade gracefully, don't 500 the panel
        app.logger.warning("figure fetch failed for %s", seed, exc_info=True)
        return jsonify({"available": False, "figures": []})
    for fig in result.get("figures", []):
        fig["image"] = "/api/figure_proxy?src=" + urllib.parse.quote(fig["image"], safe="")
    return jsonify(result)


@app.get("/api/figure_proxy")
def figure_proxy() -> Response:
    """Stream an ar5iv image through our origin (dodges hotlink/CORS).

    Locked to the ar5iv host so this can't be used as an open proxy (SSRF)."""
    src = request.args.get("src", "")
    if not figures.is_ar5iv_url(src):
        return jsonify({"error": "src must be an ar5iv image URL"}), 400
    try:
        data, content_type = figures.fetch_image(src)
    except Exception:
        app.logger.warning("figure proxy failed for %s", src, exc_info=True)
        return Response(status=502)
    return Response(
        data,
        mimetype=content_type,
        headers={"Cache-Control": "public, max-age=86400"},
    )


@app.get("/api/arxiv_search")
def arxiv_search_route() -> Response:
    """Live relevance search across all of arXiv to find a seed paper.

    Query args: q (keywords, title, author, or an arXiv id/URL), optional limit
    (default 25). Returns the matching papers; saves nothing."""
    q = (request.args.get("q") or "").strip()
    try:
        limit = max(1, min(int(request.args.get("limit", "25")), 100))
    except ValueError:
        limit = 25
    if not q:
        return jsonify({"q": q, "count": 0, "papers": []})
    try:
        papers = search.arxiv_search(q, limit=limit)
    except Exception as exc:
        app.logger.exception("arxiv search failed for %r", q)
        return jsonify({"ok": False, "error": str(exc)}), 502
    return jsonify({"q": q, "count": len(papers), "papers": papers})


@app.get("/api/local_search")
def local_search_route() -> Response:
    """Instant seed search over papers already in the local snapshot cache.

    Purely local (no arXiv / S2 calls) — the cache-first results shown while the
    live arXiv search is still in flight, and the only results available when
    Semantic Scholar is rate-limiting us. Never errors: a failure just means no
    local hits."""
    q = (request.args.get("q") or "").strip()
    try:
        limit = max(1, min(int(request.args.get("limit", "10")), 50))
    except ValueError:
        limit = 10
    if not q:
        return jsonify({"q": q, "count": 0, "papers": []})
    try:
        papers = search.local_search(q, limit=limit)
    except Exception:
        app.logger.exception("local search failed for %r", q)
        papers = []
    return jsonify({"q": q, "count": len(papers), "papers": papers})


# --- AI teacher (Phase 3a): streaming lecture + grounded Q&A -----------------
# Session-scoped Q&A history, kept in memory (cleared on restart — fine for v1).
# Maps a client-generated session id -> [{role, content}, ...].
_QA_SESSIONS: dict[str, list[dict]] = {}


def _sse(event: str, data: object) -> str:
    """Format one Server-Sent Event frame."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _sse_response(generator) -> Response:
    """Wrap a generator of SSE frames as a streaming text/event-stream response.

    X-Accel-Buffering:no keeps nginx (if ever put in front) from buffering the
    stream; Cache-Control:no-cache stops intermediaries caching partial output.
    """
    return Response(
        generator,
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/lecture")
def api_lecture() -> Response:
    """Stream a lecture over the visible graph as SSE ``beat`` events.

    Body: {seed: {title,...}, nodes: [visible node objects], mode:
    history|intuition|bridge, target?: {title,...}}. Each ``beat`` event carries
    {heading, text, node_ids} so the frontend can reveal it and light up nodes.
    """
    payload = request.get_json(silent=True) or {}
    nodes = payload.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        return jsonify({"error": "nodes must be a non-empty list"}), 400
    seed = payload.get("seed") or {}
    mode = payload.get("mode") or "history"
    target = payload.get("target")

    def gen():
        try:
            for beat in teacher.lecture_beats(seed, nodes, mode=mode, target=target):
                yield _sse("beat", beat)
            yield _sse("done", {})
        except Exception as exc:  # surface to the panel AND log the traceback
            app.logger.exception("lecture failed")
            yield _sse("error", {"error": str(exc)})

    return _sse_response(gen())


@app.post("/api/ask")
def api_ask() -> Response:
    """Answer a question grounded in the visible graph, streamed as SSE.

    Body: {question, session_id, seed, nodes}. With the agentic backend, also
    emits ``trace`` events (tool steps) and ``nodes`` events ({nodes, edges}) as
    expand_node discovers papers not yet on the graph; always emits ``token``
    events (prose) then a final ``cited`` event ({node_ids}). Conversation
    history is keyed by session_id so follow-ups keep context.
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
    history = _QA_SESSIONS.get(session_id, []) if session_id else []

    # Agentic Q&A (reads papers via tool use) when the API backend is available;
    # otherwise the non-agentic grounded answer (e.g. the claude CLI backend).
    source = (
        teacher.answer_agentic(question, seed, nodes, history)
        if teacher.agentic_available()
        else teacher.answer_stream(question, seed, nodes, history)
    )

    def gen():
        answer_parts: list[str] = []
        try:
            for kind, data in source:
                if kind == "token":
                    answer_parts.append(data)
                    yield _sse("token", {"text": data})
                elif kind == "trace":
                    yield _sse("trace", data)
                elif kind == "nodes":
                    yield _sse("nodes", data)
                elif kind == "discard":
                    # Streamed preamble turned out to precede a tool call — drop it.
                    answer_parts.clear()
                    yield _sse("discard", {})
                elif kind == "cited":
                    yield _sse("cited", {"node_ids": data})
            yield _sse("done", {})
        except Exception as exc:
            app.logger.exception("ask failed")
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


# --- Bring-your-own sources (Phase 3d): the user's local semantic library -----
@app.get("/api/sources")
def api_sources_list() -> Response:
    """List the user's uploaded sources. ``available`` reports whether local
    embeddings + sqlite-vec loaded (so the UI can explain a disabled state)."""
    try:
        available = sources.available()
    except Exception:
        app.logger.exception("sources availability check failed")
        available = False
    return jsonify({"available": available, "sources": sources.list_sources()})


@app.post("/api/sources")
def api_sources_add() -> Response:
    """Ingest a source: either a multipart PDF upload (field ``file``) or a JSON
    body ``{"url": ...}``. Returns the created source record. Synchronous — a big
    book takes a bit while it chunks + embeds."""
    import tempfile

    title = None
    try:
        upload = request.files.get("file")
        if upload and upload.filename:
            title = (request.form.get("title") or "").strip() or None
            suffix = Path(upload.filename).suffix or ".pdf"
            # NB: on Windows an open NamedTemporaryFile holds an exclusive lock,
            # so we must close our handle before save()/ingest can reopen it.
            fd, tmp_path = tempfile.mkstemp(suffix=suffix)
            os.close(fd)
            try:
                upload.save(tmp_path)
                src = sources.ingest_pdf(tmp_path, title=title or Path(upload.filename).stem)
            finally:
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
        else:
            payload = request.get_json(silent=True) or {}
            url = (payload.get("url") or "").strip()
            title = (payload.get("title") or "").strip() or None
            if not url:
                return jsonify({"error": "provide a PDF file or a url"}), 400
            src = sources.ingest_url(url, title=title)
    except sources.SourceError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        app.logger.exception("source ingest failed")
        return jsonify({"error": str(exc)}), 500
    return jsonify(src)


@app.delete("/api/sources/<source_id>")
def api_sources_delete(source_id: str) -> Response:
    """Remove a source and its chunks/vectors from the library."""
    return jsonify({"deleted": sources.delete_source(source_id)})


# --- Serve the built frontend (production) -----------------------------------
@app.get("/")
@app.get("/<path:path>")
def serve_frontend(path: str = "") -> Response:
    if FRONTEND_DIST.exists():
        target = FRONTEND_DIST / path
        if path and target.is_file():
            return send_from_directory(FRONTEND_DIST, path)
        return send_from_directory(FRONTEND_DIST, "index.html")
    return Response(
        "Frontend not built yet. Run `npm run build` in the frontend/ folder, "
        "or use the Vite dev server (`npm run dev`) during development.",
        mimetype="text/plain",
    )


def main() -> None:
    # threaded=True lets the frontend stream SSE (lecture/ask) while other
    # requests (graph, figures) are served concurrently.
    app.run(
        host=config.FLASK_HOST,
        port=config.FLASK_PORT,
        debug=True,
        threaded=True,
    )


if __name__ == "__main__":
    main()
