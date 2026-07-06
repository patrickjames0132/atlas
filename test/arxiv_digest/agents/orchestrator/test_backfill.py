"""The backfill walk: launches from the oldest visible papers, ranks
ancestors by citations, marches backward, stops at the year floor, and
reports failure honestly."""

from __future__ import annotations

from arxiv_digest.agents import events
from arxiv_digest.agents.orchestrator import backfill
from arxiv_digest.config import config
from arxiv_digest.integrations import semantic_scholar as s2
from arxiv_digest.services.graph import Node


def make_node(node_id: str, title: str, **overrides) -> Node:
    fields = dict(
        id=node_id,
        arxiv_id=None,
        title=title,
        abstract=None,
        tldr=None,
        year=2015,
        month=None,
        pub_date=None,
        citation_count=100,
        authors=None,
        url=f"https://example.org/{node_id}",
        rels=["reference"],
        is_seed=False,
    )
    fields.update(overrides)
    return Node(**fields)


def hit(node_id: str, year: int, citations: int, influential: bool = False) -> dict:
    return {
        "node": dict(
            id=node_id, arxiv_id=None, title=f"Paper {node_id}", abstract=None,
            tldr=None, year=year, month=None, pub_date=None,
            citation_count=citations, authors=None,
            url=f"https://example.org/{node_id}",
        ),
        "influential": influential,
    }


SEED = make_node("seed01", "Modern Seed", is_seed=True, year=2020, rels=[])
NODES = [
    SEED,
    make_node("mid90s", "Nineties Paper", year=1995),
    make_node("mid00s", "Noughties Paper", year=2005),
    make_node("recent", "Recent Paper", year=2019),
]


def test_launches_from_the_oldest_visible_papers(monkeypatch):
    asked: list[str] = []

    def fake_neighbors(paper_id, relation, limit):
        asked.append(paper_id)
        return []

    monkeypatch.setattr(backfill.traversal, "neighbors", fake_neighbors)
    list(backfill.history_backfill(SEED, NODES))
    # frontier=2: the two oldest non-seed papers, oldest first — never the seed.
    assert asked == ["mid90s", "mid00s"]


def test_ranks_by_citations_caps_per_hop_and_keeps_known_edges(monkeypatch):
    monkeypatch.setattr(config.graph.backfill, "per_hop", 2)
    monkeypatch.setattr(config.graph.backfill, "hops", 1)
    hits = [
        hit("anc-small", 1980, citations=10),
        hit("anc-big", 1985, citations=50000, influential=True),
        hit("anc-mid", 1975, citations=900),
        {"node": {**hit("recent", 2019, 1)["node"]}},  # already on the graph
    ]
    monkeypatch.setattr(
        backfill.traversal,
        "neighbors",
        lambda paper_id, relation, limit: hits if paper_id == "mid90s" else [],
    )

    out = list(backfill.history_backfill(SEED, NODES))
    trace, discovery = out
    assert trace == events.BackfillTrace(hop=1, found=2, oldest=1975)
    assert [node.id for node in discovery.nodes] == ["anc-big", "anc-mid"]  # citation order
    assert all(node.idx is None for node in discovery.nodes)  # pre-numbering
    # anc-small was fetched but not kept -> its edge has a dangling endpoint.
    assert {(edge.source, edge.target) for edge in discovery.edges} == {
        ("mid90s", "anc-big"),
        ("mid90s", "anc-mid"),
        ("mid90s", "recent"),
    }


def test_marches_backward_and_stops_at_the_year_floor(monkeypatch):
    monkeypatch.setattr(config.graph.backfill, "frontier", 1)
    calls: list[str] = []

    def fake_neighbors(paper_id, relation, limit):
        calls.append(paper_id)
        by_frontier = {
            "mid90s": [hit("anc-1985", 1985, 100)],
            "anc-1985": [hit("anc-1970", 1970, 100)],  # 1970 <= 2020-40 -> floor
            "anc-1970": [hit("anc-1950", 1950, 100)],
        }
        return by_frontier.get(paper_id, [])

    monkeypatch.setattr(backfill.traversal, "neighbors", fake_neighbors)
    out = list(backfill.history_backfill(SEED, NODES))
    assert calls == ["mid90s", "anc-1985"]  # floor hit -> the third hop never runs
    traces = [event for event in out if isinstance(event, events.BackfillTrace)]
    assert [trace.oldest for trace in traces] == [1985, 1970]


def test_nothing_found_reports_once_with_the_error_flag(monkeypatch):
    def explode(paper_id, relation, limit):
        raise s2.S2Error("rate limited")

    monkeypatch.setattr(backfill.traversal, "neighbors", explode)
    out = list(backfill.history_backfill(SEED, NODES))
    assert out == [events.BackfillTrace(hop=1, found=0, oldest=None, error=True)]


def test_clean_empty_walk_has_no_error_flag(monkeypatch):
    monkeypatch.setattr(
        backfill.traversal, "neighbors", lambda paper_id, relation, limit: []
    )
    out = list(backfill.history_backfill(SEED, NODES))
    assert out == [events.BackfillTrace(hop=1, found=0, oldest=None, error=False)]
