"""Neighborhood-graph assembly (services/graph/build.py): the typed Graph model —
single-provider traversals, within-provider dedupe, edge directions, counts, the
provider-keyed snapshot cache, and the two provider paths (S2 / OpenAlex).

Provider traversals are monkeypatched with canned node dicts; the cache is real
SQLite on the per-test temp DB (see conftest ``_isolate``). A graph is built from
ONE provider end-to-end — there is no cross-source hybrid — so each provider gets
its own fixture.
"""

from __future__ import annotations

import pytest

from atlas.config import config
from atlas.services.graph import budget, build
from atlas.services.graph.model import Counts, Edge, Graph, Seed


def make_node(paper_id: str, **extra) -> dict:
    """A minimal normalized node dict (the shape build_graph consumes)."""
    return {
        "id": paper_id, "arxiv_id": None, "title": f"Paper {paper_id}", "abstract": None,
        "tldr": None, "year": 2020, "month": None, "pub_date": None,
        "citation_count": 1, "authors": None, "url": "x", **extra,
    }


@pytest.fixture()
def fake_s2(monkeypatch):
    """Canned Semantic Scholar: seed detail + one reference, one landmark citer,
    one latest citer. Drives the ``provider="s2"`` build path.
    """
    calls = {"get_paper": 0}

    def get_paper(lookup):
        calls["get_paper"] += 1
        calls["lookup"] = lookup
        return make_node("seed", title="The Seed")

    def citation_relations(paper_id, *, landmark_limit, latest_limit, landmark_select=None):
        landmark = [{"node": make_node("cite1"), "influential": False}]
        latest = [{"node": make_node("latest1", pub_date="2026-06-01"), "influential": False}]
        return landmark, latest

    monkeypatch.setattr(build.s2, "get_paper", get_paper)
    monkeypatch.setattr(build.s2, "references",
                        lambda pid, limit: [{"node": make_node("ref1"), "influential": True}])
    monkeypatch.setattr(build.s2, "citation_relations", citation_relations)
    return calls


@pytest.fixture()
def fake_openalex(monkeypatch):
    """Canned OpenAlex: seed resolve+hydrate + one reference, one landmark citer,
    one latest citer. Drives the ``provider="openalex"`` build path.
    """
    calls = {"resolve": 0}

    def resolve_seed_work(seed_ref):
        calls["resolve"] += 1
        calls["seed_ref"] = seed_ref
        return {"id": "https://openalex.org/W99"}

    def citation_relations(work_id, *, landmark_limit, latest_limit, band_start=None):
        calls["work_id"] = work_id
        landmark = [{"node": make_node("DOI:10/oa-cite"), "influential": False}]
        latest = [{"node": make_node("DOI:10/oa-latest", pub_date="2026-06-01"),
                   "influential": False}]
        return landmark, latest

    monkeypatch.setattr(build.openalex, "resolve_seed_work", resolve_seed_work)
    monkeypatch.setattr(build.openalex, "node", lambda work: make_node("seed", title="The Seed"))
    monkeypatch.setattr(build.openalex, "bare_work_id", lambda work: "W99")
    monkeypatch.setattr(build.openalex, "references",
                        lambda work_id, limit: [{"node": make_node("ref1"), "influential": False}])
    monkeypatch.setattr(build.openalex, "citation_relations", citation_relations)
    return calls


def test_build_graph_shape_s2(fake_s2):
    """The S2 path: seed + reference + landmark + latest, correct edge directions,
    ranks, and counts — and no `similar` relation (retired from the build)."""
    graph = build.build_graph("1706.03762", provider="s2")
    assert isinstance(graph, Graph)
    assert graph.seed == Seed(arxiv_id=None, id="seed", title="The Seed")
    # arXiv-looking seeds are looked up with the ARXIV: prefix.
    assert fake_s2["lookup"] == "ARXIV:1706.03762"

    by_id = {node.id: node for node in graph.nodes}
    assert by_id["seed"].is_seed is True and by_id["seed"].rels == ["seed"]
    assert by_id["ref1"].rels == ["reference"]
    assert len(graph.nodes) == 4  # seed, ref1, cite1, latest1

    # Edge directions: seed cites ref (seed->ref); citer cites seed (cite->seed).
    assert Edge(source="seed", target="ref1", type="reference", influential=True, rank=0) in graph.edges
    assert Edge(source="cite1", target="seed", type="citation", influential=False, rank=0) in graph.edges
    assert Edge(source="latest1", target="seed", type="latest", influential=False, rank=0) in graph.edges
    # No similar relation is produced; the count stays 0 for schema stability.
    assert not any(edge.type == "similar" for edge in graph.edges)
    assert graph.counts == Counts(references=1, citations=1, similar=0, latest=1, nodes=4)


