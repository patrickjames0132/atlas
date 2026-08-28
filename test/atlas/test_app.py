"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
The app factory: health, CORS scope, the upload cap, and the SPA
serving/fallback/unbuilt behaviors.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

import pytest

from atlas import app as app_module


def client():
    return app_module.create_app().test_client()


def test_health():
    response = client().get("/api/health")
    assert response.status_code == 200
    assert response.json == {"status": "ok"}


def test_main_defaults_to_config_and_honors_overrides(monkeypatch):
    captured: dict = {}

    class FakeApp:
        def run(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(app_module, "create_app", lambda: FakeApp())

    # No overrides -> the config host/port; threaded stays on for SSE.
    app_module.main()
    assert captured["host"] == app_module.config.server.host
    assert captured["port"] == app_module.config.server.port
    assert captured["threaded"] is True

    # Explicit overrides win over config.
    app_module.main(host="0.0.0.0", port=5050)
    assert captured["host"] == "0.0.0.0"
    assert captured["port"] == 5050


def test_cors_covers_api_routes():
    # flask-cors answers a concrete Origin by echoing it (not a literal "*").
    response = client().get("/api/health", headers={"Origin": "http://localhost:5173"})
    assert response.headers["Access-Control-Allow-Origin"] == "http://localhost:5173"


def test_upload_cap_allows_books():
    assert app_module.create_app().config["MAX_CONTENT_LENGTH"] == 256 * 1024 * 1024


def test_spa_serves_real_files_and_falls_back(tmp_path, monkeypatch):
    (tmp_path / "index.html").write_text("<html>atlas</html>")
    (tmp_path / "app.js").write_text("console.log('atlas')")
    monkeypatch.setattr(app_module, "FRONTEND_DIST", tmp_path)

    web = client()
    assert b"console.log" in web.get("/app.js").data  # a real file serves directly
    assert b"atlas" in web.get("/").data  # root -> index.html
    assert b"atlas" in web.get("/some/spa/route").data  # SPA fallback -> index.html


def test_unbuilt_frontend_gets_a_hint(tmp_path, monkeypatch):
    monkeypatch.setattr(app_module, "FRONTEND_DIST", tmp_path / "missing")
    response = client().get("/")
    assert response.mimetype == "text/plain"
    assert b"npm run build" in response.data


def _blank_every_vendor(monkeypatch):
    """Strip every credential so `configured_vendors()` comes back empty.

    Walks the provider blocks rather than naming their fields, so a vendor
    added later is blanked here too instead of quietly leaving this test
    weaker than it reads.

    Args:
        monkeypatch: The pytest fixture, so the real config is restored.
    """
    providers = app_module.config.llm.providers
    for vendor_name in type(providers).model_fields:
        vendor = getattr(providers, vendor_name)
        for field_name, field in type(vendor).model_fields.items():
            if field.annotation is str:
                monkeypatch.setattr(vendor, field_name, "")
    assert providers.configured_vendors() == []


def test_app_starts_with_no_llm_vendor_configured_at_all(monkeypatch):
    """The keyless promise: no key, no vendor, still a running graph explorer.

    Until v7.14.0 this was impossible to write. Every agent package built its
    model at import (``Agent(factory.build_model(...))`` at module level), so
    importing the app constructed a provider for whatever vendor each agent
    named — and with that vendor blank, construction raised and ``create_app``
    never returned. README.md and docs/configuration.md both promise the
    explorer runs free and keyless; this is the test that keeps the promise
    honest.

    Reloading is the point, not incidental: the failure was an *import-time*
    one, and every agent module is long since imported by the time this runs.
    """
    import importlib

    _blank_every_vendor(monkeypatch)

    for module_name in (
        "atlas.agents.orchestrators.lecturer.main",
        "atlas.agents.orchestrators.researcher.main",
        "atlas.agents.orchestrators.summarizer.main",
        "atlas.agents.workers.search.papers.main",
        "atlas.agents.workers.search.web.main",
    ):
        importlib.reload(importlib.import_module(module_name))

    response = app_module.create_app().test_client().get("/api/health")
    assert response.status_code == 200


def test_the_teacher_is_the_only_thing_that_fails_keyless(monkeypatch):
    """...and it fails with an actionable message, not a stack trace."""
    from atlas.agents import factory

    _blank_every_vendor(monkeypatch)
    monkeypatch.setattr(factory, "_MODELS", {})

    with pytest.raises(ValueError) as caught:
        factory.model_for("summarizer")
    message = str(caught.value)
    assert "config.json" in message
    # Naming the configured alternatives is the actionable half; with none
    # configured it has to say that rather than printing an empty list.
    assert "(none configured)" in message
