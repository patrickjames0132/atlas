"""Neighborhood-graph assembly (services/graph/build.py): the typed Graph model —
dedupe, relation accumulation, edge directions, counts, and the snapshot cache.

S2 traversals are monkeypatched with canned node dicts; the cache is real SQLite
on the per-test temp DB (see conftest ``_isolate``).
"""

from __future__ import annotations

import pytest

from arxiv_digest.services.graph import build
from arxiv_digest.services.graph.model import Counts, Edge, Graph, Seed


def make_node(paper_id: str, **extra) -> dict:
    """A minimal normalized S2 node dict (the shape build_graph consumes)."""
    return {
        "id": paper_id, "arxiv_id": None, "title": f"Paper {paper_id}", "abstract": None,
        "tldr": None, "year": 2020, "month": None, "pub_date": None,
        "citation_count": 1, "authors": None, "url": "x", **extra,
    }


@pytest.fixture()
def fake_s2(monkeypatch):
    """Canned S2: seed detail + one ref, one cite, one similar (with overlap)."""
    calls = {"get_paper": 0}

    def get_paper(lookup):
        calls["get_paper"] += 1
        calls["lookup"] = lookup
        return make_node("seed", title="The Seed")

    monkeypatch.setattr(build.s2, "get_paper", get_paper)
    monkeypatch.setattr(build.s2, "references",
                        lambda pid, limit: [{"node": make_node("ref1"), "influential": True}])
    monkeypatch.setattr(build.s2, "citations",
                        lambda pid, limit: [{"node": make_node("cite1"), "influential": False}])
    # The similar hit overlaps ref1 — must accumulate rels, not duplicate.
    monkeypatch.setattr(build.s2, "recommendations",
                        lambda pid, limit: [{"node": make_node("sim1")}, {"node": make_node("ref1")}])
    return calls


def test_build_graph_shape(fake_s2):
    graph = build.build_graph("1706.03762")
    assert isinstance(graph, Graph)
    assert graph.seed == Seed(arxiv_id=None, id="seed", title="The Seed")
    # arXiv-looking seeds are looked up with the ARXIV: prefix.
    assert fake_s2["lookup"] == "ARXIV:1706.03762"

    by_id = {node.id: node for node in graph.nodes}
    assert by_id["seed"].is_seed is True and by_id["seed"].rels == ["seed"]
    # ref1 was surfaced by both references and recommendations — one node, both rels.
    assert by_id["ref1"].rels == ["reference", "similar"]
    assert len(graph.nodes) == 4  # seed, ref1, cite1, sim1 — deduped

    # Edge directions: seed cites ref (seed->ref); citer cites seed (cite->seed).
    assert Edge(source="seed", target="ref1", type="reference", influential=True) in graph.edges
    assert Edge(source="cite1", target="seed", type="citation", influential=False) in graph.edges
    # similar edges carry no influential (None).
    assert Edge(source="seed", target="sim1", type="similar") in graph.edges
    assert graph.counts == Counts(references=1, citations=1, similar=2, nodes=4)


def test_graph_serializes_and_survives_a_cache_round_trip(fake_s2):
    graph = build.build_graph("1706.03762")
    dumped = graph.model_dump()
    # A callable-to-JSON shape the routes can hand to jsonify.
    assert dumped["seed"] == {"arxiv_id": None, "id": "seed", "title": "The Seed"}
    assert {"source": "seed", "target": "sim1", "type": "similar", "influential": None} in dumped["edges"]
    # Re-validating the dump reproduces the object (the cache-hit path).
    assert Graph.model_validate(dumped) == graph


def test_raw_paperid_seed_skips_arxiv_prefix(fake_s2):
    build.build_graph("abc123def")  # not arXiv-shaped
    assert fake_s2["lookup"] == "abc123def"


def test_snapshot_cache_round_trip(fake_s2):
    first = build.build_graph("1706.03762")
    again = build.build_graph("1706.03762")
    assert fake_s2["get_paper"] == 1  # second call served from cache — zero S2 hits
    assert again == first  # a Graph rebuilt from the cached JSON equals the original


def test_refresh_bypasses_cache(fake_s2):
    build.build_graph("1706.03762")
    build.build_graph("1706.03762", refresh=True)
    assert fake_s2["get_paper"] == 2


def test_unknown_seed_returns_none(monkeypatch):
    monkeypatch.setattr(build.s2, "get_paper", lambda lookup: None)
    assert build.build_graph("0000.00000") is None
    assert build.build_graph("   ") is None
