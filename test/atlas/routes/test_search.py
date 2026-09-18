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


@pytest.fixture(autouse=True)
def _no_nickname(monkeypatch):
    """Default the direct search's nickname resolve to a miss.

    It runs on every direct search now (alongside the scout), and unstubbed it
    would reach for a model. Tests about the resolve itself override this.
    """
    monkeypatch.setattr(
        search_routes.search_service, "paper_by_name", lambda name, provider="s2": None
    )


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


def test_direct_search_prepends_the_resolved_nickname_paper(client, monkeypatch):
    """The scout has the dropdown's blind spot: asked for `dqn` it led with a
    2020 paper *titled* "Deep Q-Networks" and called it canonical, because a
    text-searching agent cannot get from the acronym to *Playing Atari with
    Deep Reinforcement Learning* any more than a text search can. The same
    day-cached resolve the dropdown runs now runs alongside the scout, and its
    confirmed paper goes to the top — deduped, not doubled, when the scout
    happened to find it too."""
    seen = {}
    stub_scout(
        monkeypatch,
        seen,
        found=[
            {"id": "s2new", "title": "Deep Q-Networks", "citation_count": 61},
            {"id": "s2atari", "title": "Playing Atari with Deep Reinforcement Learning"},
        ],
    )
    monkeypatch.setattr(
        search_routes.search_service,
        "paper_by_name",
        lambda name, provider="s2": {
            "id": "s2atari", "title": "Playing Atari with Deep Reinforcement Learning"
        },
    )
    response = client.get("/api/search?q=dqn")
    result = result_of(response)
    assert [paper["id"] for paper in result["papers"]] == ["s2atari", "s2new"]
    assert result["count"] == 2
    # The hit leaves a chip, in the dropdown's own words for the phase, so the
    # trace says where the top row came from.
    traces = [payload for name, payload in frames(response) if name == "trace"]
    assert traces[-1] == {
        "action": "search", "ok": True, "query": "Working out which paper “dqn” is", "found": 1
    }


def test_the_direct_search_resolve_is_skipped_when_a_found_title_is_the_query(
    client, monkeypatch
):
    """Same gate as the dropdown: exact equality, not "contains". The scout
    finding a paper titled exactly what was typed is the one case world
    knowledge cannot improve on."""
    seen = {}
    stub_scout(monkeypatch, seen, found=[{"id": "s2x", "title": "Attention Is All You Need"}])
    monkeypatch.setattr(
        search_routes.search_service,
        "paper_by_name",
        lambda name, provider="s2": {"id": "s2other", "title": "Something Else"},
    )
    response = client.get("/api/search?q=attention is all you need")
    assert [paper["id"] for paper in result_of(response)["papers"]] == ["s2x"]
    assert not any(
        payload.get("query", "").startswith("Working out")
        for name, payload in frames(response) if name == "trace"
    )


def test_a_miss_on_the_resolve_leaves_no_chip_and_no_change(client, monkeypatch):
    """Most queries are not a paper's name. A miss must be invisible — no
    "nothing new" chip about a step the reader never asked for."""
    seen = {}
    stub_scout(monkeypatch, seen, found=[{"id": "s2x", "title": "Replay"}])
    response = client.get("/api/search?q=replay buffers in rl")
    assert [name for name, _ in frames(response)] == ["result", "done"]
    assert [paper["id"] for paper in result_of(response)["papers"]] == ["s2x"]


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


# --- /api/mentions — the composer's `@` typeahead -------------------------------


def mention_frames(response) -> list[tuple[str, dict]]:
    """Parse a streamed mention response into (event, data) pairs.

    Args:
        response: The Flask test response.

    Returns:
        The frames in order.
    """
    parsed = []
    for chunk in response.data.decode().strip().split("\n\n"):
        event_line, data_line = chunk.split("\n")
        parsed.append(
            (event_line.removeprefix("event: "), json.loads(data_line.removeprefix("data: ")))
        )
    return parsed


def mention_papers(response) -> list[dict]:
    """The papers from a streamed mention response's result frame.

    Args:
        response: The Flask test response.

    Returns:
        The result frame's papers.
    """
    for event, data in mention_frames(response):
        if event == "result":
            return data["papers"]
    raise AssertionError("the stream ended without a result frame")


