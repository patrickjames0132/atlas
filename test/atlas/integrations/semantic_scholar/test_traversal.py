"""Batch hydration and citation-graph traversal: get_papers/get_paper,
references, citations, recommendations.

client.request is faked directly — no network.
"""

from __future__ import annotations

import datetime

import pytest

from atlas.config import config
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


def test_citation_relations_splits_latest_from_landmark(monkeypatch):
    """The seed-build view splits citers by publication date: recent ones (last
    ~12 months) are `latest`, newest-first; older ones are `landmark`,
    most-cited first. The two partitions are disjoint."""

    def fake_request(url, **kw):
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
    assert [hit["node"]["id"] for hit in latest] == ["fresher", "fresh"]  # newest-first


def test_citation_relations_undated_citer_is_landmark_not_latest(monkeypatch):
    """A citer with no publication date can't be placed in the rolling window,
    so it competes as a historic landmark rather than being guessed into latest."""

    def fake_request(url, **kw):
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


def _offset_of(url: str) -> int:
    import re

    match = re.search(r"offset=(\d+)", url)
    return int(match.group(1)) if match else 0


def test_citations_mega_fetches_one_page_then_mines(monkeypatch):
    """A mega seed fetches exactly ONE newest page (offset 0) and recovers its
    landmarks by mining — the old stratified offset windows are gone."""
    offsets = []

    def fake_request(url, method="GET", body=None, **kw):
        if "/paper/batch" in url:
            return []  # mining harvest — empty, to isolate the fetch behaviour
        offsets.append(_offset_of(url))
        return {"data": [{"citingPaper": {"paperId": "c1", "year": 2026, "citationCount": 5}}]}

    monkeypatch.setattr(client, "request", fake_request)
    traversal.citations("p1", limit=5, total_count=150000)
    assert offsets == [0]  # exactly one page at offset 0 — no offset windows


def test_citations_small_paper_one_page_no_mining(monkeypatch):
    """A modestly-cited seed's page IS its complete citation list, so it fetches
    one page and skips mining entirely."""
    urls = []

    def fake_request(url, method="GET", body=None, **kw):
        urls.append(url)
        return {"data": [{"citingPaper": {"paperId": "c1", "year": 2020, "citationCount": 5}}]}

    monkeypatch.setattr(client, "request", fake_request)
    traversal.citations("p1", limit=5, total_count=300)
    assert [_offset_of(url) for url in urls] == [0]  # one page only
    assert all("/paper/batch" not in url for url in urls)  # complete list — no mining


def test_citations_propagates_a_fetch_outage(monkeypatch):
    """If the newest-page fetch fails, that's a real outage and propagates —
    not silently swallowed."""

    def boom(url, **kw):
        raise client.S2Error("S2 down")

    monkeypatch.setattr(client, "request", boom)
    with pytest.raises(client.S2Error):
        traversal.citations("p1", limit=5, total_count=15000)


def test_citations_mega_mines_and_verifies_landmark_citers(monkeypatch):
    """Past the offset ceiling the reachable windows are all recent-tip, so
    the pool is enriched with landmark citers mined from reachable papers'
    reference lists — kept ONLY when verified to actually cite the seed."""

    def fake_request(url, method="GET", body=None, **kw):
        if "references.title" in url:
            # The harvest: ONE batch call returns every mined source's
            # reference list — the seed itself (skipped), a pre-seed giant
            # (pruned: it can't cite a paper from after its time), and two
            # heavyweight landmark candidates.
            return [
                {"references": [
                    {"paperId": "p1", "citationCount": 150000},
                    {"paperId": "adam", "year": 2014, "citationCount": 190000},
                    {"paperId": "bert", "year": 2019, "citationCount": 90000},
                    {"paperId": "freeloader", "year": 2018, "citationCount": 80000},
                ]},
            ]
        if "/paper/batch" in url:
            # Verification: the pre-seed giant never reaches it; bert's
            # references contain the seed; freeloader's don't — co-appearing
            # in reference lists is not a citation.
            assert body["ids"] == ["bert", "freeloader"]
            return [
                {"references": [{"paperId": "other"}, {"paperId": "p1"}]},
                {"references": [{"paperId": "other"}]},
            ]
        # The reachable citation windows: all recent tip; the surveys are the
        # most-cited entries, so they lead the mining sources.
        offset = _offset_of(url)
        return {"data": [
            {"citingPaper": {"paperId": f"recent{offset}", "year": 2026, "citationCount": 5}},
            {"citingPaper": {"paperId": f"survey{offset}", "year": 2026, "citationCount": 40}},
        ]}

    monkeypatch.setattr(client, "request", fake_request)
    out = traversal.citations("p1", limit=4, total_count=150000, year=2017)
    ids = {hit["node"]["id"] for hit in out}
    assert "bert" in ids and "freeloader" not in ids  # verified in, unverified out
    years = {hit["node"]["year"] for hit in out}
    assert {2019, 2026} <= years  # the mined landmark era AND the frontier
    mined = next(hit for hit in out if hit["node"]["id"] == "bert")
    assert mined["influential"] is False  # unknowable off the /citations endpoint


def test_citations_mega_mining_is_best_effort(monkeypatch):
    """A dead batch pool means mining just bails — the reachable pool still
    serves, and no extra requests chase the lost landmarks."""
    urls = []

    def fake_request(url, method="GET", body=None, **kw):
        urls.append(url)
        if "/paper/batch" in url:
            raise client.S2Error("mining blocked")
        offset = _offset_of(url)
        return {"data": [
            {"citingPaper": {"paperId": f"off{offset}", "year": 2026, "citationCount": 5}}
        ]}

    monkeypatch.setattr(client, "request", fake_request)
    out = traversal.citations("p1", limit=3, total_count=150000)
    assert out  # mining is best-effort; the reachable pool still serves
    assert all(hit["node"]["year"] == 2026 for hit in out)
    # Only the harvest batch was attempted — nothing followed its failure.
    assert len([url for url in urls if "/paper/batch" in url]) == 1


