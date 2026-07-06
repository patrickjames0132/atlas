"""The Flask API surface, split into one blueprint per concern.

``app.py`` calls :func:`register_blueprints` to wire them all onto the app.
Each route module owns its endpoints and any small per-concern helpers (SSE
framing, arXiv-id normalization) so the app factory stays thin.

Being ported module by module (Phase 5) — blueprints join ``ALL_BLUEPRINTS``
as they land: graph, then search, sessions, sources, agents.
"""

from __future__ import annotations

from flask import Flask

from .graph import bp as graph_bp

# Order is cosmetic — every route carries its own full /api/... path, so
# there's no prefix overlap between blueprints.
ALL_BLUEPRINTS = [graph_bp]


def register_blueprints(app: Flask) -> None:
    """Register every route blueprint onto the app.

    Args:
        app: The Flask app under construction.
    """
    for bp in ALL_BLUEPRINTS:
        app.register_blueprint(bp)