def test_a_short_mention_query_does_no_lookup_at_all(client, monkeypatch):
    """One or two characters match almost everything, so the list would be
    noise and the live search would be spent on it. Nothing is called."""
    monkeypatch.setattr(
        search_routes.search_service, "local_search",
        lambda *args, **kwargs: pytest.fail("no lookup for a 2-character mention"),
    )
    monkeypatch.setattr(
        search_routes.traversal, "search",
        lambda *args, **kwargs: pytest.fail("no live search for a 2-character mention"),
    )
    assert mention_papers(client.get("/api/mentions?q=dq")) == []
    # And the free pass refuses it too, so the composer's every-keystroke call
    # doesn't scan the cache for a query that matches almost everything.
    assert client.get("/api/mentions?q=dq&source=local").get_json() == {
        "papers": [],
        "partial": False,
    }


def test_a_local_only_mention_lookup_never_touches_the_provider(client, monkeypatch):
    """The whole point of splitting the endpoint. The composer fires this one on
    every keystroke with no debounce, so it must be free — serving both sources
    from one blocking call meant the free half bought nothing, because the
    response still waited on the provider."""
    monkeypatch.setattr(
        search_routes.search_service, "local_search",
        lambda query, limit=8, provider="s2": [{"id": "L1", "title": "Cached"}],
    )
    monkeypatch.setattr(
        search_routes.traversal, "search",
        lambda *args, **kwargs: pytest.fail("a local-only lookup must not hit the provider"),
    )
    body = client.get("/api/mentions?q=dqn&source=local").get_json()
    assert [paper["title"] for paper in body["papers"]] == ["Cached"]
    # The composer needs to know this list is provisional, so it doesn't treat
    # a cache miss as "no such paper".
    assert body["partial"] is True


def test_the_full_mention_lookup_names_each_phase_as_it_starts(client, monkeypatch):
    """Three phases of visibly different cost — a cache scan, a network round
    trip, a model call — and the reader is watching a dropdown while they run.
    A single blocking response could only say "Searching…" for all three."""
    monkeypatch.setattr(
        search_routes.search_service, "local_search", lambda *args, **kwargs: []
    )
    monkeypatch.setattr(search_routes.traversal, "search", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        search_routes.search_service, "paper_by_name", lambda name, provider="s2": None
    )
    frames = mention_frames(client.get("/api/mentions?q=dqn"))
    assert [event for event, _ in frames] == ["step", "step", "step", "result"]
    assert [data["label"] for event, data in frames if event == "step"] == [
        "Looking in your library",
        "Searching Semantic Scholar",
        "Working out which paper \u201cdqn\u201d is",
    ]


def test_the_provider_is_named_in_the_step_label(client, monkeypatch):
    monkeypatch.setattr(
        search_routes.search_service, "local_search", lambda *args, **kwargs: []
    )
    monkeypatch.setattr(search_routes.traversal, "search", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        search_routes.search_service, "paper_by_name", lambda name, provider="s2": None
    )
    labels = [
        data["label"]
        for event, data in mention_frames(client.get("/api/mentions?q=dqn&provider=openalex"))
        if event == "step"
    ]
    assert "Searching OpenAlex" in labels


def test_the_resolve_step_is_announced_BEFORE_it_runs(client, monkeypatch):
    """A step that appears on completion reports what already happened. This is
    the slowest phase, so the frame has to precede the call."""
    order: list[str] = []
    monkeypatch.setattr(
        search_routes.search_service, "local_search", lambda *args, **kwargs: []
    )
    monkeypatch.setattr(search_routes.traversal, "search", lambda *args, **kwargs: [])

    def slow_resolve(name, provider="s2"):
        order.append("resolve ran")
        return None

    monkeypatch.setattr(search_routes.search_service, "paper_by_name", slow_resolve)
    stream = search_routes._mention_stream("dqn", "s2")
    for frame in stream:
        if "Working out" in frame:
            order.append("step emitted")
    assert order == ["step emitted", "resolve ran"]


