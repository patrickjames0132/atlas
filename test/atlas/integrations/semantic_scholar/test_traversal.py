"""Batch hydration and citation-graph traversal: get_papers/get_paper,
references, citations, recommendations.

client.request is faked directly — no network.
"""

from __future__ import annotations

import pytest

from atlas.integrations.semantic_scholar import client, nodes, traversal


def test_get_papers_chunks_batches_and_skips_nulls(monkeypatch):
    bodies = []

    def fake_request(url, method="GET", body=None, tries=4):
        bodies.append(body["ids"])
        # S2 aligns the response list to the input ids; null = unresolved.
        return [{"paperId": pid} if pid != "ARXIV:bad" else None for pid in body["ids"]]

    monkeypatch.setattr(client, "request", fake_request)
    ids = [f"id{index}" for index in range(501)] + ["", "ARXIV:bad"]  # falsy dropped, bad unresolved
    out = traversal.get_papers(ids)
    assert [len(body) for body in bodies] == [500, 2]  # chunked at the 500-id cap
    assert len(out) == 501 and "ARXIV:bad" not in out
    assert out["id0"]["id"] == "id0"


def test_get_papers_empty_input_no_request(monkeypatch):
    monkeypatch.setattr(client, "request", lambda *a, **k: pytest.fail("should not be called"))
    assert traversal.get_papers(["", None]) == {}


def test_references_shape_and_influential(monkeypatch):
    def fake_request(url, **kw):
        assert "/references" in url
        return {
            "data": [
                {"citedPaper": {"paperId": "r1", "title": "Ref"}, "isInfluential": True},
                {"citedPaper": None},  # unresolved — skipped
            ]
        }

    monkeypatch.setattr(client, "request", fake_request)
    out = traversal.references("p1", limit=10)
    assert out == [{"node": nodes.node({"paperId": "r1", "title": "Ref"}), "influential": True}]


def test_citations_uses_citing_paper_key(monkeypatch):
    monkeypatch.setattr(
        client,
        "request",
        lambda url, **kw: {"data": [{"citingPaper": {"paperId": "c1"}, "isInfluential": False}]},
    )
    (hit,) = traversal.citations("p1", limit=10)
    assert hit["node"]["id"] == "c1" and hit["influential"] is False


def test_citations_ranked_by_citation_count_not_s2_order(monkeypatch):
    """S2's default order skews toward the most recently published citing
    paper, not the most cited — so a small `limit` must keep the
    highest-citation-count hits, not whatever S2 lists first."""

    def fake_request(url, **kw):
        assert "limit=1000" in url  # over-fetches the ranking pool regardless of `limit`
        return {
            "data": [
                {"citingPaper": {"paperId": "recent", "citationCount": 0}},
                {"citingPaper": {"paperId": "famous", "citationCount": 5000}},
                {"citingPaper": {"paperId": "mid", "citationCount": 40}},
            ]
        }

    monkeypatch.setattr(client, "request", fake_request)
    out = traversal.citations("p1", limit=2)
    assert [hit["node"]["id"] for hit in out] == ["famous", "mid"]  # top 2 by citation count


def test_recommendations_pool_in_url(monkeypatch):
    urls = []

    def fake_request(url, **kw):
        urls.append(url)
        return {"recommendedPapers": [{"paperId": "s1"}]}

    monkeypatch.setattr(client, "request", fake_request)
    (hit,) = traversal.recommendations("p1", limit=5)
    assert "from=all-cs" in urls[0]  # the "recent" pool returns nothing for old seeds
    assert hit == {"node": nodes.node({"paperId": "s1"})}
