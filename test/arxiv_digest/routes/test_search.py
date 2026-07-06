"""Seed-search routes: filter parsing/validation, the blank-query and clamp
edges, error philosophies (502 vs never-error), and the taxonomy providers."""

from __future__ import annotations

from arxiv_digest.integrations import semantic_scholar
from arxiv_digest.routes import search as search_routes


def test_search_passes_parsed_filters_to_the_service(client, monkeypatch):
    seen = {}

    def fake_live_search(q, **kwargs):
        seen["q"], seen["kwargs"] = q, kwargs
        return [{"id": "s2id01", "title": "Playing Atari"}]

    monkeypatch.setattr(search_routes.search_service, "live_search", fake_live_search)
    response = client.get(
        "/api/search?q=DQN&limit=5&year_from=2010&year_to=junk"
        "&fields=Computer Science,Bogus Field"
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
        "fields_of_study": ["Computer Science"],  # unknown fields silently dropped
    }


def test_blank_query_returns_empty_without_touching_the_service(client, monkeypatch):
    def explode(q, **kwargs):
        raise AssertionError("the service must not be called for a blank query")

    monkeypatch.setattr(search_routes.search_service, "live_search", explode)
    response = client.get("/api/search?q=")
    assert response.status_code == 200
    assert response.json == {"q": "", "count": 0, "papers": []}


def test_limit_is_clamped_and_garbage_defaults(client, monkeypatch):
    seen = {}

    def fake_live_search(q, **kwargs):
        seen.setdefault("limits", []).append(kwargs["limit"])
        return []

    monkeypatch.setattr(search_routes.search_service, "live_search", fake_live_search)
    client.get("/api/search?q=x&limit=999")
    client.get("/api/search?q=x&limit=abc")
    assert seen["limits"] == [100, 25]


def test_s2_down_returns_a_canned_502(client, monkeypatch):
    def s2_down(q, **kwargs):
        raise semantic_scholar.S2Error("rate limited")

    monkeypatch.setattr(search_routes.search_service, "live_search", s2_down)
    response = client.get("/api/search?q=DQN")
    assert response.status_code == 502
    assert "rate limited" not in response.json["error"]  # details stay in the log


def test_local_search_never_errors(client, monkeypatch):
    def boom(q, **kwargs):
        raise RuntimeError("cache corrupt")

    monkeypatch.setattr(search_routes.search_service, "local_search", boom)
    response = client.get("/api/local_search?q=atari")
    assert response.status_code == 200
    assert response.json == {"q": "atari", "count": 0, "papers": []}


def test_taxonomy_providers_return_their_natural_shapes(client):
    s2_response = client.get("/api/taxonomy/s2")
    assert s2_response.status_code == 200
    assert "Computer Science" in s2_response.json["fields"]

    arxiv_response = client.get("/api/taxonomy/arxiv")
    assert arxiv_response.status_code == 200
    group_names = [group["group"] for group in arxiv_response.json["groups"]]
    assert any("Computer" in name for name in group_names)

    assert client.get("/api/taxonomy/gopher").status_code == 404
