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


def test_citations_even_by_year_spreads_across_years(monkeypatch):
    """The selection buckets by year and round-robins, so the budget spreads
    across the timeline instead of clumping in the busiest years."""

    def fake_request(url, **kw):
        return {
            "data": [
                # 2020 is the busy year (three highly-cited papers); influence
                # ranking alone would take all three and ignore 2018/2019.
                {"citingPaper": {"paperId": "y20-a", "year": 2020, "citationCount": 900}},
                {"citingPaper": {"paperId": "y20-b", "year": 2020, "citationCount": 800}},
                {"citingPaper": {"paperId": "y20-c", "year": 2020, "citationCount": 700}},
                {"citingPaper": {"paperId": "y18", "year": 2018, "citationCount": 50}},
                {"citingPaper": {"paperId": "y19", "year": 2019, "citationCount": 60}},
            ]
        }

    monkeypatch.setattr(client, "request", fake_request)
    out = traversal.citations("p1", limit=3)
    # One per year, oldest-first, most-cited within each — not the top-3 of 2020.
    assert [hit["node"]["id"] for hit in out] == ["y18", "y19", "y20-a"]


def test_citations_even_by_year_fills_dense_years_after_first_round(monkeypatch):
    """Once every year has contributed one paper, the remaining budget fills
    the denser years by influence."""

    def fake_request(url, **kw):
        return {
            "data": [
                {"citingPaper": {"paperId": "y20-a", "year": 2020, "citationCount": 900}},
                {"citingPaper": {"paperId": "y20-b", "year": 2020, "citationCount": 800}},
                {"citingPaper": {"paperId": "y18", "year": 2018, "citationCount": 50}},
            ]
        }

    monkeypatch.setattr(client, "request", fake_request)
    out = traversal.citations("p1", limit=3)
    # Round 1: y18, y20-a (one per year). Round 2: y20-b (2020's next best).
    assert [hit["node"]["id"] for hit in out] == ["y18", "y20-a", "y20-b"]


def test_citations_even_by_year_undated_papers_sort_last(monkeypatch):
    def fake_request(url, **kw):
        return {
            "data": [
                {"citingPaper": {"paperId": "dated", "year": 2019, "citationCount": 5}},
                {"citingPaper": {"paperId": "undated", "year": None, "citationCount": 9999}},
            ]
        }

    monkeypatch.setattr(client, "request", fake_request)
    out = traversal.citations("p1", limit=2)
    assert [hit["node"]["id"] for hit in out] == ["dated", "undated"]  # undated last despite cites


def _offset_of(url: str) -> int:
    import re

    match = re.search(r"offset=(\d+)", url)
    return int(match.group(1)) if match else 0


def test_citations_even_stratifies_when_citations_overflow_the_pool(monkeypatch):
    """A mega-cited seed's pool is sampled across several offset windows
    (newest -> oldest) so the even spread can reach older descendants, not
    just S2's recent tip at offset 0."""
    seen_offsets = []

    def fake_request(url, **kw):
        offset = _offset_of(url)
        seen_offsets.append(offset)
        # Deeper offsets = older citing papers (S2 lists newest-first).
        year = 2026 - offset // 1000
        return {
            "data": [
                {"citingPaper": {"paperId": f"off{offset}-{index}", "year": year,
                                 "citationCount": 10}}
                for index in range(3)
            ]
        }

    monkeypatch.setattr(client, "request", fake_request)
    out = traversal.citations("p1", limit=5, total_count=15000)
    # Sampled multiple windows, starting at the newest (offset 0) and reaching deep.
    assert seen_offsets[0] == 0 and len(seen_offsets) >= 3 and max(seen_offsets) > 1000
    # The pool spanned several eras, so the selection isn't all one year.
    assert len({hit["node"]["year"] for hit in out}) >= 3


def test_citations_even_single_page_when_within_the_pool(monkeypatch):
    """A modestly-cited seed (citations fit in one page) skips stratification —
    one request at offset 0."""
    offsets = []

    def fake_request(url, **kw):
        offsets.append(_offset_of(url))
        return {"data": [{"citingPaper": {"paperId": "c1", "year": 2020, "citationCount": 5}}]}

    monkeypatch.setattr(client, "request", fake_request)
    traversal.citations("p1", limit=5, total_count=300)
    assert offsets == [0]  # one page only


def test_citations_even_skips_offset_windows_s2_rejects(monkeypatch):
    """A too-deep offset (past S2's ceiling / the list end) is skipped, not
    fatal — the pool degrades to the windows that resolved."""

    def fake_request(url, **kw):
        offset = _offset_of(url)
        if offset > 5000:
            raise client.S2Error("offset too large", status=400)
        return {"data": [{"citingPaper": {"paperId": f"off{offset}", "year": 2026 - offset // 1000,
                                          "citationCount": 5}}]}

    monkeypatch.setattr(client, "request", fake_request)
    out = traversal.citations("p1", limit=5, total_count=15000)
    assert out  # reachable windows still produced a pool, no crash


def test_citations_even_propagates_a_newest_window_outage(monkeypatch):
    """If even the newest window (offset 0) fails, that's a real outage and
    propagates — not silently swallowed."""

    def boom(url, **kw):
        raise client.S2Error("S2 down")

    monkeypatch.setattr(client, "request", boom)
    with pytest.raises(client.S2Error):
        traversal.citations("p1", limit=5, total_count=15000)


def test_recommendations_pool_in_url(monkeypatch):
    urls = []

    def fake_request(url, **kw):
        urls.append(url)
        return {"recommendedPapers": [{"paperId": "s1"}]}

    monkeypatch.setattr(client, "request", fake_request)
    (hit,) = traversal.recommendations("p1", limit=5)
    assert "from=all-cs" in urls[0]  # the "recent" pool returns nothing for old seeds
    assert hit == {"node": nodes.node({"paperId": "s1"})}
