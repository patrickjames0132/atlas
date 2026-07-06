"""Shared fixture for route tests: a test client over the real app factory,
so every test exercises the app exactly as `create_app` wires it (CORS,
health, blueprints, SPA catch-all included)."""

from __future__ import annotations

import pytest

from arxiv_digest.app import create_app


@pytest.fixture
def client():
    return create_app().test_client()
