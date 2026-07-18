"""Seed discovery (services/search.py): live S2 search (mocked) and the
cache-first local search (real SQLite on the per-test temp DB).
"""

from __future__ import annotations

from atlas.services.search import discovery
from atlas.storage import cache

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


def analysis(expanded: str, titles: list[str] | None = None):
    return discovery.query_analyst.Expansion(
        expanded_query=expanded, known_titles=titles or []
    )


def test_live_search_routes_query_through_the_analysis_seam(monkeypatch):
    seen = {}

    def fake_analyze(query):
        seen["query"] = query
        return analysis("EXPANDED")

    monkeypatch.setattr(discovery, "_analyze", fake_analyze)
    monkeypatch.setattr(discovery.s2, "search_papers", lambda query, **kw: [{"node": {"id": query}}])
    out = discovery.live_search("dqn")
    assert seen["query"] == "dqn"          # the raw query goes through the seam
    assert out == [{"id": "EXPANDED"}]     # the expanded query is what reaches S2


def test_the_seam_delegates_to_the_query_analyst(monkeypatch):
    monkeypatch.setattr(
        discovery.query_analyst, "analyze", lambda query: analysis(query + " deep q-network")
    )
    assert discovery._analyze("dqn").expanded_query == "dqn deep q-network"


def test_analyst_off_skips_the_llm_and_searches_the_words_as_typed(monkeypatch):
    def explode(*args, **kwargs):
        raise AssertionError("analyst=False must not reach the analyst or title match")

    monkeypatch.setattr(discovery, "_analyze", explode)
    monkeypatch.setattr(discovery.s2, "match_title", explode)
    monkeypatch.setattr(
        discovery.s2, "search_papers", lambda query, **kw: [{"node": {"id": query}}]
    )
    out = discovery.live_search("dqn", analyst=False)
    assert out == [{"id": "dqn"}]  # the raw query reached S2 untouched


def test_analyst_off_openalex_branch_also_skips_the_llm(monkeypatch):
    def explode(*args, **kwargs):
        raise AssertionError("analyst=False must not reach the analyst")

    monkeypatch.setattr(discovery, "_analyze", explode)
    monkeypatch.setattr(
        discovery.openalex, "search_papers", lambda query, **kw: [{"id": query}]
    )
    assert discovery.live_search("gnn", provider="openalex", analyst=False) == [{"id": "gnn"}]


def test_analyst_on_and_off_are_cached_separately(monkeypatch):
    """A raw search and an expanded search return different results, so
    neither may be served from the other's cache entry."""
    monkeypatch.setattr(discovery, "_analyze", lambda query: analysis("EXPANDED"))
    monkeypatch.setattr(
        discovery.s2, "search_papers", lambda query, **kw: [{"node": {"id": query}}]
    )
    expanded = discovery.live_search("dqn")
    raw = discovery.live_search("dqn", analyst=False)
    assert [node["id"] for node in expanded] == ["EXPANDED"]
    assert [node["id"] for node in raw] == ["dqn"]  # not the cached expanded result


def test_verified_titles_lead_results_and_dedupe_against_lexical(monkeypatch):
    monkeypatch.setattr(
        discovery, "_analyze",
        lambda query: analysis("dqn deep q-network", ["Playing Atari", "Ghost Paper"]),
    )
    matches = {"Playing Atari": {"id": "atari01", "title": "Playing Atari"}}
    monkeypatch.setattr(discovery.s2, "match_title", lambda title: matches.get(title))
    monkeypatch.setattr(
        discovery.s2, "search_papers",
        lambda query, **kw: [{"node": {"id": "atari01", "title": "Playing Atari"}},
                             {"node": {"id": "other02", "title": "Other"}}],
    )
    out = discovery.live_search("dqn")
    # The verified paper leads; its lexical duplicate is dropped; the
    # unverifiable "Ghost Paper" produced nothing (and broke nothing).
    assert [node["id"] for node in out] == ["atari01", "other02"]


def test_repeat_searches_are_served_from_the_cache(monkeypatch):
    calls = {"analyze": 0, "s2": 0}

    def fake_analyze(query):
        calls["analyze"] += 1
        return analysis("dqn deep q-network")

    def fake_search(query, **kw):
        calls["s2"] += 1
        return [{"node": {"id": "p1", "title": "Playing Atari"}}]

    monkeypatch.setattr(discovery, "_analyze", fake_analyze)
    monkeypatch.setattr(discovery.s2, "search_papers", fake_search)
    first = discovery.live_search("DQN")
    second = discovery.live_search("dqn")  # the cache key is case-insensitive
    assert first == second == [{"id": "p1", "title": "Playing Atari"}]
    assert calls == {"analyze": 1, "s2": 1}  # the repeat cost nothing

    # A different filter set is a different search — not served from cache.
    discovery.live_search("dqn", fields_of_study=["Computer Science"])
    assert calls["s2"] == 2


