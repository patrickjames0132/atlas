"""Seed discovery (services/search.py): live S2 search (mocked) and the
cache-first local search (real SQLite on the per-test temp DB).
"""

from __future__ import annotations

from arxiv_digest.services.search import discovery
from arxiv_digest.storage import cache

# --- live_search (S2, mocked) ----------------------------------------------------


def test_live_search_unwraps_nodes_and_forwards_filters(monkeypatch):
    captured = {}

    def fake_search_papers(query, limit, year_from=None, year_to=None, fields_of_study=None):
        captured.update(
            query=query, limit=limit, year_from=year_from,
            year_to=year_to, fields_of_study=fields_of_study,
        )
        return [{"node": {"id": "p1", "title": "A"}}, {"node": {"id": "p2", "title": "B"}}]

    monkeypatch.setattr(discovery.s2, "search_papers", fake_search_papers)
    out = discovery.live_search(
        "ssm", limit=5, year_from=2020, fields_of_study=["Computer Science"]
    )
    assert out == [{"id": "p1", "title": "A"}, {"id": "p2", "title": "B"}]  # unwrapped
    assert captured == {
        "query": "ssm", "limit": 5, "year_from": 2020,
        "year_to": None, "fields_of_study": ["Computer Science"],
    }


def test_live_search_blank_short_circuits_without_hitting_s2(monkeypatch):
    def explode(*args, **kwargs):
        raise AssertionError("S2 should not be called for a blank query")

    monkeypatch.setattr(discovery.s2, "search_papers", explode)
    assert discovery.live_search("   ") == []


def test_live_search_routes_query_through_the_expansion_seam(monkeypatch):
    seen = {}

    def fake_expand(query):
        seen["query"] = query
        return "EXPANDED"

    monkeypatch.setattr(discovery, "_expand_query", fake_expand)
    monkeypatch.setattr(discovery.s2, "search_papers", lambda query, **kw: [{"node": {"id": query}}])
    out = discovery.live_search("dqn")
    assert seen["query"] == "dqn"          # the raw query goes through the seam
    assert out == [{"id": "EXPANDED"}]     # the expanded query is what reaches S2


# --- local_search (cache-first) --------------------------------------------------


def _node(paper_id: str, title: str, **extra) -> dict:
    return {
        "id": paper_id, "arxiv_id": None, "title": title, "authors": None,
        "year": 2020, "citation_count": 1, "url": "u", "is_seed": False, **extra,
    }


def _snapshot(seed: dict, nodes: list[dict]) -> dict:
    return {"seed": seed, "nodes": nodes, "edges": [], "counts": {}}


def test_local_search_matches_tokens_and_flags_fresh_graph():
    cache.set("graph:1706.03762", _snapshot(
        {"arxiv_id": "1706.03762", "id": "seedA", "title": "Attention Is All You Need"},
        [
            _node("seedA", "Attention Is All You Need", is_seed=True,
                  authors="Vaswani", arxiv_id="1706.03762", citation_count=1000),
            _node("nB", "Some Other Paper", authors="Smith"),
        ],
    ))
    out = discovery.local_search("attention")
    ids = [hit["id"] for hit in out]
    assert ids == ["seedA"]  # only the token-matching paper
    assert out[0]["has_graph"] is True  # a fresh snapshot exists with it as seed


def test_local_search_dedupes_keeping_the_richer_record():
    # The same paper as a bare neighbor in one snapshot and hydrated in another.
    cache.set("graph:s1", _snapshot(
        {"id": "s1", "title": "Seed One"}, [_node("shared", "Shared Paper Title")]))
    cache.set("graph:s2", _snapshot(
        {"id": "s2b", "title": "Seed Two"},
        [_node("shared", "Shared Paper Title", authors="Rich Author")]))
    (hit,) = discovery.local_search("shared paper")
    assert hit["id"] == "shared" and hit["authors"] == "Rich Author"


def test_local_search_year_filter_excludes_out_of_range_and_undated():
    cache.set("graph:y", _snapshot(
        {"id": "y", "title": "Y"},
        [
            _node("old", "Deep Learning 2010", year=2010, authors="A"),
            _node("new", "Deep Learning 2022", year=2022, authors="B"),
            _node("undated", "Deep Learning Undated", year=None, authors="C"),
        ],
    ))
    out = discovery.local_search("deep learning", year_from=2015)
    assert {hit["id"] for hit in out} == {"new"}  # 2010 too old, undated excluded under a bound


def test_local_search_ranks_phrase_title_then_seed_then_citations():
    cache.set("graph:r", _snapshot(
        {"id": "seedX", "title": "Neural Networks"},
        [
            _node("seedX", "Neural Networks", is_seed=True, authors="S", citation_count=5),
            _node("exact", "Neural Networks Revisited", authors="E", citation_count=100),
            _node("partial", "Networks of Neural Cells", authors="P", citation_count=50),
        ],
    ))
    order = [hit["id"] for hit in discovery.local_search("neural networks")]
    # phrase-in-title (seedX, exact) beat non-phrase (partial); among the two,
    # the explored seed beats the plain hit.
    assert order.index("seedX") < order.index("exact") < order.index("partial")


def test_local_search_blank_returns_empty():
    assert discovery.local_search("") == []
    assert discovery.local_search("   ") == []
