"""Batch hydration and citation-graph traversal: get_papers/get_paper,
references, citations, recommendations.

client.request is faked directly — no network.
"""

from __future__ import annotations

import datetime

import pytest

from atlas.integrations.semantic_scholar import client, nodes, traversal


def _iso(days_ago: int) -> str:
    """An ISO date ``days_ago`` before today — for placing a citer inside or
    outside the rolling 'latest' window without hardcoding a calendar date."""
    return (datetime.date.today() - datetime.timedelta(days=days_ago)).isoformat()


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
    monkeypatch.setattr(client, "request", lambda *args, **kwargs: pytest.fail("should not be called"))
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
    highest-citation-count hits (here within one year bucket), not whatever
    S2 lists first."""

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


def test_citation_relations_splits_latest_from_landmark(monkeypatch):
    """The seed-build view splits citers by publication date: recent ones (last
    ~12 months) are `latest`, shipped oldest-first (the reveal slider walks
    toward the present); older ones are `landmark`, most-cited first. The two
    partitions are disjoint."""

    def fake_request(url, **kw):
        if _offset_of(url):
            return {"data": []}  # one page is the whole list here
        return {
            "data": [
                {"citingPaper": {"paperId": "fresh", "citationCount": 2, "publicationDate": _iso(40)}},
                {"citingPaper": {"paperId": "fresher", "citationCount": 1, "publicationDate": _iso(5)}},
                {"citingPaper": {"paperId": "old-giant", "citationCount": 5000, "publicationDate": _iso(2000)}},
                {"citingPaper": {"paperId": "old-mid", "citationCount": 40, "publicationDate": _iso(1500)}},
            ]
        }

    monkeypatch.setattr(client, "request", fake_request)
    landmark, latest = traversal.citation_relations("p1", landmark_limit=10, latest_limit=10)
    assert [hit["node"]["id"] for hit in landmark] == ["old-giant", "old-mid"]  # most-cited first
    assert [hit["node"]["id"] for hit in latest] == ["fresh", "fresher"]  # oldest-first


def test_citation_relations_undated_citer_is_landmark_not_latest(monkeypatch):
    """A citer with no publication date can't be placed in the rolling window,
    so it competes as a historic landmark rather than being guessed into latest."""

    def fake_request(url, **kw):
        if _offset_of(url):
            return {"data": []}
        return {
            "data": [
                {"citingPaper": {"paperId": "undated", "citationCount": 9999}},
                {"citingPaper": {"paperId": "recent", "citationCount": 1, "publicationDate": _iso(10)}},
            ]
        }

    monkeypatch.setattr(client, "request", fake_request)
    landmark, latest = traversal.citation_relations("p1", landmark_limit=10, latest_limit=10)
    assert [hit["node"]["id"] for hit in landmark] == ["undated"]
    assert [hit["node"]["id"] for hit in latest] == ["recent"]


def test_citation_relations_respects_each_limit(monkeypatch):
    """landmark_limit and latest_limit trim their partitions independently."""

    def fake_request(url, **kw):
        if _offset_of(url):
            return {"data": []}
        return {
            "data": [
                {"citingPaper": {"paperId": f"old{index}", "citationCount": 100 - index,
                                 "publicationDate": _iso(1000 + index)}}
                for index in range(5)
            ] + [
                {"citingPaper": {"paperId": f"new{index}", "citationCount": 1,
                                 "publicationDate": _iso(index + 1)}}
                for index in range(5)
            ]
        }

    monkeypatch.setattr(client, "request", fake_request)
    landmark, latest = traversal.citation_relations("p1", landmark_limit=2, latest_limit=3)
    assert len(landmark) == 2 and len(latest) == 3


def test_citation_relations_none_limit_ships_everything(monkeypatch):
    """A null config limit (unbounded) ships the whole ranked pool for that
    relation — so the frontend slider can max out to the paper's full count."""

    def fake_request(url, **kw):
        if _offset_of(url):
            return {"data": []}
        return {
            "data": [
                {"citingPaper": {"paperId": f"old{index}", "citationCount": 100 - index,
                                 "publicationDate": _iso(1000 + index)}}
                for index in range(6)
            ] + [
                {"citingPaper": {"paperId": f"new{index}", "citationCount": 1,
                                 "publicationDate": _iso(index + 1)}}
                for index in range(4)
            ]
        }

    monkeypatch.setattr(client, "request", fake_request)
    landmark, latest = traversal.citation_relations("p1", landmark_limit=None, latest_limit=None)
    assert len(landmark) == 6 and len(latest) == 4  # every citer, uncapped