def test_title_match_s2_errors_skip_the_title_not_the_search(monkeypatch):
    monkeypatch.setattr(
        discovery, "_analyze", lambda query: analysis("dqn", ["Playing Atari"])
    )

    def match_down(title):
        raise discovery.s2.S2Error("rate limited")

    monkeypatch.setattr(discovery.s2, "match_title", match_down)
    monkeypatch.setattr(
        discovery.s2, "search_papers", lambda query, **kw: [{"node": {"id": "p1"}}]
    )
    assert discovery.live_search("dqn") == [{"id": "p1"}]


def test_a_pasted_arxiv_url_skips_search_and_expansion_entirely(monkeypatch):
    def explode(*args, **kwargs):
        raise AssertionError("a pasted id must not reach analysis or lexical search")

    monkeypatch.setattr(discovery, "_analyze", explode)
    monkeypatch.setattr(discovery.s2, "search_papers", explode)
    lookups = []

    def fake_get_paper(ref):
        lookups.append(ref)
        return {"id": "s2id01", "title": "Playing Atari"}

    monkeypatch.setattr(discovery.s2, "get_paper", fake_get_paper)
    out = discovery.live_search(
        "https://arxiv.org/abs/1312.5602v2", fields_of_study=["Computer Science"]
    )
    assert out == [{"id": "s2id01", "title": "Playing Atari"}]
    assert lookups == ["ARXIV:1312.5602"]  # bare, version-stripped, prefixed


def test_a_pasted_id_s2_does_not_know_returns_nothing(monkeypatch):
    monkeypatch.setattr(discovery.s2, "get_paper", lambda ref: None)

    def explode(*args, **kwargs):
        raise AssertionError("an unknown id must not fall through to lexical search")

    monkeypatch.setattr(discovery.s2, "search_papers", explode)
    assert discovery.live_search("2406.99999") == []


# --- live_search: OpenAlex provider branch ---------------------------------------


def test_live_search_openalex_branch_uses_openalex_not_s2(monkeypatch):
    """provider='openalex' routes to openalex.search_papers (bare node dicts,
    no unwrap) and never touches S2; the analyst-expanded query still flows."""
    monkeypatch.setattr(discovery, "_analyze", lambda query: analysis("EXPANDED"))
    captured = {}

    def fake_oa_search(query, limit, year_from=None, year_to=None, fields=None):
        captured["query"] = query
        return [{"id": "DOI:10/a", "title": "A"}, {"id": "DOI:10/b", "title": "B"}]

    def s2_forbidden(*args, **kwargs):
        raise AssertionError("S2 must not be called under the OpenAlex provider")

    monkeypatch.setattr(discovery.openalex, "search_papers", fake_oa_search)
    monkeypatch.setattr(discovery.s2, "search_papers", s2_forbidden)
    out = discovery.live_search("gnn", provider="openalex")
    assert captured["query"] == "EXPANDED"
    assert [node["id"] for node in out] == ["DOI:10/a", "DOI:10/b"]


def test_live_search_openalex_pasted_id_resolves_via_openalex(monkeypatch):
    """A pasted arXiv id under OpenAlex resolves through openalex.get_paper."""
    seen = {}

    def fake_get_paper(ref):
        seen["ref"] = ref
        return {"id": "DOI:10/x", "title": "Resolved"}

    monkeypatch.setattr(discovery.openalex, "get_paper", fake_get_paper)
    out = discovery.live_search("2101.00001", provider="openalex")
    assert seen["ref"] == "2101.00001"  # bare id, un-prefixed
    assert out == [{"id": "DOI:10/x", "title": "Resolved"}]


def test_live_search_cache_is_provider_scoped(monkeypatch):
    """An S2 search and an OpenAlex search for the same query are cached under
    different keys — neither is served the other's results."""
    monkeypatch.setattr(discovery, "_analyze", lambda query: analysis("EXP"))
    monkeypatch.setattr(discovery.s2, "search_papers", lambda query, **kw: [{"node": {"id": "s2hit"}}])
    monkeypatch.setattr(discovery.openalex, "search_papers", lambda query, **kw: [{"id": "oahit"}])
    s2_out = discovery.live_search("q", provider="s2")
    oa_out = discovery.live_search("q", provider="openalex")
    assert [node["id"] for node in s2_out] == ["s2hit"]
    assert [node["id"] for node in oa_out] == ["oahit"]  # not the cached S2 result


