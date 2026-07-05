"""client: the huggingface_hub paper_info wrapper (fetch_paper).

The HfApi handle is faked directly — no network. Covers the happy path and the
404-as-None / non-404-reraise translation that code_links relies on.
"""

from __future__ import annotations

import httpx
import pytest
from huggingface_hub.utils import HfHubHTTPError

from arxiv_digest.integrations.huggingface import client


class _FakeApi:
    """Stand-in for HfApi: returns a canned PaperInfo or raises."""

    def __init__(self, *, result=None, exc=None):
        self._result = result
        self._exc = exc
        self.calls: list[str] = []

    def paper_info(self, arxiv_id):
        self.calls.append(arxiv_id)
        if self._exc is not None:
            raise self._exc
        return self._result


def _http_error(status: int) -> HfHubHTTPError:
    # huggingface_hub 1.x speaks httpx, so its HfHubHTTPError carries an
    # httpx.Response (which needs a request set on it to be well-formed).
    request = httpx.Request("GET", "https://huggingface.co/api/papers/x")
    response = httpx.Response(status_code=status, request=request)
    return HfHubHTTPError(f"HTTP {status}", response=response)


def test_fetch_paper_returns_the_paper_info(monkeypatch):
    sentinel = object()
    monkeypatch.setattr(client, "_api", _FakeApi(result=sentinel))
    assert client.fetch_paper("1706.03762") is sentinel


def test_fetch_paper_returns_none_on_404(monkeypatch):
    monkeypatch.setattr(client, "_api", _FakeApi(exc=_http_error(404)))
    assert client.fetch_paper("0000.00000") is None


def test_fetch_paper_reraises_non_404(monkeypatch):
    monkeypatch.setattr(client, "_api", _FakeApi(exc=_http_error(500)))
    with pytest.raises(HfHubHTTPError):
        client.fetch_paper("1706.03762")
