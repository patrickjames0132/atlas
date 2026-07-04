"""Neighborhood-graph assembly (services/graph.py): dedupe, relation
accumulation, edge directions, counts, and the snapshot cache.

S2 traversals are monkeypatched with canned nodes; the cache is real SQLite
on the per-test temp DB (see conftest ``_isolate``).
"""

from __future__ import annotations

import pytest
from arxiv_digest.services import graph as graph_service


def n(pid: str, **extra) -> dict:
    """A minimal normalized S2 node."""
    return {"id": pid, "arxiv_id": None, "title": f"Paper {pid}", "abstract": None,
            "tldr": None, "year": 2020, "month": None, "pub_date": None,
            "citation_count": 1, "authors": None, "url": "x", **extra}


@pytest.fixture()
def fake_s2(monkeypatch):
    """Canned S2: seed detail + one ref, one cite, one similar (with overlap)."""
    calls = {"get_paper": 0}

    def get_paper(lookup):
        calls["get_paper"] += 1
        calls["lookup"] = lookup
        return n("seed", title="The Seed")

    monkeypatch.setattr(graph_service.s2, "get_paper", get_paper)
    monkeypatch.setattr(graph_service.s2, "references",
                        lambda pid, limit: [{"node": n("ref1"), "influential": True}])
    monkeypatch.setattr(graph_service.s2, "citations",
                        lambda pid, limit: [{"node": n("cite1"), "influential": False}])
    # The similar hit overlaps ref1 — must accumulate rels, not duplicate.
    monkeypatch.setattr(graph_service.s2, "recommendations",
                        lambda pid, limit: [{"node": n("sim1")}, {"node": n("ref1")}])
    return calls


def test_build_graph_shape(fake_s2):
    g = graph_service.build_graph("1706.03762")
    assert g["seed"] == {"arxiv_id": None, "id": "seed", "title": "The Seed"}
    # arXiv-looking seeds are looked up with the ARXIV: prefix.
    assert fake_s2["lookup"] == "ARXIV:1706.03762"

    by_id = {node["id"]: node for node in g["nodes"]}
    assert by_id["seed"]["is_seed"] is True and by_id["seed"]["rels"] == ["seed"]
    # ref1 was surfaced by both references and recommendations — one node, both rels.
    assert by_id["ref1"]["rels"] == ["reference", "similar"]
    assert len(g["nodes"]) == 4  # seed, ref1, cite1, sim1 — deduped

    # Edge directions: seed cites ref (seed->ref); citer cites seed (cite->seed).
    assert {"source": "seed", "target": "ref1", "type": "reference", "influential": True} in g["edges"]
    assert {"source": "cite1", "target": "seed", "type": "citation", "influential": False} in g["edges"]
    assert {"source": "seed", "target": "sim1", "type": "similar"} in g["edges"]
    assert g["counts"] == {"references": 1, "citations": 1, "similar": 2, "nodes": 4}


def test_raw_paperid_seed_skips_arxiv_prefix(fake_s2):
    graph_service.build_graph("abc123def")  # not arXiv-shaped
    assert fake_s2["lookup"] == "abc123def"


def test_snapshot_cache_round_trip(fake_s2):
    first = graph_service.build_graph("1706.03762")
    again = graph_service.build_graph("1706.03762")
    assert fake_s2["get_paper"] == 1  # second call served from cache — zero S2 hits
    assert again == first


def test_refresh_bypasses_cache(fake_s2):
    graph_service.build_graph("1706.03762")
    graph_service.build_graph("1706.03762", refresh=True)
    assert fake_s2["get_paper"] == 2


def test_unknown_seed_returns_none(monkeypatch):
    monkeypatch.setattr(graph_service.s2, "get_paper", lambda lookup: None)
    assert graph_service.build_graph("0000.00000") is None
    assert graph_service.build_graph("   ") is None
