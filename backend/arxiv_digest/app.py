"""Flask app factory for arXiv Atlas.

The API surface lives in ``routes/`` — one blueprint per concern (graph, search,
teacher, sources, sessions). This module just builds the app, wires those
blueprints on, and (in production) serves the built React frontend.

See ``routes/*.py`` for the endpoint list.
"""

from __future__ import annotations

import logging

from flask import Flask, Response, jsonify, send_from_directory
from flask_cors import CORS

from . import config
from .routes import register_blueprints

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

register_blueprints(app)


@app.get("/api/health")
def health() -> Response:
    """Liveness check.

    Returns:
        JSON ``{status, model}`` — the configured teacher model doubles as a
        quick config sanity check.
    """
    return jsonify({"status": "ok", "model": config.TEACHER_MODEL})


# --- Serve the built frontend (production) -----------------------------------
@app.get("/")
@app.get("/<path:path>")
def serve_frontend(path: str = "") -> Response:
    """Serve the built React frontend (SPA fallback to index.html).

    Args:
        path: The requested path; real files under ``frontend/dist`` are
            served directly, anything else falls back to ``index.html``.

    Returns:
        The static file or index.html — or a plain-text hint when the
        frontend hasn't been built yet.
    """
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
    """Run the Flask dev server (the `serve` CLI command lands here).

    ``threaded=True`` lets the frontend stream SSE (lecture/ask) while other
    requests (graph, figures) are served concurrently.

    Returns:
        None (blocks until the server exits).
    """
    app.run(
        host=config.FLASK_HOST,
        port=config.FLASK_PORT,
        debug=True,
        threaded=True,
    )


if __name__ == "__main__":
    main()
