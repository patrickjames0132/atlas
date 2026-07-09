"""Neighborhood-graph assembly (services/graph/build.py): the typed Graph model —
dedupe, relation accumulation, edge directions, counts, and the snapshot cache.

S2 traversals are monkeypatched with canned node dicts; the cache is real SQLite
on the per-test temp DB (see conftest ``_isolate``).
"""

from __future__ import annotations

import pytest

from atlas.services.graph import build
from atlas.services.graph.model import Counts, Edge, Graph, Seed


def make_node(paper_id: str, **extra) -> dict:
    """A minimal normalized S2 node dict (the shape build_graph consumes)."""
    return {
        "id": paper_id, "arxiv_id": None, "title": f"Paper {paper_id}", "abstract": None,
        "tldr": None, "year": 2020, "month": None, "pub_date": None,
        "citation_count": 1, "authors": None, "url": "x", **extra,
    }


@pytest.fixture()
def fake_s2(monkeypatch):
    """Canned S2: seed detail + one ref, one cite, one similar (with overlap).

    OpenAlex resolution is stubbed to return no work, so citations take the S2
    fallback path — this fixture exercises the S2 traversal + assembly. The
    OpenAlex-citations path has its own test below.
    """
    calls = {"get_paper": 0}
    monkeypatch.setattr(build.openalex, "resolve_work", lambda **kwargs: None)

    def get_paper(lookup):
        calls["get_paper"] += 1
        calls["lookup"] = lookup
        return make_node("seed", title="The Seed")

    def citation_relations(pid, *, landmark_limit, latest_limit):
        landmark = [{"node": make_node("cite1"), "influential": False}]
        latest = [{"node": make_node("latest1", pub_date="2026-06-01"), "influential": False}]
        return landmark, latest

    monkeypatch.setattr(build.s2, "get_paper", get_paper)
    monkeypatch.setattr(build.s2, "references",
                        lambda pid, limit: [{"node": make_node("ref1"), "influential": True}])
    monkeypatch.setattr(build.s2, "citation_relations", citation_relations)
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
    assert len(graph.nodes) == 5  # seed, ref1, cite1, sim1, latest1 — deduped

    # Edge directions: seed cites ref (seed->ref); citer cites seed (cite->seed).
    # `rank` is each edge's index within its own relation (the slider order).
    assert Edge(source="seed", target="ref1", type="reference", influential=True, rank=0) in graph.edges
    assert Edge(source="cite1", target="seed", type="citation", influential=False, rank=0) in graph.edges
    # latest citers run citer->seed too, on their own relation.
    assert Edge(source="latest1", target="seed", type="latest", influential=False, rank=0) in graph.edges
    # similar edges carry no influential (None); sim1 is first (rank 0), ref1 second (rank 1).
    assert Edge(source="seed", target="sim1", type="similar", rank=0) in graph.edges
    assert Edge(source="seed", target="ref1", type="similar", rank=1) in graph.edges
    assert graph.counts == Counts(references=1, citations=1, similar=2, latest=1, nodes=5)


def test_citations_come_from_openalex_when_seed_resolves(fake_s2, monkeypatch):
    """The hybrid: when OpenAlex resolves the seed, its citer nodes populate the
    citation/latest relations instead of S2's (references + similar stay S2)."""
    resolved = {"id": "https://openalex.org/W99"}
    monkeypatch.setattr(build.openalex, "resolve_work", lambda **kwargs: resolved)

    captured = {}

    def openalex_relations(work_id, *, landmark_limit, latest_limit):
        captured["work_id"] = work_id
        landmark = [{"node": make_node("DOI:10/oa-cite"), "influential": False}]
        latest = [{"node": make_node("DOI:10/oa-latest", pub_date="2026-06-01"),
                   "influential": False}]
        return landmark, latest

    monkeypatch.setattr(build.openalex, "citation_relations", openalex_relations)

    graph = build.build_graph("1706.03762")
    by_id = {node.id: node for node in graph.nodes}
    assert captured["work_id"] == "W99"  # bare OpenAlex id handed to the cites: query
    # OpenAlex citer + latest nodes are present; the S2 canned cite1/latest1 are not.
    assert "DOI:10/oa-cite" in by_id and by_id["DOI:10/oa-cite"].rels == ["citation"]
    assert "DOI:10/oa-latest" in by_id and by_id["DOI:10/oa-latest"].rels == ["latest"]
    assert "cite1" not in by_id and "latest1" not in by_id
    # References + similar still come from S2.
    assert by_id["ref1"].rels == ["reference", "similar"]


def test_openalex_failure_falls_back_to_s2_citations(fake_s2, monkeypatch):
    """An OpenAlex error never fails the build — it degrades to S2 citations."""
    monkeypatch.setattr(
        build.openalex, "resolve_work",
        lambda **kwargs: (_ for _ in ()).throw(build.openalex.OpenAlexError("down")),
    )
    graph = build.build_graph("1706.03762")
    by_id = {node.id: node for node in graph.nodes}
    assert "cite1" in by_id and "latest1" in by_id  # S2 fallback citers present


def test_graph_serializes_and_survives_a_cache_round_trip(fake_s2):
    graph = build.build_graph("1706.03762")
    dumped = graph.model_dump()
    # A callable-to-JSON shape the routes can hand to jsonify.
    assert dumped["seed"] == {"arxiv_id": None, "id": "seed", "title": "The Seed"}
    assert {
        "source": "seed", "target": "sim1", "type": "similar", "influential": None, "rank": 0,
    } in dumped["edges"]
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


def test_on_progress_fires_on_a_build_but_not_a_cache_hit(fake_s2):
    stages: list[tuple[int, int, str]] = []
    build.build_graph("1706.03762", on_progress=lambda done, total, label: stages.append((done, total, label)))
    # One frame per coarse stage, in order (1-indexed so the last hits 100%),
    # each carrying the same total.
    assert [done for done, _, _ in stages] == [1, 2, 3, 4, 5]
    assert {total for _, total, _ in stages} == {build._BUILD_STEPS}
    assert all(label for _, _, label in stages)  # every stage has a human label

    # A cache hit returns before the first stage — no frames.
    stages.clear()
    build.build_graph("1706.03762", on_progress=lambda done, total, label: stages.append((done, total, label)))
    assert stages == []
