"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
The Flask API surface, split into one blueprint per concern.

``app.py`` calls :func:`register_blueprints` to wire them all onto the app.
Each route module owns its endpoints and any small per-concern helpers (SSE
framing, arXiv-id normalization) so the app factory stays thin.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

from flask import Flask

from .agents import bp as agents_bp
from .graph import bp as graph_bp
from .search import bp as search_bp
from .sessions import bp as sessions_bp
from .settings import bp as settings_bp
from .sources import bp as sources_bp

# Order is cosmetic — every route carries its own full /api/... path, so
# there's no prefix overlap between blueprints.
ALL_BLUEPRINTS = [graph_bp, search_bp, agents_bp, sessions_bp, sources_bp, settings_bp]


def register_blueprints(app: Flask) -> None:
    """Register every route blueprint onto the app.

    Args:
        app: The Flask app under construction.
    """
    for bp in ALL_BLUEPRINTS:
        app.register_blueprint(bp)
