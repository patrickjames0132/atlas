"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
HTTP transport: 429 backoff, error wrapping, and id quoting.

urlopen is faked directly — no network.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

import io
import json
import urllib.error

import pytest

from atlas.integrations.semantic_scholar import client


class _FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


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
    assert client.request("https://api.test/x") == {"ok": True}
    assert len(attempts) == 3
    assert sleeps == [1, 2]  # exponential backoff between retries


def test_request_gives_up_after_tries(monkeypatch):
    def always_429(http_request, timeout=None):
        raise urllib.error.HTTPError(http_request.full_url, 429, "Too Many", {}, None)

    monkeypatch.setattr("urllib.request.urlopen", always_429)
    monkeypatch.setattr(client.time, "sleep", lambda seconds: None)
    with pytest.raises(client.S2Error, match="HTTP 429"):
        client.request("https://api.test/x", tries=3)


def test_request_non_429_fails_fast(monkeypatch):
    attempts = []

    def forbidden(http_request, timeout=None):
        attempts.append(1)
        raise urllib.error.HTTPError(http_request.full_url, 403, "Forbidden", {}, None)

    monkeypatch.setattr("urllib.request.urlopen", forbidden)
    with pytest.raises(client.S2Error, match="HTTP 403"):
        client.request("https://api.test/x")
    assert len(attempts) == 1  # no retry on non-429


def test_request_network_error_wrapped(monkeypatch):
    def unreachable(http_request, timeout=None):
        raise urllib.error.URLError("no route to host")

    monkeypatch.setattr("urllib.request.urlopen", unreachable)
    with pytest.raises(client.S2Error, match="no route to host"):
        client.request("https://api.test/x")


def test_quote_keeps_prefixes_and_old_style_ids():
    assert client.quote("ARXIV:1706.03762") == "ARXIV:1706.03762"
    assert client.quote("ARXIV:hep-th/9901001") == "ARXIV:hep-th/9901001"
