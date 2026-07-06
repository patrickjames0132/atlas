"""Sources routes: the list + availability flag, dual-mode ingestion with
its two-tier error contract, temp-file hygiene, and idempotent delete."""

from __future__ import annotations

import io
import os

from arxiv_digest.routes import sources as sources_routes
from arxiv_digest.services.sources import SourceError

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


def test_pdf_upload_ingests_from_a_cleaned_up_temp_file(client, monkeypatch):
    seen = {}

    def fake_ingest_pdf(path, title=None):
        seen["path"], seen["title"] = str(path), title
        seen["existed_during_ingest"] = os.path.exists(path)
        return RECORD

    monkeypatch.setattr(sources_routes.sources_service, "ingest_pdf", fake_ingest_pdf)
    response = client.post(
        "/api/sources",
        data={"file": (io.BytesIO(b"%PDF-1.4 fake"), "goodfellow.pdf")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 200 and response.json == RECORD
    assert seen["title"] == "goodfellow"  # falls back to the filename stem
    assert seen["path"].endswith(".pdf")
    assert seen["existed_during_ingest"] is True
    assert not os.path.exists(seen["path"])  # temp file removed afterwards


def test_url_ingestion_and_the_no_input_400(client, monkeypatch):
    seen = {}

    def fake_ingest_url(url, title=None):
        seen["url"], seen["title"] = url, title
        return RECORD

    monkeypatch.setattr(sources_routes.sources_service, "ingest_url", fake_ingest_url)
    response = client.post("/api/sources", json={"url": " https://example.org/notes ", "title": " Notes "})
    assert response.status_code == 200
    assert seen == {"url": "https://example.org/notes", "title": "Notes"}

    assert client.post("/api/sources", json={}).status_code == 400


def test_two_tier_error_contract(client, monkeypatch):
    def scanned(url, title=None):
        raise SourceError("This PDF has no extractable text — is it scanned?")

    monkeypatch.setattr(sources_routes.sources_service, "ingest_url", scanned)
    response = client.post("/api/sources", json={"url": "https://example.org/x"})
    assert response.status_code == 400
    assert "is it scanned?" in response.json["error"]  # user-facing by design

    def unexpected(url, title=None):
        raise RuntimeError("sqlite disk I/O error at /private/path")

    monkeypatch.setattr(sources_routes.sources_service, "ingest_url", unexpected)
    response = client.post("/api/sources", json={"url": "https://example.org/x"})
    assert response.status_code == 500
    assert "/private/path" not in response.json["error"]  # canned; details in the log


def test_delete_is_idempotent(client, monkeypatch):
    monkeypatch.setattr(
        sources_routes.sources_service, "delete_source", lambda source_id: False
    )
    assert client.delete("/api/sources/nope").json == {"deleted": False}
