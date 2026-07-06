"""The app factory: health, CORS scope, the upload cap, and the SPA
serving/fallback/unbuilt behaviors."""

from __future__ import annotations

from arxiv_digest import app as app_module


def client():
    return app_module.create_app().test_client()


def test_health():
    response = client().get("/api/health")
    assert response.status_code == 200
    assert response.json == {"status": "ok"}


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
