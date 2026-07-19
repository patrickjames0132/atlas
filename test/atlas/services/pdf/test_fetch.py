"""The OA-PDF fetcher: download, magic/size defenses, disk cache, LRU prune.

All network is faked by monkeypatching ``urllib.request.urlopen`` — a
download that actually escapes to the network would hang the offline suite.
"""

from __future__ import annotations

import io
import os
import time

import pytest

from atlas.config import config
from atlas.services.pdf import PdfError, fetch


class _FakeResponse(io.BytesIO):
    """A minimal urlopen() context manager streaming canned bytes."""

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


def _serve(monkeypatch, payload: bytes) -> list[str]:
    """Route urlopen to canned bytes, recording requested URLs."""
    requested: list[str] = []

    def fake_urlopen(request, timeout=None):
        requested.append(request.full_url)
        return _FakeResponse(payload)

    monkeypatch.setattr(fetch.urllib.request, "urlopen", fake_urlopen)
    return requested


def test_fetch_downloads_once_then_serves_from_disk(monkeypatch):
    requested = _serve(monkeypatch, b"%PDF-1.5 fake body")
    first = fetch.fetch_pdf("https://host/paper.pdf")
    second = fetch.fetch_pdf("https://host/paper.pdf")
    assert first == second and first.read_bytes().startswith(b"%PDF")
    assert requested == ["https://host/paper.pdf"]  # one network hit total


def test_fetch_rejects_non_http_and_non_pdf(monkeypatch):
    with pytest.raises(PdfError):
        fetch.fetch_pdf("file:///etc/passwd")
    _serve(monkeypatch, b"<html>consent page</html>")
    with pytest.raises(PdfError):
        fetch.fetch_pdf("https://host/consent.pdf")
    # The rejected payload must not have been cached as a PDF.
    assert fetch.cached_path("https://host/consent.pdf") is None


def test_fetch_aborts_oversized_downloads(monkeypatch):
    monkeypatch.setattr(config.pdf, "max_bytes", 100)
    _serve(monkeypatch, b"%PDF" + b"x" * 200)
    with pytest.raises(PdfError):
        fetch.fetch_pdf("https://host/huge.pdf")


def test_prune_evicts_least_recently_used(monkeypatch):
    monkeypatch.setattr(config.pdf, "cache_files", 2)
    _serve(monkeypatch, b"%PDF fake")
    fetch.fetch_pdf("https://host/one.pdf")
    # Distinct mtimes so LRU order is deterministic on coarse filesystems.
    oldest = fetch.cached_path("https://host/one.pdf")
    past = time.time() - 3600
    os.utime(oldest, (past, past))
    fetch.fetch_pdf("https://host/two.pdf")
    fetch.fetch_pdf("https://host/three.pdf")
    assert fetch.cached_path("https://host/one.pdf") is None  # evicted
    assert fetch.cached_path("https://host/two.pdf") is not None
    assert fetch.cached_path("https://host/three.pdf") is not None


def test_url_token_is_stable_and_url_safe():
    token = fetch.url_token("https://host/paper.pdf?x=1&y=2")
    assert token == fetch.url_token("https://host/paper.pdf?x=1&y=2")
    assert token != fetch.url_token("https://host/other.pdf")
    assert len(token) == 24 and token.isalnum()
