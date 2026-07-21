"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
Seed-search routes: filter parsing/validation, the blank-query and clamp
edges, error philosophies (502 vs never-error), and the taxonomy providers.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

from atlas.integrations import semantic_scholar
from atlas.routes import search as search_routes


def test_search_passes_parsed_filters_to_the_service(client, monkeypatch):
    seen = {}

    def fake_live_search(query, **kwargs):
        seen["q"], seen["kwargs"] = query, kwargs
        return [{"id": "s2id01", "title": "Playing Atari"}]

    monkeypatch.setattr(search_routes.search_service, "live_search", fake_live_search)
    # Under OpenAlex the field filter is validated against OpenAlex field IDS —
    # "17" (Computer Science) survives, "999" is dropped as unknown.
    response = client.get(
        "/api/search?q=DQN&limit=5&year_from=2010&year_to=junk"
        "&fields=17,999&provider=openalex"
    )
    assert response.status_code == 200
    assert response.json == {
        "q": "DQN",
        "count": 1,
        "papers": [{"id": "s2id01", "title": "Playing Atari"}],
    }
    assert seen["q"] == "DQN"
    assert seen["kwargs"] == {
        "limit": 5,
        "year_from": 2010,
        "year_to": None,  # garbage degrades to no-filter
        "fields_of_study": ["17"],  # valid OpenAlex field id kept, unknown dropped
        "provider": "openalex",  # threaded through to the service
        "analyst": True,  # on unless explicitly switched off
    }


def test_search_analyst_arg_switches_the_analyst_off(client, monkeypatch):
    """analyst=0/false/no turns the query analyst off; anything else (junk
    included) keeps it on — the LLM is opt-out, never accidentally off."""
    seen = {}
    monkeypatch.setattr(
        search_routes.search_service, "live_search",
        lambda query, **kwargs: seen.update(kwargs) or [],
    )
    for value, expected in [("0", False), ("false", False), ("no", False),
                            ("1", True), ("junk", True), ("", True)]:
        client.get(f"/api/search?q=dqn&analyst={value}")
        assert seen["analyst"] is expected, value
    client.get("/api/search?q=dqn")  # absent entirely
    assert seen["analyst"] is True


def test_search_field_filter_validates_against_the_provider_vocab(client, monkeypatch):
    """An S2 field name is invalid under OpenAlex (different vocab), so it's
    dropped; the same name is valid under S2."""
    seen = {}
    monkeypatch.setattr(
        search_routes.search_service, "live_search",
        lambda query, **kwargs: seen.update(kwargs) or [],
    )
    client.get("/api/search?q=x&fields=Computer Science&provider=s2")
    assert seen["fields_of_study"] == ["Computer Science"]  # S2 name valid under S2
    client.get("/api/search?q=x&fields=Computer Science&provider=openalex")
    assert seen["fields_of_study"] is None  # not a valid OpenAlex field id


def test_blank_query_returns_empty_without_touching_the_service(client, monkeypatch):
    def explode(query, **kwargs):
        raise AssertionError("the service must not be called for a blank query")

    monkeypatch.setattr(search_routes.search_service, "live_search", explode)
    response = client.get("/api/search?q=")
    assert response.status_code == 200
    assert response.json == {"q": "", "count": 0, "papers": []}


def test_limit_is_clamped_and_garbage_defaults(client, monkeypatch):
    seen = {}

    def fake_live_search(query, **kwargs):
        seen.setdefault("limits", []).append(kwargs["limit"])
        return []

    monkeypatch.setattr(search_routes.search_service, "live_search", fake_live_search)
    client.get("/api/search?q=x&limit=999")
    client.get("/api/search?q=x&limit=abc")
    assert seen["limits"] == [100, 25]


def test_s2_down_returns_a_canned_502(client, monkeypatch):
    def s2_down(query, **kwargs):
        raise semantic_scholar.S2Error("rate limited")

    monkeypatch.setattr(search_routes.search_service, "live_search", s2_down)
    response = client.get("/api/search?q=DQN")
    assert response.status_code == 502
    assert "rate limited" not in response.json["error"]  # details stay in the log


def test_local_search_never_errors(client, monkeypatch):
    def boom(query, **kwargs):
        raise RuntimeError("cache corrupt")

    monkeypatch.setattr(search_routes.search_service, "local_search", boom)
    response = client.get("/api/local_search?q=atari")
    assert response.status_code == 200
    assert response.json == {"q": "atari", "count": 0, "papers": []}


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
