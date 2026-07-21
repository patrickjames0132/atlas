"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
Shared fixture for route tests: a test client over the real app factory,
so every test exercises the app exactly as `create_app` wires it (CORS,
health, blueprints, SPA catch-all included).

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

import pytest

from atlas.app import create_app


@pytest.fixture
def client():
    return create_app().test_client()