def test_s2_build_prefers_corpus_over_live(fake_s2, monkeypatch):
    """When the offline corpus can serve the seed, its citers are used and the
    recency-biased live citation endpoint is never called."""
    def corpus_relations(seed_paper, seed_ref, *, landmark_limit, latest_limit):
        landmark = [{"node": make_node("CorpusId:2", title="BERT"), "influential": True}]
        latest = [{"node": make_node("CorpusId:3", pub_date="2026-07-01"), "influential": False}]
        return landmark, latest

    def live_should_not_run(paper_id, *, landmark_limit, latest_limit, landmark_select=None):
        raise AssertionError("live citation_relations called despite an available corpus")

    monkeypatch.setattr(build.s2.corpus, "citation_relations", corpus_relations)
    monkeypatch.setattr(build.s2, "citation_relations", live_should_not_run)

    graph = build.build_graph("1706.03762", provider="s2")
    by_id = {node.id: node for node in graph.nodes}
    assert by_id["CorpusId:2"].rels == ["citation"] and by_id["CorpusId:2"].title == "BERT"
    assert by_id["CorpusId:3"].rels == ["latest"]
    assert graph.citation_source == "corpus"  # surfaced to the UI's Field-Landmarks note


def test_s2_build_falls_back_to_live_when_corpus_declines(fake_s2, monkeypatch):
    """When the corpus returns None (absent, or can't resolve the seed), the build
    falls back to the live citation path."""
    live_calls = {"n": 0}

    def corpus_declines(seed_paper, seed_ref, *, landmark_limit, latest_limit):
        return None

    def live_relations(paper_id, *, landmark_limit, latest_limit, landmark_select=None):
        live_calls["n"] += 1
        return [{"node": make_node("cite1"), "influential": False}], []

    monkeypatch.setattr(build.s2.corpus, "citation_relations", corpus_declines)
    monkeypatch.setattr(build.s2, "citation_relations", live_relations)

    graph = build.build_graph("1706.03762", provider="s2")
    assert live_calls["n"] == 1
    assert any(node.id == "cite1" for node in graph.nodes)
    assert graph.citation_source == "live"


def test_build_graph_shape_openalex(fake_openalex):
    """The OpenAlex path: the seed resolves through ``resolve_seed_work``, the bare
    work id drives the citation queries, and references/citations populate the graph."""
    graph = build.build_graph("1706.03762", provider="openalex")
    assert isinstance(graph, Graph)
    assert graph.seed == Seed(arxiv_id=None, id="seed", title="The Seed")
    assert fake_openalex["seed_ref"] == "1706.03762"  # passed through un-prefixed
    assert fake_openalex["work_id"] == "W99"  # bare id handed to the cites: query

    by_id = {node.id: node for node in graph.nodes}
    assert by_id["ref1"].rels == ["reference"]
    assert by_id["DOI:10/oa-cite"].rels == ["citation"]
    assert by_id["DOI:10/oa-latest"].rels == ["latest"]
    assert Edge(source="DOI:10/oa-cite", target="seed", type="citation",
                influential=False, rank=0) in graph.edges
    assert graph.counts == Counts(references=1, citations=1, similar=0, latest=1, nodes=4)
    assert graph.citation_source is None  # not applicable to OpenAlex's sorted citers


def test_a_paper_thats_both_a_reference_and_a_citer_merges(fake_s2, monkeypatch):
    """A mutual citation — a paper the seed cites that also cites the seed —
    resolves into ONE node carrying both relations, with an edge each way."""
    monkeypatch.setattr(build.s2, "references",
                        lambda pid, limit: [{"node": make_node("mutual"), "influential": False}])

    def citation_relations(pid, *, landmark_limit, latest_limit, landmark_select=None):
        return [{"node": make_node("mutual"), "influential": False}], []

    monkeypatch.setattr(build.s2, "citation_relations", citation_relations)

    graph = build.build_graph("1706.03762", provider="s2")
    by_id = {node.id: node for node in graph.nodes}
    assert by_id["mutual"].rels == ["reference", "citation"]
    # Both directions are drawn (they're different edge types).
    assert Edge(source="seed", target="mutual", type="reference", influential=False, rank=0) in graph.edges
    assert Edge(source="mutual", target="seed", type="citation", influential=False, rank=0) in graph.edges


