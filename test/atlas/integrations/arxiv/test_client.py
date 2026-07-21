"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
client: the shared ar5iv HTTP fetch, image proxy fetch, and host allowlist.

urlopen is faked directly — no network.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

import io
import urllib.error

import pytest

from atlas.integrations.arxiv import client


class _FakeResponse(io.BytesIO):
    def __init__(self, body: bytes, content_type: str | None = None, charset: str | None = None):
        super().__init__(body)
        self.headers = _FakeHeaders(content_type, charset)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _FakeHeaders:
    def __init__(self, content_type: str | None, charset: str | None):
        self._content_type = content_type
        self._charset = charset

    def get_content_charset(self):
        return self._charset

    def get_content_type(self):
        return self._content_type


def test_fetch_html_returns_decoded_body(monkeypatch):
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda request, timeout=None: _FakeResponse("<p>hello</p>".encode(), charset="utf-8"),
    )
    assert client.fetch_html("2406.12345") == "<p>hello</p>"


def test_fetch_html_returns_none_on_404(monkeypatch):
    def raise_404(request, timeout=None):
        raise urllib.error.HTTPError("url", 404, "Not Found", {}, None)

    monkeypatch.setattr("urllib.request.urlopen", raise_404)
    assert client.fetch_html("2406.12345") is None


def test_fetch_html_reraises_non_404(monkeypatch):
    def raise_500(request, timeout=None):
        raise urllib.error.HTTPError("url", 500, "Server Error", {}, None)

    monkeypatch.setattr("urllib.request.urlopen", raise_500)
    with pytest.raises(urllib.error.HTTPError):
        client.fetch_html("2406.12345")


def test_fetch_html_builds_the_ar5iv_url(monkeypatch):
    urls = []

    def fake_urlopen(request, timeout=None):
        urls.append(request.full_url)
        return _FakeResponse(b"ok", charset="utf-8")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    client.fetch_html("hep-th/9901001")
    # urllib.parse.quote's default safe="/" keeps old-style ids' slash literal.
    assert urls[0] == f"{client.BASE_URL}/html/hep-th/9901001"


@pytest.mark.parametrize(
    "url,expected",
    [
        (f"https://{client.AR5IV_HOST}/html/2406.12345", True),
        (f"http://{client.AR5IV_HOST}/html/2406.12345", False),  # not https
        ("https://evil.example.com/html/2406.12345", False),  # wrong host
        ("not a url at all: 🚫", False),  # unparseable
    ],
)
def test_is_ar5iv_url(url, expected):
    assert client.is_ar5iv_url(url) is expected


def test_fetch_image_returns_bytes_and_content_type(monkeypatch):
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda request, timeout=None: _FakeResponse(b"\x89PNG", content_type="image/jpeg"),
    )
    body, content_type = client.fetch_image(f"https://{client.AR5IV_HOST}/fig1.jpg")
    assert body == b"\x89PNG"
    assert content_type == "image/jpeg"


def test_fetch_image_defaults_content_type(monkeypatch):
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda request, timeout=None: _FakeResponse(b"\x89PNG", content_type=None),
    )
    _body, content_type = client.fetch_image(f"https://{client.AR5IV_HOST}/fig1.png")
    assert content_type == "image/png"
