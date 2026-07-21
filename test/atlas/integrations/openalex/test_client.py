"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
HTTP transport & URL building: credential params, 429/5xx backoff, error
wrapping, and the free id-lookup path.

urlopen is faked directly — no network.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

import io
import json
import urllib.error
import urllib.parse

import pytest

from atlas.config import config
from atlas.integrations.openalex import client


class _FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _query(url):
    return {key: values[0] for key, values in
            urllib.parse.parse_qs(urllib.parse.urlparse(url).query).items()}


def test_works_url_adds_mailto_and_api_key(monkeypatch):
    monkeypatch.setattr(config.providers.openalex, "mailto", "me@x.org")
    monkeypatch.setattr(config.providers.openalex, "api_key", "SECRET")
    params = _query(client.works_url({"filter": "cites:W1", "sort": "cited_by_count:desc"}))
    assert params["mailto"] == "me@x.org"
    assert params["api_key"] == "SECRET"
    assert params["filter"] == "cites:W1"


def test_works_url_omits_empty_credentials(monkeypatch):
    monkeypatch.setattr(config.providers.openalex, "mailto", "")
    monkeypatch.setattr(config.providers.openalex, "api_key", "")
    params = _query(client.works_url({"filter": "cites:W1"}))
    assert "mailto" not in params and "api_key" not in params


def test_entity_url_keeps_doi_colon_and_slash(monkeypatch):
    monkeypatch.setattr(config.providers.openalex, "mailto", "")
    monkeypatch.setattr(config.providers.openalex, "api_key", "")
    url = client.entity_url("doi:10.1038/248030a0", {"select": "id"})
    assert "/works/doi:10.1038/248030a0?" in url


def test_request_backs_off_on_429_then_succeeds(monkeypatch):
    attempts = []
    sleeps = []

    def fake_urlopen(http_request, timeout=None):
        attempts.append(http_request.full_url)
        if len(attempts) < 3:
            raise urllib.error.HTTPError(http_request.full_url, 429, "Too Many", {}, None)
        return _FakeResponse(json.dumps({"ok": True}).encode())

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr(client.time, "sleep", sleeps.append)
    assert client.request("https://api.openalex.org/works?x=1") == {"ok": True}
    assert len(attempts) == 3
    assert sleeps == [1, 2]


def test_request_retries_on_5xx(monkeypatch):
    attempts = []

    def fake_urlopen(http_request, timeout=None):
        attempts.append(1)
        if len(attempts) < 2:
            raise urllib.error.HTTPError(http_request.full_url, 503, "Unavailable", {}, None)
        return _FakeResponse(json.dumps({"ok": True}).encode())

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr(client.time, "sleep", lambda seconds: None)
    assert client.request("https://api.openalex.org/works?x=1") == {"ok": True}
    assert len(attempts) == 2


def test_request_400_fails_fast_and_carries_status(monkeypatch):
    attempts = []

    def bad_request(http_request, timeout=None):
        attempts.append(1)
        raise urllib.error.HTTPError(http_request.full_url, 400, "Bad Request", {}, None)

    monkeypatch.setattr("urllib.request.urlopen", bad_request)
    with pytest.raises(client.OpenAlexError, match="HTTP 400") as caught:
        client.request("https://api.openalex.org/works?x=1")
    assert caught.value.status == 400
    assert len(attempts) == 1  # 400 is not retryable


def test_request_404_status_preserved_for_entity_fallback(monkeypatch):
    def not_found(http_request, timeout=None):
        raise urllib.error.HTTPError(http_request.full_url, 404, "Not Found", {}, None)

    monkeypatch.setattr("urllib.request.urlopen", not_found)
    with pytest.raises(client.OpenAlexError) as caught:
        client.request("https://api.openalex.org/works/doi:x")
    assert caught.value.status == 404


def test_request_network_error_wrapped(monkeypatch):
    def unreachable(http_request, timeout=None):
        raise urllib.error.URLError("no route to host")

    monkeypatch.setattr("urllib.request.urlopen", unreachable)
    with pytest.raises(client.OpenAlexError, match="no route to host"):
        client.request("https://api.openalex.org/works?x=1")
