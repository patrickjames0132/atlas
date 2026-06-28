"""Flask API for the dashboard.

Endpoints
---------
GET  /api/papers?date=YYYY-MM-DD   -> papers for a date (default: latest)
GET  /api/dates                    -> list of dates that have papers
POST /api/refresh                  -> run the fetch/parse/summarize pipeline
GET  /api/export/notebooklm?date=  -> a Markdown digest to drop into NotebookLM
GET  /api/health                   -> simple liveness check

In production it also serves the built React app from frontend/dist.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, request, Response, send_from_directory
from flask_cors import CORS

from . import config, pipeline, store, summarizer

# The built frontend lands in frontend/dist after `npm run build`.
FRONTEND_DIST = config.PROJECT_ROOT / "frontend" / "dist"

app = Flask(__name__, static_folder=None)
# Allow the Vite dev server (localhost:5173) to call the API during development.
CORS(app, resources={r"/api/*": {"origins": "*"}})


# --- API ---------------------------------------------------------------------
@app.get("/api/health")
def health() -> Response:
    return jsonify({"status": "ok", "model": config.ANTHROPIC_MODEL})


@app.get("/api/papers")
def get_papers() -> Response:
    digest_date = request.args.get("date")
    papers = store.get_papers(digest_date)
    return jsonify(
        {
            "date": papers[0]["digest_date"] if papers else digest_date,
            "count": len(papers),
            "papers": papers,
            "dates": store.available_dates(),
            "followed_categories": config.ARXIV_CATEGORIES,
        }
    )


@app.get("/api/dates")
def get_dates() -> Response:
    return jsonify({"dates": store.available_dates()})


@app.post("/api/refresh")
def refresh() -> Response:
    """Pull papers submitted on a given date (default today) from arXiv.

    Summaries are generated per-row on demand, so this does NOT summarize by
    default (pass summarize=true to also do so)."""
    payload = request.get_json(silent=True) or {}
    digest_date = payload.get("date")
    summarize = payload.get("summarize", False)

    if digest_date:
        try:
            datetime.strptime(digest_date, "%Y-%m-%d")
        except ValueError:
            return jsonify({"ok": False, "error": "date must be YYYY-MM-DD"}), 400

    try:
        result = pipeline.run(digest_date=digest_date, summarize=summarize)
    except Exception as exc:  # surface the error to the dashboard
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
        return jsonify({"ok": False, "error": str(exc)}), 500

    updated = store.get_paper(arxiv_id)
    if not updated or not updated.get("summary"):
        return jsonify({"ok": False, "error": "summary generation failed"}), 502
    return jsonify({"ok": True, "arxiv_id": arxiv_id, "summary": updated["summary"]})


@app.get("/api/export/notebooklm")
def export_notebooklm() -> Response:
    """Return a clean Markdown digest you can paste/upload into NotebookLM."""
    digest_date = request.args.get("date")
    papers = store.get_papers(digest_date)
    date_label = papers[0]["digest_date"] if papers else (digest_date or "today")

    lines = [f"# arXiv Digest — {date_label}", ""]
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
    filename = f"arxiv-digest-{date_label}.md"
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
