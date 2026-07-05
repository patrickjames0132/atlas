"""client: the single HF Papers HTTP fetch (fetch_paper).

urlopen is faked directly — no network. Covers JSON decode, 404-as-None,
non-404 reraise, and slash-id path encoding.
"""

from __future__ import annotations

import io
import json
import urllib.error

import pytest

from arxiv_digest.integrations.huggingface import client


class _FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_fetch_paper_returns_parsed_json(monkeypatch):
    body = json.dumps({"id": "1706.03762", "upvotes": 127}).encode()
    monkeypatch.setattr(
        "urllib.request.urlopen", lambda request, timeout=None: _FakeResponse(body)
    )
    assert client.fetch_paper("1706.03762") == {"id": "1706.03762", "upvotes": 127}


def test_fetch_paper_returns_none_when_body_is_not_an_object(monkeypatch):
    # HF should return an object; a bare array/string is treated as "no record".
    monkeypatch.setattr(
        "urllib.request.urlopen", lambda request, timeout=None: _FakeResponse(b"[1, 2, 3]")
    )
    assert client.fetch_paper("1706.03762") is None


def test_fetch_paper_returns_none_on_404(monkeypatch):
    def raise_404(request, timeout=None):
        raise urllib.error.HTTPError("url", 404, "Not Found", {}, None)

    monkeypatch.setattr("urllib.request.urlopen", raise_404)
    assert client.fetch_paper("2301.00001") is None


def test_fetch_paper_reraises_non_404(monkeypatch):
    def raise_500(request, timeout=None):
        raise urllib.error.HTTPError("url", 500, "Server Error", {}, None)

    monkeypatch.setattr("urllib.request.urlopen", raise_500)
    with pytest.raises(urllib.error.HTTPError):
        client.fetch_paper("2301.00001")


def test_fetch_paper_path_encodes_a_slash_id(monkeypatch):
    urls = []

    def fake_urlopen(request, timeout=None):
        urls.append(request.full_url)
        return _FakeResponse(b"{}")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    client.fetch_paper("math/0211159")
    # safe="" encodes the slash so it stays inside the {arxiv_id} path segment.
    assert urls[0] == f"{client.BASE_URL}/api/papers/math%2F0211159"
