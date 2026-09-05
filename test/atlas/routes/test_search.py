"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
Seed-search routes: filter parsing/validation, the blank-query and clamp
edges, error philosophies (never-error), and the taxonomy providers.

The scout is stubbed throughout — these test the route's parsing and shaping,
not the agent behind it (that lives in the worker's own test module).

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

import json

import pytest

from atlas.agents.workers.search import papers
from atlas.routes import search as search_routes


def frames(response) -> list[tuple[str, dict]]:
    """Decode an SSE body into (event name, payload) pairs.

    Args:
        response: The test client's streamed response.

    Returns:
        One pair per frame, in arrival order.
    """
    out = []
    for block in response.data.decode().split("\n\n"):
        if not block.strip():
            continue
        name = next(line[7:] for line in block.splitlines() if line.startswith("event: "))
        payload = next(line[6:] for line in block.splitlines() if line.startswith("data: "))
        out.append((name, json.loads(payload)))
    return out


def result_of(response) -> dict:
    """The single ``result`` frame's payload.

    Args:
        response: The test client's streamed response.

    Returns:
        The result payload.
    """
    return next(payload for name, payload in frames(response) if name == "result")


def stub_scout(monkeypatch, seen, found=(), summary="found some", queries=("q",)):
    """Swap the paper scout for a recorder, so the route is tested, not the agent.

    Args:
        monkeypatch: The test's monkeypatch fixture.
        seen: A dict the call's arguments are recorded into.
        found: Node dicts the scout "found".
        summary: The scout's own account of the search.
        queries: The lookups it claims to have made.
    """

    async def fake_scout(need, provider, known_ids, **filters):
        seen["need"], seen["provider"], seen["known_ids"] = need, provider, known_ids
        # on_lookup is the streaming hook, asserted by its own test — drop it
        # so the filter assertions stay about filters.
        seen["filters"] = {key: value for key, value in filters.items() if key != "on_lookup"}
        seen["on_lookup"] = filters.get("on_lookup")
        return papers.ScoutResult(found=list(found), summary=summary, queries=list(queries))

    monkeypatch.setattr(search_routes.papers, "scout", fake_scout)


def test_direct_search_hands_the_query_and_parsed_filters_to_the_scout(client, monkeypatch):
    seen = {}
    stub_scout(monkeypatch, seen, found=[{"id": "s2id01", "title": "Playing Atari"}])
    # Under OpenAlex the field filter is validated against OpenAlex field IDS —
    # "17" (Computer Science) survives, "999" is dropped as unknown.
    response = client.get(
        "/api/search?q=DQN&limit=5&year_from=2010&year_to=junk"
        "&fields=17,999&provider=openalex"
    )
    assert response.status_code == 200
    assert result_of(response) == {
        "q": "DQN",
        "count": 1,
        "papers": [{"id": "s2id01", "title": "Playing Atari"}],
        "summary": "found some",
        "queries": ["q"],
    }
    # The query leads; the picker brief rides behind it (a spread of
    # candidates, not the single best answer — see _PICKER_BRIEF).
    assert seen["need"].startswith("DQN")
    assert "SPREAD of candidates" in seen["need"]
    assert seen["provider"] == "openalex"
    assert seen["filters"] == {
        "year_from": 2010,
        "year_to": None,  # garbage degrades to no-filter
        "fields": ["17"],  # valid OpenAlex field id kept, unknown dropped
        "limit": 5,
    }


def test_direct_search_dedupes_against_nothing(client, monkeypatch):
    """The scout dedupes against its caller's world, which is right for the
    researcher and wrong here: you're picking a paper to explore, and hiding one
    because it already sits on the canvas is exactly backwards."""
    seen = {}
    stub_scout(monkeypatch, seen)
    client.get("/api/search?q=DQN")
    assert seen["known_ids"] == set()


def test_field_filter_is_validated_against_the_selected_provider_vocab(client, monkeypatch):
    """An S2 field name is invalid under OpenAlex (different vocab), so it's
    dropped; the same name is valid under S2."""
    seen = {}
    stub_scout(monkeypatch, seen)
    client.get("/api/search?q=x&fields=Computer Science&provider=s2")
    assert seen["filters"]["fields"] == ["Computer Science"]  # S2 name valid under S2
    client.get("/api/search?q=x&fields=Computer Science&provider=openalex")
    assert seen["filters"]["fields"] is None  # not a valid OpenAlex field id


def test_blank_query_returns_empty_without_running_the_scout(client, monkeypatch):
    async def explode(*args, **kwargs):
        raise AssertionError("the scout must not run for a blank query")

    monkeypatch.setattr(search_routes.papers, "scout", explode)
    response = client.get("/api/search?q=")
    assert response.status_code == 200
    assert result_of(response) == {"q": "", "count": 0, "papers": [], "summary": "", "queries": []}


def test_limit_is_clamped_and_garbage_defaults(client, monkeypatch):
    seen = {}
    limits = []

    async def fake_scout(need, provider, known_ids, **filters):
        limits.append(filters["limit"])
        return papers.ScoutResult(found=[], summary="", queries=[])

    monkeypatch.setattr(search_routes.papers, "scout", fake_scout)
    client.get("/api/search?q=x&limit=999")
    client.get("/api/search?q=x&limit=abc")
    assert limits == [50, 12]
    assert seen == {}


def test_a_failing_scout_is_a_normal_result_with_the_reason_not_an_error_frame(client, monkeypatch):
    """The scout degrades internally — a provider outage comes back as an empty
    result whose summary says why, so the reader is told rather than shown a
    dead route. That's the opposite of the old live-search 502, and it's why
    `error` frames stay reserved for a genuine break."""
    seen = {}
    stub_scout(monkeypatch, seen, found=[], summary="Paper search failed: rate limited")
    response = client.get("/api/search?q=DQN")
    assert response.status_code == 200
    assert result_of(response)["count"] == 0
    assert "rate limited" in result_of(response)["summary"]
    assert [name for name, _ in frames(response)] == ["result", "done"]


def test_each_lookup_streams_pending_then_counted(client, monkeypatch):
    """The reason this route streams at all: a scout run is several seconds,
    and a blocking response left the transcript blank for all of them. Chips
    have to arrive while the work happens — so a lookup is announced when it's
    ISSUED (pending) and again when it lands (with its count).

    The count is not cosmetic: the chip renders "nothing new" whenever `found`
    is missing, so a pending-only stream made every lookup look like a miss,
    including the one that found everything."""

    async def talkative_scout(need, provider, known_ids, **filters):
        on_lookup = filters["on_lookup"]
        on_lookup("deep q-network", None)
        on_lookup("deep q-network", [{"id": "s2a", "title": "One"}])
        return papers.ScoutResult(found=[], summary="done", queries=["deep q-network"])

    monkeypatch.setattr(search_routes.papers, "scout", talkative_scout)
    response = client.get("/api/search?q=dqn")
    # The papers a lookup found ride out WITH its finished chip, so the list
    # grows as the scout works rather than landing whole at the end.
    assert [name for name, _ in frames(response)] == [
        "trace", "trace", "papers", "result", "done"
    ]
    traces = [payload for name, payload in frames(response) if name == "trace"]
    assert traces[0] == {"action": "search", "ok": True, "query": "deep q-network", "pending": True}
    assert traces[1] == {"action": "search", "ok": True, "query": "deep q-network", "found": 1}
    found = next(payload for name, payload in frames(response) if name == "papers")
    assert found == {"papers": [{"id": "s2a", "title": "One"}]}


def test_a_broken_run_ends_the_stream_with_an_error_frame(client, monkeypatch):
    """A stream that simply stops is indistinguishable from one still working,
    so the panel would wait forever — every path has to terminate."""

    async def explode(need, provider, known_ids, **filters):
        raise RuntimeError("the loop fell over")

    monkeypatch.setattr(search_routes.papers, "scout", explode)
    response = client.get("/api/search?q=dqn")
    assert [name for name, _ in frames(response)] == ["error", "done"]


def test_taxonomy_returns_unified_id_name_shape_per_provider(client):
    """Both providers return {fields: [{id, name}]}. For S2 the id IS the name
    (S2 filters on the name); for OpenAlex the id is the numeric field id."""
    s2_fields = client.get("/api/taxonomy/s2").json["fields"]
    cs = next(field for field in s2_fields if field["name"] == "Computer Science")
    assert cs == {"id": "Computer Science", "name": "Computer Science"}  # id == name for S2

    oa_fields = client.get("/api/taxonomy/openalex").json["fields"]
    oa_cs = next(field for field in oa_fields if field["name"] == "Computer Science")
    assert oa_cs == {"id": "17", "name": "Computer Science"}  # numeric OpenAlex field id
    assert len(oa_fields) == 26  # OpenAlex's 26 top-level fields

    # arxiv is retired as a taxonomy provider; an unknown provider is a 404.
    assert client.get("/api/taxonomy/arxiv").status_code == 404
    assert client.get("/api/taxonomy/gopher").status_code == 404


def test_the_cache_answers_first_while_the_scout_is_still_working(client, monkeypatch):
    """The instant tier, rebuilt on the stream rather than on a second endpoint.
    The cache reads in milliseconds, so its hits paint while the scout is still
    on its first provider call — and they arrive BEFORE the result that
    supersedes them, which is the whole point."""
    seen = {}
    stub_scout(monkeypatch, seen, found=[{"id": "s2live", "title": "A Live Paper"}])
    # `cached_nodes` hands back whole graph nodes now — the paper scout builds
    # `DiscoveredNode`s straight out of them — so the route is what trims them
    # for the wire.
    monkeypatch.setattr(
        search_routes.search_service, "cached_nodes",
        lambda *args, **kwargs: [{
            "id": "cachedA", "arxiv_id": None, "title": "A Cached Paper",
            "abstract": "a long abstract nobody reads in a list", "tldr": None,
            "year": 2020, "month": None, "pub_date": None, "citation_count": 7,
            "authors": "Someone", "url": "u", "fields_of_study": [],
            "rels": [], "is_seed": False, "has_graph": True,
        }],
    )
    response = client.get("/api/search?q=dqn")
    names = [name for name, _ in frames(response)]
    assert names.index("cached") < names.index("result")
    cached = next(payload for name, payload in frames(response) if name == "cached")
    [paper] = cached["papers"]
    assert paper["id"] == "cachedA"
    assert paper["title"] == "A Cached Paper"
    assert paper["has_graph"] is True
    # The list shows no abstract, and an abstract per hit is the bulk of the
    # payload — so the projection has to actually drop it.
    assert "abstract" not in paper


def test_a_field_filter_suppresses_the_instant_list_too(client, monkeypatch):
    """Same rule the scout follows: snapshots carry no fields of study, so a
    path that cannot honor the filter is switched OFF rather than allowed to
    quietly ignore it. An instant list that leaked unfiltered papers would
    break the promise the filter makes, and it would do it first."""
    seen = {}
    stub_scout(monkeypatch, seen)
    monkeypatch.setattr(
        search_routes.search_service, "cached_nodes",
        lambda *args, **kwargs: pytest.fail("the cache cannot honour a field filter"),
    )
    response = client.get("/api/search?q=dqn&fields=Computer Science&provider=s2")
    assert "cached" not in [name for name, _ in frames(response)]


def test_a_broken_cache_read_does_not_break_the_search(client, monkeypatch):
    seen = {}
    stub_scout(monkeypatch, seen, found=[{"id": "s2live", "title": "A Live Paper"}])
    monkeypatch.setattr(
        search_routes.search_service, "cached_nodes",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("cache corrupt")),
    )
    response = client.get("/api/search?q=dqn")
    assert result_of(response)["count"] == 1