def test_no_resolve_step_when_a_title_already_matches(client, monkeypatch):
    """The label must not claim work that was skipped."""
    monkeypatch.setattr(
        search_routes.search_service, "local_search", lambda *args, **kwargs: []
    )
    monkeypatch.setattr(
        search_routes.traversal, "search",
        lambda query, limit, provider="s2": [
            {"node": {"id": "S1", "title": "Attention Is All You Need"}}
        ],
    )
    labels = [
        data["label"]
        for event, data in mention_frames(
            client.get("/api/mentions?q=attention+is+all+you+need")
        )
        if event == "step"
    ]
    assert not any("Working out" in label for label in labels)


def test_the_full_mention_lookup_reranks_across_both_sources(client, monkeypatch):
    """An exact live title match must lead a barely-relevant cached paper. Until
    the re-rank ran, the order was "everything cached, then everything live",
    which put the reader's own stale hit above the paper they just named."""
    monkeypatch.setattr(
        search_routes.search_service, "local_search",
        lambda query, limit=8, provider="s2": [
            {"id": "L1", "title": "A survey mentioning DQN in passing", "citation_count": 9000}
        ],
    )
    monkeypatch.setattr(
        search_routes.traversal, "search",
        lambda query, limit, provider="s2": [
            {"node": {"id": "S1", "title": "DQN", "citation_count": 10}}
        ],
    )
    papers = mention_papers(client.get("/api/mentions?q=dqn"))
    assert [paper["title"] for paper in papers] == [
        "DQN",
        "A survey mentioning DQN in passing",
    ]


def test_mentions_put_cached_papers_first_then_live_ones(client, monkeypatch):
    """A paper already in the reader's cache is one they have seen — usually the
    paper they are reaching for — and costs nothing. Live hits fill the rest,
    which is what makes a paper they've never opened mentionable at all."""
    # Neither title contains the query, so the relevance sort can't reorder
    # them and this test is about the merge alone (see the re-rank test above).
    monkeypatch.setattr(
        search_routes.search_service, "local_search",
        lambda query, limit=8, provider="s2": [
            {"id": "L1", "arxiv_id": "1312.5602", "title": "Playing Atari", "venue": "NeurIPS",
             "citation_count": 100}
        ],
    )
    monkeypatch.setattr(
        search_routes.traversal, "search",
        lambda query, limit, provider="s2": [
            {"node": {"id": "S9", "arxiv_id": None, "title": "Rainbow", "venue": "ICML",
                      "citation_count": 50}}
        ],
    )
    papers = mention_papers(client.get("/api/mentions?q=dqn"))
    assert [paper["title"] for paper in papers] == ["Playing Atari", "Rainbow"]
    # The row shows the venue, which the ordinary search list has no need for.
    assert papers[0]["venue"] == "NeurIPS"


def test_a_dead_provider_degrades_to_the_cached_mentions(client, monkeypatch):
    """A typeahead that errors is worse than one that returns less: the reader
    is mid-sentence, and the fallback for an unresolvable name already exists —
    send the message and the scout searches properly."""
    monkeypatch.setattr(
        search_routes.search_service, "local_search",
        lambda query, limit=8, provider="s2": [{"id": "L1", "title": "Playing Atari"}],
    )
    monkeypatch.setattr(
        search_routes.traversal, "search",
        lambda query, limit, provider="s2": (_ for _ in ()).throw(RuntimeError("429")),
    )
    response = client.get("/api/mentions?q=dqn")
    assert response.status_code == 200
    assert [paper["title"] for paper in mention_papers(response)] == ["Playing Atari"]


def test_the_year_filter_deliberately_does_not_bind_a_mention(client, monkeypatch):
    """Unlike every other paper search in the app. Those filters narrow a
    *search* for papers the reader hasn't named; a mention names one. Filtering
    to 2020+ and then failing to resolve `@attention is all you need` (2017)
    would be maddening — the same reading `match_title` already takes."""
    seen: dict = {}

    def record_local(query, limit=8, provider="s2", **kwargs):
        seen["local"] = kwargs
        return []

    def record_live(query, limit, provider="s2", **kwargs):
        seen["live"] = kwargs
        return []

    monkeypatch.setattr(search_routes.search_service, "local_search", record_local)
    monkeypatch.setattr(search_routes.traversal, "search", record_live)
    # Consumed, not just requested: the full pass is a generator, so nothing
    # runs until the body is read.
    mention_papers(client.get("/api/mentions?q=attention&year_from=2020&fields=Computer+Science"))
    # Neither bound is forwarded — the query args are simply not read.
    assert seen["local"] == {} and seen["live"] == {}


