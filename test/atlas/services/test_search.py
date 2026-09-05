"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
Seed discovery (services/search): the cache-first local search, over real
SQLite on the per-test temp DB, plus field-filter validation.

Live search left this module in v7.6.0 (the paper scout owns it now), so what
remains is the half the scout calls *into* rather than duplicates — see
``test/atlas/agents/workers/search/papers/test_main.py`` for the search itself.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

from atlas.services.search import discovery
from atlas.storage import cache

# --- local_search (cache-first) --------------------------------------------------


def _node(paper_id: str, title: str, **extra) -> dict:
    return {
        "id": paper_id, "arxiv_id": None, "title": title, "authors": None,
        "year": 2020, "citation_count": 1, "url": "u", "is_seed": False, **extra,
    }


def _snapshot(seed: dict, nodes: list[dict]) -> dict:
    return {"seed": seed, "nodes": nodes, "edges": [], "counts": {}}


def test_local_search_matches_tokens_and_flags_fresh_graph():
    cache.set("graph:v2:s2:1706.03762", _snapshot(
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
    cache.set("graph:v2:s2:X", _snapshot(
        {"id": "s2seed", "title": "S2 Snapshot"},
        [_node("s2paper", "Reinforcement Learning Survey", is_seed=True)]))
    cache.set("graph:v2:openalex:Y", _snapshot(
        {"id": "oaseed", "title": "OpenAlex Snapshot"},
        [_node("oapaper", "Reinforcement Learning Survey", is_seed=True)]))

    s2_hits = {hit["id"] for hit in discovery.local_search("reinforcement", provider="s2")}
    oa_hits = {hit["id"] for hit in discovery.local_search("reinforcement", provider="openalex")}
    assert s2_hits == {"s2paper"}  # only the S2 snapshot's paper
    assert oa_hits == {"oapaper"}  # only the OpenAlex snapshot's paper


def test_local_search_dedupes_keeping_the_richer_record():
    # The same paper as a bare neighbor in one snapshot and hydrated in another.
    cache.set("graph:v2:s2:s1", _snapshot(
        {"id": "s1", "title": "Seed One"}, [_node("shared", "Shared Paper Title")]))
    cache.set("graph:v2:s2:s2b", _snapshot(
        {"id": "s2b", "title": "Seed Two"},
        [_node("shared", "Shared Paper Title", authors="Rich Author")]))
    (hit,) = discovery.local_search("shared paper", provider="s2")
    assert hit["id"] == "shared" and hit["authors"] == "Rich Author"


def test_local_search_year_filter_excludes_out_of_range_and_undated():
    cache.set("graph:v2:s2:y", _snapshot(
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
    cache.set("graph:v2:s2:r", _snapshot(
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


# --- valid_fields (shared by both filter-accepting routes) -----------------------


def test_valid_fields_keeps_known_values_per_provider():
    assert discovery.valid_fields("s2", ["Computer Science"]) == ["Computer Science"]
    # An OpenAlex numeric field id means nothing to S2, and vice versa — the two
    # vocabularies are disjoint, so a value surviving a provider switch is
    # nonsense rather than merely stale.
    assert discovery.valid_fields("openalex", ["Computer Science"]) == []


def test_valid_fields_drops_unknown_values_rather_than_passing_them_on():
    # Dropped, not forwarded: the filter binds every search now, so one bogus
    # value would silently narrow a search to nothing while the UI still showed
    # a chip claiming it was active.
    assert discovery.valid_fields("s2", ["Computer Science", "Phrenology"]) == [
        "Computer Science"
    ]
    assert discovery.valid_fields("s2", []) == []


def test_local_search_reads_the_same_key_prefix_build_graph_writes():
    """The v7.5.0 regression, pinned. Snapshots moved to `graph:v2:<provider>:`
    to make schema-stale entries unreadable, and this scan kept looking under
    the old `graph:<provider>:` — so it silently matched NOTHING for two
    releases. No error, no empty-cache warning: a cache-first search that had
    quietly stopped being cache-first. Both sides read `snapshot_prefix` now,
    and this asserts they agree rather than trusting them to."""
    from atlas.services.graph import snapshot_prefix

    cache.set(f"{snapshot_prefix('s2')}vkey", _snapshot(
        {"id": "vk", "title": "Versioned"},
        [_node("vpaper", "Versioned Key Paper", is_seed=True)]))
    assert [hit["id"] for hit in discovery.local_search("versioned key", provider="s2")] == [
        "vpaper"
    ]


def test_cached_nodes_keeps_the_instant_flag_local_search_computed():
    """`has_graph` survives the hand-off: a paper whose own graph is already on
    disk opens with no provider call, and the reader is told so."""
    from atlas.services.graph import snapshot_prefix

    cache.set(f"{snapshot_prefix('s2')}inst", _snapshot(
        {"id": "instseed", "title": "Instant Paper"},
        [_node("instseed", "Instant Paper", is_seed=True)]))
    (hit,) = discovery.cached_nodes("instant paper", provider="s2")
    assert hit["has_graph"] is True


def test_a_cached_hit_can_become_a_graph_node():
    """The scout turns these straight into ``DiscoveredNode``s.

    This is the shape contract that matters, and it was broken: ``local_search``
    used to return the search *list's* projection — no abstract, tldr, month or
    pub_date — so every cache hit raised a ``ValidationError`` inside
    ``find_papers``, pydantic-ai retried the tool once, and the whole answer
    died with "Tool 'find_papers' exceeded max retries count of 1". Because a
    cache hit is deterministic, retrying reproduced it exactly.
    """
    from atlas.agents import events

    cache.set("graph:v2:s2:seedA", _snapshot(
        {"arxiv_id": None, "id": "seedA", "title": "Attention Is All You Need"},
        [_node("nB", "Diffusion Models", authors="Ho", abstract=None, tldr=None,
               month=None, pub_date=None, fields_of_study=[], rels=[])],
    ))
    [hit] = discovery.local_search("diffusion", provider="s2")
    # Exactly what the scout does with it (`_cached_hits` drops the badge).
    scouted = {key: value for key, value in hit.items() if key != "has_graph"}
    node = events.DiscoveredNode(**scouted, idx=1)
    assert node.id == "nB"
    assert node.idx == 1


def test_display_hits_keeps_the_search_list_lean():
    """Abstracts are large and the list shows none of them, so the projection
    stays — it just belongs at the wire rather than in the shared lookup."""
    trimmed = discovery.display_hits(
        [{**_node("nB", "Diffusion Models", abstract="a very long abstract"), "has_graph": True}]
    )
    assert "abstract" not in trimmed[0]
    assert trimmed[0]["has_graph"] is True
    assert trimmed[0]["title"] == "Diffusion Models"