# --- local_search (cache-first) --------------------------------------------------


def _node(paper_id: str, title: str, **extra) -> dict:
    return {
        "id": paper_id, "arxiv_id": None, "title": title, "authors": None,
        "year": 2020, "citation_count": 1, "url": "u", "is_seed": False, **extra,
    }


def _snapshot(seed: dict, nodes: list[dict]) -> dict:
    return {"seed": seed, "nodes": nodes, "edges": [], "counts": {}}


def test_local_search_matches_tokens_and_flags_fresh_graph():
    cache.set("graph:s2:1706.03762", _snapshot(
        {"arxiv_id": "1706.03762", "id": "seedA", "title": "Attention Is All You Need"},
        [
            _node("seedA", "Attention Is All You Need", is_seed=True,
                  authors="Vaswani", arxiv_id="1706.03762", citation_count=1000),
            _node("nB", "Some Other Paper", authors="Smith"),
        ],
    ))
    out = discovery.local_search("attention", provider="s2")
    ids = [hit["id"] for hit in out]
    assert ids == ["seedA"]  # only the token-matching paper
    assert out[0]["has_graph"] is True  # a fresh snapshot exists with it as seed


def test_local_search_is_scoped_to_the_selected_provider():
    """A cached paper surfaces only for the provider whose snapshot holds it —
    the other provider's cache is invisible, so the 'instant' badge is truthful."""
    cache.set("graph:s2:X", _snapshot(
        {"id": "s2seed", "title": "S2 Snapshot"},
        [_node("s2paper", "Reinforcement Learning Survey", is_seed=True)]))
    cache.set("graph:openalex:Y", _snapshot(
        {"id": "oaseed", "title": "OpenAlex Snapshot"},
        [_node("oapaper", "Reinforcement Learning Survey", is_seed=True)]))

    s2_hits = {hit["id"] for hit in discovery.local_search("reinforcement", provider="s2")}
    oa_hits = {hit["id"] for hit in discovery.local_search("reinforcement", provider="openalex")}
    assert s2_hits == {"s2paper"}  # only the S2 snapshot's paper
    assert oa_hits == {"oapaper"}  # only the OpenAlex snapshot's paper


def test_local_search_dedupes_keeping_the_richer_record():
    # The same paper as a bare neighbor in one snapshot and hydrated in another.
    cache.set("graph:s2:s1", _snapshot(
        {"id": "s1", "title": "Seed One"}, [_node("shared", "Shared Paper Title")]))
    cache.set("graph:s2:s2b", _snapshot(
        {"id": "s2b", "title": "Seed Two"},
        [_node("shared", "Shared Paper Title", authors="Rich Author")]))
    (hit,) = discovery.local_search("shared paper", provider="s2")
    assert hit["id"] == "shared" and hit["authors"] == "Rich Author"


def test_local_search_year_filter_excludes_out_of_range_and_undated():
    cache.set("graph:s2:y", _snapshot(
        {"id": "y", "title": "Y"},
        [
            _node("old", "Deep Learning 2010", year=2010, authors="A"),
            _node("new", "Deep Learning 2022", year=2022, authors="B"),
            _node("undated", "Deep Learning Undated", year=None, authors="C"),
        ],
    ))
    out = discovery.local_search("deep learning", year_from=2015, provider="s2")
    assert {hit["id"] for hit in out} == {"new"}  # 2010 too old, undated excluded under a bound


def test_local_search_ranks_phrase_title_then_seed_then_citations():
    cache.set("graph:s2:r", _snapshot(
        {"id": "seedX", "title": "Neural Networks"},
        [
            _node("seedX", "Neural Networks", is_seed=True, authors="S", citation_count=5),
            _node("exact", "Neural Networks Revisited", authors="E", citation_count=100),
            _node("partial", "Networks of Neural Cells", authors="P", citation_count=50),
        ],
    ))
    order = [hit["id"] for hit in discovery.local_search("neural networks", provider="s2")]
    # phrase-in-title (seedX, exact) beat non-phrase (partial); among the two,
    # the explored seed beats the plain hit.
    assert order.index("seedX") < order.index("exact") < order.index("partial")


def test_local_search_blank_returns_empty():
    assert discovery.local_search("") == []
    assert discovery.local_search("   ") == []
