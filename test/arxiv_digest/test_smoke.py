"""Smoke tests: the app boots and its keyless endpoints answer.

These are the first tests in the project (Phase: nox + CI backbone). They stay
offline — no live arXiv / Semantic Scholar calls — so they're safe to run in the
`uv run nox` gate. Real feature coverage grows from here.
"""

from __future__ import annotations

import pytest

from arxiv_digest.app import app as flask_app


@pytest.fixture()
def client():
    """A Flask test client over the real app (no network is touched here)."""
    flask_app.config.update(TESTING=True)
    return flask_app.test_client()


def test_app_imports() -> None:
    """The application factory imports and exposes a Flask app."""
    assert flask_app.name


def test_taxonomy_endpoint(client) -> None:
    """/api/taxonomy returns the grouped arXiv taxonomy (keyless, offline)."""
    resp = client.get("/api/taxonomy")
    assert resp.status_code == 200
    groups = resp.get_json()["groups"]
    assert isinstance(groups, list) and groups
    # Each group carries a name and a non-empty category list of {code, name}.
    first = groups[0]
    assert first["group"]
    assert first["categories"][0]["code"]


def test_blank_arxiv_search_is_empty(client) -> None:
    """A blank query short-circuits to an empty result without hitting arXiv."""
    resp = client.get("/api/arxiv_search?q=")
    assert resp.status_code == 200
    assert resp.get_json() == {"q": "", "count": 0, "papers": []}
