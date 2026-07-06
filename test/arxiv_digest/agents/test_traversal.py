"""Day-cached S2 hops and search: relation routing, cache behavior (including
the limit living in the key), and that S2 failures propagate untouched."""

from __future__ import annotations

import pytest

from arxiv_digest.agents import traversal

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