def test_references_none_limit_returns_all_fetched(monkeypatch):
    """A null ref_limit returns the whole fetched (ranked) reference page."""

    def fake_request(url, **kw):
        return {"data": [{"citedPaper": {"paperId": f"r{index}", "citationCount": index}}
                         for index in range(7)]}

    monkeypatch.setattr(client, "request", fake_request)
    assert len(traversal.references("p1", None)) == 7


def test_recommendations_none_limit_requests_s2_max(monkeypatch):
    """A null similar_limit asks S2 for its max recommendations page (500)."""
    seen = {}

    def fake_request(url, **kw):
        seen["url"] = url
        return {"recommendedPapers": []}

    monkeypatch.setattr(client, "request", fake_request)
    traversal.recommendations("p1", None)
    assert "limit=500" in seen["url"]


def _offset_of(url: str) -> int:
    import re

    match = re.search(r"offset=(\d+)", url)
    return int(match.group(1)) if match else 0


def test_citation_relations_pages_until_the_window_boundary(monkeypatch):
    """The fallback build pages newest-first while pages hold in-window citers
    and stops at the first page fully past the window — so `latest` spans
    multiple pages and the boundary page's older citers become landmarks."""
    seen_offsets = []

    def fake_request(url, method="GET", body=None, **kw):
        offset = _offset_of(url)
        seen_offsets.append(offset)
        if offset == 0:
            return {"data": [{"citingPaper": {"paperId": "new0", "citationCount": 1,
                                              "publicationDate": _iso(10)}}]}
        if offset == 1000:
            return {"data": [{"citingPaper": {"paperId": "new1", "citationCount": 1,
                                              "publicationDate": _iso(200)}}]}
        # offset 2000: all older than the 12-month window → boundary crossed.
        return {"data": [{"citingPaper": {"paperId": "old", "citationCount": 500,
                                          "publicationDate": _iso(3000)}}]}

    monkeypatch.setattr(client, "request", fake_request)
    landmark, latest = traversal.citation_relations("p1", landmark_limit=10, latest_limit=10)
    assert seen_offsets == [0, 1000, 2000]  # paged through the boundary page, then stopped
    assert {hit["node"]["id"] for hit in latest} == {"new0", "new1"}  # both in-window pages
    assert "old" in {hit["node"]["id"] for hit in landmark}  # boundary page → landmark


def test_citations_expansion_fetches_one_newest_page(monkeypatch):
    """The single-relation expansion view fetches exactly ONE newest page
    (offset 0) — the recent tip, fast; no deep paging, no mining (retired)."""
    offsets = []

    def fake_request(url, method="GET", body=None, **kw):
        offsets.append(_offset_of(url))
        return {"data": [{"citingPaper": {"paperId": "c1", "year": 2026, "citationCount": 5}}]}

    monkeypatch.setattr(client, "request", fake_request)
    traversal.citations("p1", limit=5)
    assert offsets == [0]  # exactly one page at offset 0


def test_citations_propagates_a_fetch_outage(monkeypatch):
    """If the newest-page fetch fails, that's a real outage and propagates —
    not silently swallowed."""

    def boom(url, **kw):
        raise client.S2Error("S2 down")

    monkeypatch.setattr(client, "request", boom)
    with pytest.raises(client.S2Error):
        traversal.citations("p1", limit=5)


def test_recommendations_pool_in_url(monkeypatch):
    urls = []

    def fake_request(url, **kw):
        urls.append(url)
        return {"recommendedPapers": [{"paperId": "s1"}]}

    monkeypatch.setattr(client, "request", fake_request)
    (hit,) = traversal.recommendations("p1", limit=5)
    assert "from=all-cs" in urls[0]  # the "recent" pool returns nothing for old seeds
    assert hit == {"node": nodes.node({"paperId": "s1"})}