def test_openalex_duplicate_works_merge_via_arxiv_id(fake_openalex, monkeypatch):
    """OpenAlex sometimes holds duplicate works for one paper (the MuZero-twice
    problem). Two citer sightings sharing an arXiv id merge into ONE node, with a
    single citation edge and a compact rank on the next distinct citer."""
    def citation_relations(work_id, *, landmark_limit, latest_limit, band_start=None):
        landmark = [
            {"node": make_node("DOI:10/a", arxiv_id="1909.08593", citation_count=100),
             "influential": False},
            # OpenAlex's duplicate work for the SAME paper, under another id.
            {"node": make_node("W12345", arxiv_id="1909.08593", citation_count=140),
             "influential": False},
            {"node": make_node("DOI:10/other", citation_count=50), "influential": False},
        ]
        return landmark, []

    monkeypatch.setattr(build.openalex, "citation_relations", citation_relations)

    graph = build.build_graph("1706.03762", provider="openalex")
    by_id = {node.id: node for node in graph.nodes}
    assert "DOI:10/a" in by_id and "W12345" not in by_id
    # The later sighting upgraded the count to the best-known value.
    assert by_id["DOI:10/a"].citation_count == 140
    citation_edges = [edge for edge in graph.edges if edge.type == "citation"]
    assert [(edge.source, edge.rank) for edge in citation_edges] == [
        ("DOI:10/a", 0),
        ("DOI:10/other", 1),
    ]
    assert graph.counts.citations == 2


def test_a_citer_that_is_the_seed_never_self_loops(fake_openalex, monkeypatch):
    """A seed appearing among its own citers (dirty data) merges into the seed
    node — no duplicate seed, no self-edge, seed keeps its single 'seed' tag."""
    monkeypatch.setattr(build.openalex, "node",
                        lambda work: make_node("seed", title="The Seed", arxiv_id="1706.03762"))

    def citation_relations(work_id, *, landmark_limit, latest_limit, band_start=None):
        return [{"node": make_node("DOI:10/seed-twin", arxiv_id="1706.03762"),
                 "influential": False}], []

    monkeypatch.setattr(build.openalex, "citation_relations", citation_relations)

    graph = build.build_graph("1706.03762", provider="openalex")
    by_id = {node.id: node for node in graph.nodes}
    assert "DOI:10/seed-twin" not in by_id
    assert by_id["seed"].rels == ["seed"]
    assert all(edge.source != edge.target for edge in graph.edges)
    assert graph.counts.citations == 0


def test_cache_is_keyed_by_provider(fake_s2, fake_openalex):
    """An S2 graph and an OpenAlex graph for the same seed are distinct snapshots
    — one must never be served for the other's provider."""
    s2_graph = build.build_graph("1706.03762", provider="s2")
    oa_graph = build.build_graph("1706.03762", provider="openalex")
    # Different citer ids prove each provider's own traversal ran (no collision).
    assert {node.id for node in s2_graph.nodes} != {node.id for node in oa_graph.nodes}
    assert "cite1" in {node.id for node in s2_graph.nodes}
    assert "DOI:10/oa-cite" in {node.id for node in oa_graph.nodes}
    # Each is now cache-served (no extra provider calls beyond the first build).
    build.build_graph("1706.03762", provider="s2")
    assert fake_s2["get_paper"] == 1
    build.build_graph("1706.03762", provider="openalex")
    assert fake_openalex["resolve"] == 1


def test_graph_serializes_and_survives_a_cache_round_trip(fake_s2):
    graph = build.build_graph("1706.03762", provider="s2")
    dumped = graph.model_dump()
    assert dumped["seed"] == {"arxiv_id": None, "id": "seed", "title": "The Seed"}
    assert {
        "source": "cite1", "target": "seed", "type": "citation", "influential": False, "rank": 0,
    } in dumped["edges"]
    # Re-validating the dump reproduces the object (the cache-hit path).
    assert Graph.model_validate(dumped) == graph


def test_raw_paperid_seed_skips_arxiv_prefix(fake_s2):
    build.build_graph("abc123def", provider="s2")  # not arXiv-shaped
    assert fake_s2["lookup"] == "abc123def"


def test_snapshot_cache_round_trip(fake_s2):
    first = build.build_graph("1706.03762", provider="s2")
    again = build.build_graph("1706.03762", provider="s2")
    assert fake_s2["get_paper"] == 1  # second call served from cache — zero S2 hits
    assert again == first


def test_refresh_bypasses_cache(fake_s2):
    build.build_graph("1706.03762", provider="s2")
    build.build_graph("1706.03762", provider="s2", refresh=True)
    assert fake_s2["get_paper"] == 2


def test_defaults_to_config_provider(fake_s2, monkeypatch):
    """An omitted provider falls back to config.graph.default_provider."""
    monkeypatch.setattr(config.graph, "default_provider", "s2")
    graph = build.build_graph("1706.03762")
    assert "cite1" in {node.id for node in graph.nodes}  # took the S2 path


