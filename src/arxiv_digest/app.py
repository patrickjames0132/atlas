"""Flask app factory for arXiv Atlas.

The API surface lives in ``routes/`` — one blueprint per concern (graph,
search, agents, sources, sessions). This module just builds the app, wires
those blueprints on, and (in production) serves the built React frontend.

See ``routes/README.md`` for the endpoint list.
"""

from __future__ import annotations

import logging
from pathlib import Path

from flask import Flask, Response, jsonify, send_from_directory
from flask_cors import CORS

from .config import config
from .routes import register_blueprints

# The built frontend lands in frontend/dist after `npm run build`. Derived
# from this file's location (src/arxiv_digest/app.py, two parents up to the
# repo root) — the app runs from an editable src-layout install, so the repo
# layout is a safe anchor. Module-level so tests can point it elsewhere.
FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


def create_app() -> Flask:
    """Build the Flask app: logging, CORS, blueprints, health, SPA serving.

    A factory (not a module-level app) so each test builds a fresh,
    isolated instance.

    Returns:
        The configured Flask app.
    """
    # Emit tracebacks + client chatter to the console so failures aren't
    # silent. DEBUG level when config.server.debug is set, else INFO.
    logging.basicConfig(
        level=logging.DEBUG if config.server.debug else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    app = Flask(__name__, static_folder=None)
    # Books can be large — allow generous uploads for source ingestion.
    app.config["MAX_CONTENT_LENGTH"] = 256 * 1024 * 1024  # 256 MB
    # Allow the Vite dev server (localhost:5173) to call the API during
    # development.
    CORS(app, resources={r"/api/*": {"origins": "*"}})
    register_blueprints(app)

    @app.get("/api/health")
    def health() -> Response:
        """Liveness check.

        Returns:
            JSON ``{status: "ok"}`` — config validity is already proven by
            the process being up (the config loads, fully validated, at
            import).
        """
        return jsonify({"status": "ok"})

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

    return app


def main() -> None:
    """Run the Flask dev server (the `serve` CLI command lands here).

    ``threaded=True`` lets the frontend stream SSE (lecture/ask) while other
    requests (graph, figures) are served concurrently. ``debug`` follows
    config — the old app hardcoded ``debug=True``, running the reloader and
    interactive debugger on every "production" serve.

    Returns:
        None (blocks until the server exits).
    """
    create_app().run(
        host=config.server.host,
        port=config.server.port,
        debug=config.server.debug,
        threaded=True,
    )


if __name__ == "__main__":
    main()