def test_citations_mega_unverifiable_candidates_are_dropped(monkeypatch):
    """When the verification batch is down, NOTHING mined is kept — the
    graph never guesses a citation edge."""

    def fake_request(url, method="GET", body=None, **kw):
        if "references.title" in url:
            # The harvest batch succeeds and finds a landmark candidate...
            return [
                {"references": [{"paperId": "bert", "year": 2019, "citationCount": 90000}]}
            ]
        if "/paper/batch" in url:
            raise client.S2Error("verification down")  # ...but no check can run.
        offset = _offset_of(url)
        return {"data": [
            {"citingPaper": {"paperId": f"off{offset}", "year": 2026, "citationCount": 5}}
        ]}

    monkeypatch.setattr(client, "request", fake_request)
    out = traversal.citations("p1", limit=3, total_count=150000)
    assert all(hit["node"]["id"] != "bert" for hit in out)


def test_cites_seed_chunks_beyond_the_batch_cap(monkeypatch):
    """Verification splits into ≤_BATCH_MAX-id batches, so a candidate budget
    larger than S2's 500-id cap is honoured — results unioned across chunks."""
    chunk_sizes = []

    def fake_request(url, method="GET", body=None, **kw):
        chunk_sizes.append(len(body["ids"]))
        # Every candidate cites the seed (its references contain 'seed').
        return [{"references": [{"paperId": "seed"}]} for _ in body["ids"]]

    monkeypatch.setattr(client, "request", fake_request)
    candidate_ids = [f"c{index}" for index in range(traversal._BATCH_MAX + 30)]
    verified = traversal._cites_seed(candidate_ids, "seed")
    assert chunk_sizes == [traversal._BATCH_MAX, 30]  # two batches, chunked at the cap
    assert len(verified) == traversal._BATCH_MAX + 30  # all verified across both


def test_cites_seed_is_best_effort_per_chunk(monkeypatch):
    """One chunk's batch failing drops only that chunk — the other chunk's
    verified candidates are still kept (a 429 no longer nukes every landmark)."""

    def fake_request(url, method="GET", body=None, **kw):
        if "c0" in body["ids"]:
            raise client.S2Error("first chunk 429")  # first chunk fails
        return [{"references": [{"paperId": "seed"}]} for _ in body["ids"]]

    monkeypatch.setattr(client, "request", fake_request)
    candidate_ids = [f"c{index}" for index in range(traversal._BATCH_MAX + 5)]
    verified = traversal._cites_seed(candidate_ids, "seed")
    assert len(verified) == 5  # only the second (surviving) chunk's candidates


def test_citations_mining_ranks_candidates_by_co_citation_not_raw_citations(monkeypatch):
    """A candidate co-cited by MANY seed-citers beats a globally-huge but
    off-topic giant for a scarce verification slot — so the budget isn't burnt
    on papers that don't cite the seed."""

    def fake_request(url, method="GET", body=None, **kw):
        if "references.title" in url:
            # Two source citers' reference lists: the giant appears in only one,
            # the landmark in both (co-cited) — despite far fewer raw citations.
            return [
                {"references": [
                    {"paperId": "giant", "year": 2019, "citationCount": 200000},
                    {"paperId": "landmark", "year": 2019, "citationCount": 500},
                ]},
                {"references": [{"paperId": "landmark", "year": 2019, "citationCount": 500}]},
            ]
        if "/paper/batch" in url:
            # Only one candidate slot: co-citation ranking must have sent the
            # landmark (freq 2), not the giant (freq 1) — so 'giant' never here.
            assert body["ids"] == ["landmark"]
            return [{"references": [{"paperId": "p1"}]}]
        offset = _offset_of(url)
        return {"data": [
            {"citingPaper": {"paperId": f"src-a{offset}", "year": 2026, "citationCount": 40}},
            {"citingPaper": {"paperId": f"src-b{offset}", "year": 2026, "citationCount": 30}},
        ]}

    monkeypatch.setattr(client, "request", fake_request)
    monkeypatch.setattr(config.graph.citation_mining, "candidates", 1)
    out = traversal.citations("p1", limit=10, total_count=150000, year=2017)
    ids = {hit["node"]["id"] for hit in out}
    assert "landmark" in ids and "giant" not in ids  # co-cited landmark won the slot


def test_citations_mines_whenever_list_overflows_one_page(monkeypatch):
    """Any seed with more citers than one page (`total_count` > the ranking
    pool) mines for landmarks — there's no separate 'reachable by windows'
    tier any more, so a 5000-citer paper mines just like a 150k one."""
    urls = []

    def fake_request(url, method="GET", body=None, **kw):
        urls.append(url)
        if "/paper/batch" in url:
            return []  # harvest returns nothing — we only assert it was attempted
        return {"data": [{"citingPaper": {"paperId": "c1", "year": 2024, "citationCount": 5}}]}

    monkeypatch.setattr(client, "request", fake_request)
    traversal.citations("p1", limit=5, total_count=5000)
    assert any("/paper/batch" in url for url in urls)  # mining ran


def test_recommendations_pool_in_url(monkeypatch):
    urls = []

    def fake_request(url, **kw):
        urls.append(url)
        return {"recommendedPapers": [{"paperId": "s1"}]}

    monkeypatch.setattr(client, "request", fake_request)
    (hit,) = traversal.recommendations("p1", limit=5)
    assert "from=all-cs" in urls[0]  # the "recent" pool returns nothing for old seeds
    assert hit == {"node": nodes.node({"paperId": "s1"})}
