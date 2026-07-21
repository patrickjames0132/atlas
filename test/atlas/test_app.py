"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
The app factory: health, CORS scope, the upload cap, and the SPA
serving/fallback/unbuilt behaviors.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

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
