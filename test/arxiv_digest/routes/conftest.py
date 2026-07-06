"""Shared fixture for route tests: a Flask test client over the real
blueprint registry, so every test exercises the app the way `app.py` will
wire it."""

from __future__ import annotations

import pytest
from flask import Flask

from arxiv_digest.routes import register_blueprints


@pytest.fixture
def client():
    app = Flask(__name__)
    register_blueprints(app)
    return app.test_client()
