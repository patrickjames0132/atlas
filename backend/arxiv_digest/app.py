"""Flask API for the dashboard.

Endpoints
---------
GET  /api/papers?start=&end=       -> papers submitted in a date range
GET  /api/search?q=&start=&end=    -> hybrid search (BM25 + embedding similarity)
GET  /api/arxiv_search?q=&limit=   -> live relevance search across all of arXiv
POST /api/arxiv_search/add         -> add live arXiv result(s) to the library
GET  /api/dates                    -> list of dates that have papers
POST /api/refresh                  -> run the fetch/parse/summarize pipeline
GET  /api/export/notebooklm?start=&end=&q= -> a Markdown digest for NotebookLM
                                     (q present -> only that search's results)
GET  /api/health                   -> simple liveness check

In production it also serves the built React app from frontend/dist.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, request, Response, send_from_directory
from flask_cors import CORS

from . import config, pipeline, search, store, summarizer, taxonomy

# The built frontend lands in frontend/dist after `npm run build`.
FRONTEND_DIST = config.PROJECT_ROOT / "frontend" / "dist"

# Emit tracebacks + arXiv client chatter to the console so failed pulls aren't
# silent. Level is DEBUG when ARXIV_DEBUG is set, else INFO.
logging.basicConfig(
    level=logging.DEBUG if config.DEBUG else logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

app = Flask(__name__, static_folder=None)
# Allow the Vite dev server (localhost:5173) to call the API during development.
CORS(app, resources={r"/api/*": {"origins": "*"}})


def _valid_date(value: str) -> bool:
    try:
        datetime.strptime(value, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def _range_args() -> tuple[str, str]:
    """Resolve (start, end) from request args, tolerating a single `date`.

    Both default to today's most-recent data when omitted; if only one bound is
    given the range collapses to that single day.
    """
    start = request.args.get("start") or request.args.get("date")
    end = request.args.get("end") or request.args.get("date") or start
    start = start or end
    return start, end


# --- API ---------------------------------------------------------------------
@app.get("/api/health")
def health() -> Response:
    return jsonify({"status": "ok", "model": config.ANTHROPIC_MODEL})


@app.get("/api/papers")
def get_papers() -> Response:
    start, end = _range_args()
    if start and end:
        papers = store.get_papers_in_range(start, end)
        coverage = store.pull_coverage(start, end)
    else:
        # No range given: fall back to the latest date on record.
        papers = store.get_papers()
        coverage = {}
    return jsonify(
        {
            "start": start,
            "end": end,
            "count": len(papers),
            "papers": papers,
            "dates": store.available_dates(),
            "followed_categories": store.get_followed_categories(),
            # date -> categories already fetched for it, so the dashboard can skip
            # re-pulling a day only when every followed category is covered.
            "coverage": coverage,
        }
    )


@app.get("/api/search")
def search_route() -> Response:
    """Hybrid (lexical + semantic) search over stored papers, scoped to a date
    range when given.

    Query args: q (the search text), plus optional start/end (or a single date).
    Blends BM25 keyword matches with embedding similarity via rank fusion; falls
    back to lexical-only when embeddings aren't available. ``mode`` reports which
    ran. Returns the same paper shape as /api/papers (plus per-row matched_by).
    """
    q = (request.args.get("q") or "").strip()
    start, end = _range_args()
    if not q:
        papers: list[dict] = []
        mode = "lexical"
    else:
        papers, mode = search.hybrid_search(q, start, end)
    return jsonify(
        {
            "q": q,
            "start": start,
            "end": end,
            "mode": mode,
            "count": len(papers),
            "papers": papers,
        }
    )


@app.get("/api/arxiv_search")
def arxiv_search_route() -> Response:
    """Live relevance search across ALL of arXiv (not just the stored library).

    Query args: q (keywords, title, author, or an arXiv id/URL), optional limit
    (default 25). Ignores the date range and followed categories. Each result is
    tagged ``in_library`` so the dashboard shows Add vs In library. Saves nothing.
    """
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


@app.post("/api/arxiv_search/add")
def arxiv_search_add() -> Response:
    """Add live arXiv-search results to the library. Body: {"arxiv_ids": [...]}
    (or a single "arxiv_id"). Fetches each by id, stores and embeds it."""
    payload = request.get_json(silent=True) or {}
    ids = payload.get("arxiv_ids")
    if ids is None and payload.get("arxiv_id"):
        ids = [payload["arxiv_id"]]
    if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids) or not ids:
        return jsonify({"ok": False, "error": "arxiv_ids must be a non-empty list of strings"}), 400
    try:
        result = pipeline.add_papers_by_ids(ids)
    except Exception as exc:
        app.logger.exception("adding arxiv papers failed: %s", ids)
        return jsonify({"ok": False, "error": str(exc)}), 502
    return jsonify({"ok": True, **result})


@app.get("/api/dates")
def get_dates() -> Response:
    return jsonify({"dates": store.available_dates()})


@app.get("/api/categories")
def get_categories() -> Response:
    """The full arXiv taxonomy plus the categories the user currently follows."""
    return jsonify(
        {
            "groups": taxonomy.groups(),
            "followed": store.get_followed_categories(),
        }
    )


@app.put("/api/categories")
def put_categories() -> Response:
    """Replace the followed-category set. Body: {"followed": ["cs.LG", ...]}."""
    payload = request.get_json(silent=True) or {}
    followed = payload.get("followed")
    if not isinstance(followed, list) or not all(isinstance(c, str) for c in followed):
        return jsonify({"ok": False, "error": "followed must be a list of strings"}), 400

    valid = taxonomy.valid_codes()
    unknown = [c for c in followed if c not in valid]
    if unknown:
        return jsonify({"ok": False, "error": f"unknown categories: {', '.join(unknown)}"}), 400
    if not followed:
        return jsonify({"ok": False, "error": "select at least one category"}), 400

    saved = store.set_followed_categories(followed)
    return jsonify({"ok": True, "followed": saved})


@app.post("/api/refresh")
def refresh() -> Response:
    """Pull papers submitted in a date range (default today) from arXiv.

    Body: {"start": "YYYY-MM-DD", "end": "YYYY-MM-DD", "summarize": false}. A
    single "date" is also accepted (collapses to that day). Summaries are
    generated per-row on demand, so this does NOT summarize by default."""
    payload = request.get_json(silent=True) or {}
    start = payload.get("start") or payload.get("date")
    end = payload.get("end") or payload.get("date") or start

    for value in (start, end):
        if value and not _valid_date(value):
            return jsonify({"ok": False, "error": "dates must be YYYY-MM-DD"}), 400
    if start and end and start > end:
        return jsonify({"ok": False, "error": "start must be on or before end"}), 400

    summarize = payload.get("summarize", False)

    try:
        result = pipeline.run(start_date=start, end_date=end, summarize=summarize)
    except Exception as exc:  # surface the error to the dashboard AND log it
        app.logger.exception("refresh failed for %s..%s", start, end)
        return jsonify({"ok": False, "error": str(exc)}), 500
    return jsonify({"ok": True, **result})


@app.post("/api/papers/<arxiv_id>/summary")
def summarize_paper(arxiv_id: str) -> Response:
    """Generate (or return the cached) AI summary for a single paper."""
    paper = store.get_paper(arxiv_id)
    if paper is None:
        return jsonify({"ok": False, "error": "paper not found"}), 404
    if paper.get("summary"):
        return jsonify(
            {"ok": True, "arxiv_id": arxiv_id, "summary": paper["summary"], "cached": True}
        )
    try:
        summarizer.summarize_pending([paper])
    except Exception as exc:
        app.logger.exception("summary failed for %s", arxiv_id)
        return jsonify({"ok": False, "error": str(exc)}), 500

    updated = store.get_paper(arxiv_id)
    if not updated or not updated.get("summary"):
        return jsonify({"ok": False, "error": "summary generation failed"}), 502
    return jsonify({"ok": True, "arxiv_id": arxiv_id, "summary": updated["summary"]})


@app.get("/api/export/notebooklm")
def export_notebooklm() -> Response:
    """Return a clean Markdown digest you can paste/upload into NotebookLM.

    When a search query ``q`` is given, the digest contains only that search's
    results (hybrid lexical + semantic, scoped to the date range) — matching what
    you see in the dashboard. Without ``q`` it exports the whole date range.
    """
    start, end = _range_args()
    q = (request.args.get("q") or "").strip()
    if q:
        papers, _mode = search.hybrid_search(q, start, end)
    elif start and end:
        papers = store.get_papers_in_range(start, end)
    else:
        papers = store.get_papers()
    date_label = start if start == end else f"{start} to {end}"
    date_label = date_label or "today"
    if q:
        date_label = f"{date_label} · “{q}”"

    heading = f"# arXiv Digest — {date_label}"
    if q:
        heading += f"\n\n_Search: **{q}** — {len(papers)} matching paper(s)._"
    lines = [heading, ""]
    for i, p in enumerate(papers, 1):
        lines.append(f"## {i}. {p['title']}")
        if p.get("authors"):
            lines.append(f"**Authors:** {p['authors']}")
        if p.get("categories"):
            lines.append(f"**Categories:** {p['categories']}")
        lines.append(f"**Link:** {p['url']}")
        lines.append("")
        if p.get("summary"):
            lines.append(f"**AI summary:** {p['summary']}")
            lines.append("")
        if p.get("abstract"):
            lines.append(f"**Abstract:** {p['abstract']}")
            lines.append("")
        lines.append("---")
        lines.append("")

    # Also append a bare list of PDF links — handy as NotebookLM sources.
    lines.append("## PDF links")
    for p in papers:
        lines.append(f"- {p['url'].replace('/abs/', '/pdf/')}")

    markdown = "\n".join(lines)
    range_label = start if start == end else f"{start} to {end}"
    range_label = range_label or "today"
    slug = f"{range_label}-{q}" if q else range_label
    slug = re.sub(r"[^0-9A-Za-z-]+", "-", slug).strip("-") or "digest"
    filename = f"arxiv-digest-{slug}.md"
    return Response(
        markdown,
        mimetype="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


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
    store.init_db()
    # threaded=True lets the dashboard poll /api/papers for live updates while a
    # /api/refresh is still running (summaries are committed as they're generated).
    app.run(
        host=config.FLASK_HOST,
        port=config.FLASK_PORT,
        debug=True,
        threaded=True,
    )


if __name__ == "__main__":
    main()
