"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
Day-cached S2 hops and search: relation routing, cache behavior (including
the limit living in the key), and that S2 failures propagate untouched.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

import pytest

from atlas.agents import traversal

HIT = {"node": {"id": "s2-x", "title": "X"}}


class FakeS2:
    """Counts calls per endpoint and returns canned hits."""

    def __init__(self):
        self.calls: list[tuple] = []

    def references(self, paper_id, limit):
        self.calls.append(("references", paper_id, limit))
        return [HIT]

    def citations(self, paper_id, limit):
        self.calls.append(("citations", paper_id, limit))
        return [HIT]

    def recommendations(self, paper_id, limit):
        self.calls.append(("recommendations", paper_id, limit))
        return [HIT]

    def search_papers(self, query, limit, year_from, year_to):
        self.calls.append(("search_papers", query, limit, year_from, year_to))
        return [HIT]


@pytest.fixture
def fake_s2(monkeypatch):
    fake = FakeS2()
    for name in ("references", "citations", "recommendations", "search_papers"):
        monkeypatch.setattr(traversal.s2, name, getattr(fake, name))
    return fake


def test_neighbors_routes_each_relation_to_its_endpoint(fake_s2):
    traversal.neighbors("p1", "references", 5)
    traversal.neighbors("p1", "citations", 5)
    traversal.neighbors("p1", "similar", 5)
    assert [call[0] for call in fake_s2.calls] == [
        "references",
        "citations",
        "recommendations",
    ]


def test_neighbors_second_call_is_served_from_cache(fake_s2):
    first = traversal.neighbors("p1", "references", 5)
    second = traversal.neighbors("p1", "references", 5)
    assert first == second == [HIT]
    assert len(fake_s2.calls) == 1


def test_neighbors_cache_key_includes_the_limit(fake_s2):
    traversal.neighbors("p1", "references", 5)
    traversal.neighbors("p1", "references", 10)
    assert len(fake_s2.calls) == 2  # different limit -> different cache entry


def test_relations_do_not_share_cache_entries(fake_s2):
    traversal.neighbors("p1", "references", 5)
    traversal.neighbors("p1", "citations", 5)
    assert len(fake_s2.calls) == 2


def test_search_caches_by_normalized_query(fake_s2):
    traversal.search("  Deep Q-Network  ", 10)
    traversal.search("deep q-network", 10)
    assert len(fake_s2.calls) == 1  # same entry after strip+lowercase
    # ...but S2 saw the query as given, not the normalized form.
    assert fake_s2.calls[0][1] == "  Deep Q-Network  "


def test_search_year_window_is_forwarded_and_keyed(fake_s2):
    traversal.search("dqn", 10, year_from=2015, year_to=2020)
    traversal.search("dqn", 10)  # different window -> different entry
    assert fake_s2.calls[0] == ("search_papers", "dqn", 10, 2015, 2020)
    assert len(fake_s2.calls) == 2


def test_s2_errors_propagate_uncaught(monkeypatch):
    def boom(paper_id, limit):
        raise traversal.s2.S2Error("rate limited")

    monkeypatch.setattr(traversal.s2, "references", boom)
    with pytest.raises(traversal.s2.S2Error):
        traversal.neighbors("p1", "references", 5)


def test_rel_tag_maps_every_relation():
    assert traversal.REL_TAG == {
        "references": "reference",
        "citations": "citation",
        "similar": "similar",
    }


# --- OpenAlex provider ------------------------------------------------------------


class FakeOpenAlex:
    """Fakes the OpenAlex traversal surface the agent layer calls."""

    def __init__(self):
        self.calls: list[tuple] = []

    def resolve_seed_work(self, node_id):
        self.calls.append(("resolve", node_id))
        return {"id": "https://openalex.org/W99"}

    def bare_work_id(self, work):
        return "W99"

    def references(self, work_id, limit):
        self.calls.append(("references", work_id, limit))
        return [HIT]

    def citations(self, work_id, limit):
        self.calls.append(("citations", work_id, limit))
        return [HIT]

    def related_works(self, work_id, limit):
        self.calls.append(("related_works", work_id, limit))
        return [HIT]

    def search_papers(self, query, limit, year_from, year_to):
        # openalex.search_papers returns BARE node dicts (NOT the {"node": ...}
        # traversal shape) — mirror that so the wrap-at-the-boundary is tested.
        self.calls.append(("search_papers", query, limit, year_from, year_to))
        return [{"id": "oa-x", "title": "X"}]


@pytest.fixture
def fake_openalex(monkeypatch):
    fake = FakeOpenAlex()
    for name in (
        "resolve_seed_work", "bare_work_id", "references", "citations",
        "related_works", "search_papers",
    ):
        monkeypatch.setattr(traversal.openalex, name, getattr(fake, name))
    return fake


def test_openalex_neighbors_resolve_then_hit_the_matching_endpoint(fake_openalex):
    """Under OpenAlex each hop resolves the node id to a work, then hits the
    matching endpoint — similar routes to related_works (no S2 recommendations)."""
    traversal.neighbors("DOI:10/x", "references", 5, provider="openalex")
    traversal.neighbors("DOI:10/x", "citations", 5, provider="openalex")
    traversal.neighbors("DOI:10/x", "similar", 5, provider="openalex")
    assert [call[0] for call in fake_openalex.calls] == [
        "resolve", "references", "resolve", "citations", "resolve", "related_works"
    ]


def test_openalex_search_uses_openalex_and_wraps_bare_nodes(fake_openalex):
    """OpenAlex search hits are bare node dicts; traversal.search wraps them into
    the {"node": ...} shape the researcher's search tool consumes (else it
    KeyErrors on hit["node"])."""
    out = traversal.search("graph neural networks", 10, provider="openalex")
    assert fake_openalex.calls[0] == ("search_papers", "graph neural networks", 10, None, None)
    assert out == [{"node": {"id": "oa-x", "title": "X"}}]  # wrapped, not bare


def test_provider_scopes_the_cache(fake_s2, fake_openalex):
    """The same node under different providers keys to different cache entries —
    neither serves the other, and each provider's endpoints are hit."""
    traversal.neighbors("p1", "references", 5, provider="s2")
    traversal.neighbors("p1", "references", 5, provider="openalex")
    assert ("references", "p1", 5) in fake_s2.calls  # S2 hit by paperId
    assert ("resolve", "p1") in fake_openalex.calls  # OpenAlex resolved the node id