def test_resolve_provider_validates_and_defaults(monkeypatch):
    """resolve_provider normalizes valid names and degrades anything else to the
    configured default — the one place provider strings are trusted."""
    monkeypatch.setattr(config.graph, "default_provider", "s2")
    assert build.resolve_provider("openalex") == "openalex"
    assert build.resolve_provider("S2") == "s2"  # case-normalized
    assert build.resolve_provider("  openalex  ") == "openalex"  # trimmed
    assert build.resolve_provider(None) == "s2"  # missing → default
    assert build.resolve_provider("bogus") == "s2"  # unrecognized → default


def test_unknown_seed_returns_none(fake_s2, fake_openalex, monkeypatch):
    monkeypatch.setattr(build.s2, "get_paper", lambda lookup: None)
    monkeypatch.setattr(build.openalex, "resolve_seed_work", lambda seed_ref: None)
    assert build.build_graph("0000.00000", provider="s2") is None
    assert build.build_graph("0000.00000", provider="openalex") is None
    assert build.build_graph("   ", provider="s2") is None


def test_predicted_budget_reaches_the_ranked_traversals(fake_s2, fake_openalex, monkeypatch):
    """The RANKED citer paths (OpenAlex, and the offline S2 corpus) get the
    model's *predicted* budget: they push a count into a citation-sorted query, so
    they must be told it before they hold any citers to measure."""
    monkeypatch.setattr(config.graph, "adaptive_cite_limit", True)
    monkeypatch.setattr(config.graph, "cite_limit", None)
    expected = build._adaptive_cite_limit(make_node("seed", title="The Seed"))
    assert expected not in (None, build.openalex.UNBOUNDED_LANDMARK_CAP)  # genuinely adapted
    received: dict[str, int | None] = {}

    def corpus_relations(seed_paper, seed_ref, *, landmark_limit, latest_limit):
        received["corpus"] = landmark_limit
        return [], []

    monkeypatch.setattr(build.s2.corpus, "citation_relations", corpus_relations)
    build.build_graph("1706.03762", provider="s2")
    assert received["corpus"] == expected

    def openalex_relations(work_id, *, landmark_limit, latest_limit, band_start=None):
        received["openalex"] = landmark_limit
        return [], []

    monkeypatch.setattr(build.openalex, "citation_relations", openalex_relations)
    build.build_graph("1706.03762", provider="openalex")
    assert received["openalex"] == expected


def test_live_s2_fallback_selects_instead_of_predicting(fake_s2, monkeypatch):
    """The LIVE S2 fallback is handed the banded selector, not a predicted count.

    Its pool is truncated at S2's offset ceiling, so a count inferred from the
    seed's age (which assumes landmarks spanning its whole history) over-ships —
    and a count could only keep a prefix anyway, which strands the recent years.
    The pool is in memory by trim time, so ``build`` injects
    ``budget.density_selection`` and passes the flat ``cite_limit`` only as a
    ceiling.
    """
    monkeypatch.setattr(config.graph, "adaptive_cite_limit", True)
    monkeypatch.setattr(config.graph, "cite_limit", 200)
    monkeypatch.setattr(build.s2.corpus, "citation_relations",
                        lambda seed_paper, seed_ref, **kwargs: None)  # force the live path
    received: dict[str, object] = {}

    def live_relations(pid, *, landmark_limit, latest_limit, landmark_select=None):
        received["landmark_limit"] = landmark_limit
        received["landmark_select"] = landmark_select
        return [], []

    monkeypatch.setattr(build.s2, "citation_relations", live_relations)
    build.build_graph("1706.03762", provider="s2")

    # The flat config ceiling, NOT the model's prediction for this seed.
    assert received["landmark_limit"] == 200
    assert received["landmark_select"] is budget.density_selection
    # And the rule it injected really bands: a flooded year is capped without
    # stranding a later one — the hole a predicted count leaves on a real seed.
    select = received["landmark_select"]
    years = [2020] * 30 + [2025] * 3
    assert [years[index] for index in select(years)] == [2020] * budget.DENSITY_CAP + [2025] * 3


def test_on_progress_fires_on_a_build_but_not_a_cache_hit(fake_s2):
    stages: list[tuple[int, int, str]] = []
    build.build_graph("1706.03762", provider="s2",
                      on_progress=lambda done, total, label: stages.append((done, total, label)))
    # One frame per coarse stage, in order (1-indexed so the last hits 100%),
    # each carrying the same total.
    assert [done for done, _, _ in stages] == [1, 2, 3, 4]
    assert {total for _, total, _ in stages} == {build._BUILD_STEPS}
    assert all(label for _, _, label in stages)  # every stage has a human label

    # A cache hit returns before the first stage — no frames.
    stages.clear()
    build.build_graph("1706.03762", provider="s2",
                      on_progress=lambda done, total, label: stages.append((done, total, label)))
    assert stages == []
