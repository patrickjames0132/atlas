"""The Semantic Scholar client (integrations/semantic_scholar.py): node
normalization, batch chunking, 429 backoff, and the traversal/search parsers.

HTTP is faked at ``urllib.request.urlopen`` (for _request itself) or at
``_request`` (for the endpoint parsers) — no network.
"""

from __future__ import annotations

import io
import json
import urllib.error

import pytest
from arxiv_digest.integrations import semantic_scholar as s2


# --- _node normalization -------------------------------------------------------

def test_node_normalizes_rich_paper():
    raw = {
        "paperId": "abc", "externalIds": {"ArXiv": "1706.03762"},
        "title": "Attention", "abstract": "We propose...",
        "tldr": {"model": "v2", "text": "Attention is enough."},
        "year": 2017, "publicationDate": "2017-06-12", "citationCount": 100000,
        "authors": [{"name": "Vaswani"}, {"name": ""}, {"name": "Shazeer"}],
    }
    n = s2._node(raw)
    assert n["id"] == "abc" and n["arxiv_id"] == "1706.03762"
    assert n["tldr"] == "Attention is enough."
    assert n["month"] == 6 and n["pub_date"] == "2017-06-12"
    assert n["authors"] == "Vaswani, Shazeer"  # blanks dropped
    assert n["url"] == "https://arxiv.org/abs/1706.03762"


def test_node_handles_sparse_paper():
    n = s2._node({"paperId": "xyz"})
    assert n["title"] == "(untitled)" and n["arxiv_id"] is None
    assert n["month"] is None and n["authors"] is None
    assert n["url"] == "https://www.semanticscholar.org/paper/xyz"


@pytest.mark.parametrize("pub,month", [
    ("2017-06-12", 6), ("2017-13-01", None), ("2017", None), (None, None), ("2017-0x-01", None),
])
def test_node_month_parsing(pub, month):
    n = s2._node({"paperId": "a", "publicationDate": pub})
    assert n["month"] == month


def test_node_none_for_unresolved():
    assert s2._node(None) is None
    assert s2._node({}) is None
    assert s2._node({"title": "no paperId"}) is None


# --- _request: 429 backoff -----------------------------------------------------

class _FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_request_backs_off_on_429_then_succeeds(monkeypatch):
    attempts = []
    sleeps = []

    def fake_urlopen(req, timeout=None):
        attempts.append(req.full_url)
        if len(attempts) < 3:
            raise urllib.error.HTTPError(req.full_url, 429, "Too Many", {}, None)
        return _FakeResponse(json.dumps({"ok": True}).encode())

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr(s2.time, "sleep", sleeps.append)
    assert s2._request("https://api.test/x") == {"ok": True}
    assert len(attempts) == 3
    assert sleeps == [1, 2]  # exponential backoff between retries


def test_request_gives_up_after_tries(monkeypatch):
    def always_429(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 429, "Too Many", {}, None)

    monkeypatch.setattr("urllib.request.urlopen", always_429)
    monkeypatch.setattr(s2.time, "sleep", lambda s: None)
    with pytest.raises(s2.S2Error, match="HTTP 429"):
        s2._request("https://api.test/x", tries=3)


def test_request_non_429_fails_fast(monkeypatch):
    attempts = []

    def forbidden(req, timeout=None):
        attempts.append(1)
        raise urllib.error.HTTPError(req.full_url, 403, "Forbidden", {}, None)

    monkeypatch.setattr("urllib.request.urlopen", forbidden)
    with pytest.raises(s2.S2Error, match="HTTP 403"):
        s2._request("https://api.test/x")
    assert len(attempts) == 1  # no retry on non-429


def test_request_network_error_wrapped(monkeypatch):
    def unreachable(req, timeout=None):
        raise urllib.error.URLError("no route to host")

    monkeypatch.setattr("urllib.request.urlopen", unreachable)
    with pytest.raises(s2.S2Error, match="no route to host"):
        s2._request("https://api.test/x")


# --- get_papers batching -------------------------------------------------------

def test_get_papers_chunks_batches_and_skips_nulls(monkeypatch):
    bodies = []

    def fake_request(url, method="GET", body=None, tries=4):
        bodies.append(body["ids"])
        # S2 aligns the response list to the input ids; null = unresolved.
        return [{"paperId": pid} if pid != "ARXIV:bad" else None for pid in body["ids"]]

    monkeypatch.setattr(s2, "_request", fake_request)
    ids = [f"id{i}" for i in range(501)] + ["", "ARXIV:bad"]  # falsy dropped, bad unresolved
    out = s2.get_papers(ids)
    assert [len(b) for b in bodies] == [500, 2]  # chunked at the 500-id cap
    assert len(out) == 501 and "ARXIV:bad" not in out
    assert out["id0"]["id"] == "id0"


def test_get_papers_empty_input_no_request(monkeypatch):
    monkeypatch.setattr(s2, "_request", lambda *a, **k: pytest.fail("should not be called"))
    assert s2.get_papers(["", None]) == {}


# --- traversal + search parsers --------------------------------------------------

def test_references_shape_and_influential(monkeypatch):
    def fake_request(url, **kw):
        assert "/references" in url
        return {"data": [
            {"citedPaper": {"paperId": "r1", "title": "Ref"}, "isInfluential": True},
            {"citedPaper": None},  # unresolved — skipped
        ]}

    monkeypatch.setattr(s2, "_request", fake_request)
    out = s2.references("p1", limit=10)
    assert out == [{"node": s2._node({"paperId": "r1", "title": "Ref"}), "influential": True}]


def test_citations_uses_citing_paper_key(monkeypatch):
    monkeypatch.setattr(s2, "_request", lambda url, **kw: {"data": [
        {"citingPaper": {"paperId": "c1"}, "isInfluential": False}]})
    (hit,) = s2.citations("p1", limit=10)
    assert hit["node"]["id"] == "c1" and hit["influential"] is False


def test_recommendations_pool_in_url(monkeypatch):
    urls = []

    def fake_request(url, **kw):
        urls.append(url)
        return {"recommendedPapers": [{"paperId": "s1"}]}

    monkeypatch.setattr(s2, "_request", fake_request)
    (hit,) = s2.recommendations("p1", limit=5)
    assert "from=all-cs" in urls[0]  # the "recent" pool returns nothing for old seeds
    assert hit == {"node": s2._node({"paperId": "s1"})}


@pytest.mark.parametrize("lo,hi,expected", [
    (2016, 2020, "2016-2020"), (2020, None, "2020-"), (None, 2015, "-2015"), (None, None, None),
])
def test_year_range(lo, hi, expected):
    assert s2._year_range(lo, hi) == expected


def test_search_papers_url_carries_year_filter(monkeypatch):
    urls = []

    def fake_request(url, **kw):
        urls.append(url)
        return {"data": [{"paperId": "h1"}]}

    monkeypatch.setattr(s2, "_request", fake_request)
    (hit,) = s2.search_papers("state space models", limit=8, year_from=2024)
    assert "year=2024-" in urls[0] and "state+space+models" in urls[0]
    assert hit["node"]["id"] == "h1"


def test_quote_keeps_prefixes_and_old_style_ids():
    assert s2._quote("ARXIV:1706.03762") == "ARXIV:1706.03762"
    assert s2._quote("ARXIV:hep-th/9901001") == "ARXIV:hep-th/9901001"
