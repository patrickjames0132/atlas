"""Sources routes: the list + availability flag, progress-streaming
ingestion with its two-tier error contract, temp-file hygiene, and
idempotent delete."""

from __future__ import annotations

import io
import json
import os

from atlas.routes import sources as sources_routes
from atlas.services.sources import SourceError


def frames(response) -> list[tuple[str, dict]]:
    parsed = []
    for chunk in response.data.decode().strip().split("\n\n"):
        event_line, data_line = chunk.split("\n")
        parsed.append(
            (event_line.removeprefix("event: "), json.loads(data_line.removeprefix("data: ")))
        )
    return parsed

RECORD = {"id": "src01", "title": "Deep Learning", "kind": "pdf", "pages": 800}


def test_list_reports_availability_and_degrades(client, monkeypatch):
    monkeypatch.setattr(sources_routes.sources_service, "available", lambda: True)
    monkeypatch.setattr(sources_routes.sources_service, "list_sources", lambda: [RECORD])
    assert client.get("/api/sources").json == {"available": True, "sources": [RECORD]}

    def boom():
        raise RuntimeError("torch exploded")

    monkeypatch.setattr(sources_routes.sources_service, "available", boom)
    response = client.get("/api/sources")
    assert response.status_code == 200
    assert response.json["available"] is False  # degrade, don't error


def test_pdf_upload_streams_progress_from_a_cleaned_up_temp_file(client, monkeypatch):
    seen = {}

    def fake_ingest_pdf(path, title=None, on_progress=None):
        seen["path"], seen["title"] = str(path), title
        seen["existed_during_ingest"] = os.path.exists(path)
        if on_progress:
            on_progress(0, 2)
            on_progress(2, 2)
        return RECORD

    monkeypatch.setattr(sources_routes.sources_service, "ingest_pdf", fake_ingest_pdf)
    response = client.post(
        "/api/sources",
        data={"file": (io.BytesIO(b"%PDF-1.4 fake"), "goodfellow.pdf")},
        content_type="multipart/form-data",
    )
    assert frames(response) == [
        ("progress", {"done": 0, "total": 2}),
        ("progress", {"done": 2, "total": 2}),
        ("done", RECORD),
    ]
    assert seen["title"] == "goodfellow"  # falls back to the filename stem
    assert seen["path"].endswith(".pdf")
    assert seen["existed_during_ingest"] is True
    assert not os.path.exists(seen["path"])  # temp file removed afterwards


def test_url_ingestion_and_the_no_input_400(client, monkeypatch):
    seen = {}

    def fake_ingest_url(url, title=None, on_progress=None):
        seen["url"], seen["title"] = url, title
        return RECORD

    monkeypatch.setattr(sources_routes.sources_service, "ingest_url", fake_ingest_url)
    response = client.post("/api/sources", json={"url": " https://example.org/notes ", "title": " Notes "})
    assert frames(response) == [("done", RECORD)]
    assert seen == {"url": "https://example.org/notes", "title": "Notes"}

    assert client.post("/api/sources", json={}).status_code == 400  # pre-stream JSON 400


def test_two_tier_error_contract(client, monkeypatch):
    def scanned(url, title=None, on_progress=None):
        raise SourceError("This PDF has no extractable text — is it scanned?")

    monkeypatch.setattr(sources_routes.sources_service, "ingest_url", scanned)
    ((kind, data),) = frames(client.post("/api/sources", json={"url": "https://example.org/x"}))
    assert kind == "error"
    assert "is it scanned?" in data["message"]  # user-facing by design

    def unexpected(url, title=None, on_progress=None):
        raise RuntimeError("sqlite disk I/O error at /private/path")

    monkeypatch.setattr(sources_routes.sources_service, "ingest_url", unexpected)
    ((kind, data),) = frames(client.post("/api/sources", json={"url": "https://example.org/x"}))
    assert kind == "error"
    assert "/private/path" not in data["message"]  # canned; details in the log


def test_delete_is_idempotent(client, monkeypatch):
    monkeypatch.setattr(
        sources_routes.sources_service, "delete_source", lambda source_id: False
    )
    assert client.delete("/api/sources/nope").json == {"deleted": False}


def test_source_figure_route_serves_png_and_404s(client, monkeypatch):
    """The library figure route: PNG on success; 404 (never 500) for unknown
    sources/indices or sources without a stored PDF."""
    from atlas.routes import sources as sources_routes

    monkeypatch.setattr(
        sources_routes.sources_service,
        "render_source_figure",
        lambda source_id, index: b"\x89PNG library",
    )
    response = client.get("/api/sources/src1/figure/0")
    assert response.status_code == 200
    assert response.mimetype == "image/png"
    assert response.data == b"\x89PNG library"

    def refuse(source_id, index):
        raise RuntimeError("no such source")

    monkeypatch.setattr(sources_routes.sources_service, "render_source_figure", refuse)
    assert client.get("/api/sources/ghost/figure/0").status_code == 404