# --- the nickname resolve, the one model call in the mention path ---------------


def test_a_nickname_resolves_to_the_top_of_the_mention_list(client, monkeypatch):
    """The case that prompted this. `@dqn` returns a page of DQN-*titled*
    papers while the paper actually called DQN — *Playing Atari with Deep
    Reinforcement Learning* — shares no word with the query and cannot be
    reached by any text search. Measured, not assumed: S2 free-text can't
    reach it at limit 30, `match_title('dqn')` returns nothing, and no field
    of the cached node contains the string."""
    monkeypatch.setattr(
        search_routes.search_service, "local_search", lambda *args, **kwargs: []
    )
    monkeypatch.setattr(
        search_routes.traversal, "search",
        lambda query, limit, provider="s2": [
            {"node": {"id": "S1", "title": "Deep Exploration via Bootstrapped DQN",
                      "citation_count": 1561}}
        ],
    )
    monkeypatch.setattr(
        search_routes.search_service, "paper_by_name",
        lambda name, provider="s2": {
            "id": "S9", "title": "Playing Atari with Deep Reinforcement Learning",
            "citation_count": 13985,
        },
    )
    papers = mention_papers(client.get("/api/mentions?q=dqn"))
    # Prepended, not re-ranked in: an identity match on what was typed
    # outranks any word overlap, however well-cited.
    assert papers[0]["title"] == "Playing Atari with Deep Reinforcement Learning"


def test_the_nickname_resolve_is_skipped_when_a_title_already_matches_exactly(
    client, monkeypatch
):
    """The one case world knowledge cannot improve on: the reader typed a
    paper's full title and it came back."""
    monkeypatch.setattr(
        search_routes.search_service, "local_search", lambda *args, **kwargs: []
    )
    monkeypatch.setattr(
        search_routes.traversal, "search",
        lambda query, limit, provider="s2": [
            {"node": {"id": "S1", "title": "Attention Is All You Need"}}
        ],
    )
    monkeypatch.setattr(
        search_routes.search_service, "paper_by_name",
        lambda name, provider="s2": pytest.fail("no model call when the title already matches"),
    )
    assert mention_papers(client.get("/api/mentions?q=attention+is+all+you+need"))


def test_the_nickname_resolve_is_NOT_gated_on_a_mere_contains_match(client, monkeypatch):
    """The bug in the first cut of this gate, pinned so it can't come back.
    "Text matching found something" is not the same as "found the right
    thing" — every result containing DQN is still the wrong paper."""
    called: list[str] = []
    monkeypatch.setattr(
        search_routes.search_service, "local_search", lambda *args, **kwargs: []
    )
    monkeypatch.setattr(
        search_routes.traversal, "search",
        lambda query, limit, provider="s2": [
            {"node": {"id": "S1", "title": "Multi-DQN: an ensemble for stock forecasting"}}
        ],
    )

    def record(name, provider="s2"):
        called.append(name)
        return None

    monkeypatch.setattr(search_routes.search_service, "paper_by_name", record)
    mention_papers(client.get("/api/mentions?q=dqn"))
    assert called == ["dqn"]  # the contains-match did NOT suppress it


def test_the_local_pass_never_resolves_a_nickname(client, monkeypatch):
    """The free pass has to stay free: it runs on every keystroke, and a model
    call there is exactly what the debounce exists to prevent."""
    monkeypatch.setattr(
        search_routes.search_service, "local_search", lambda *args, **kwargs: []
    )
    monkeypatch.setattr(
        search_routes.search_service, "paper_by_name",
        lambda name, provider="s2": pytest.fail("no model call on the free pass"),
    )
    assert client.get("/api/mentions?q=dqn&source=local").status_code == 200
