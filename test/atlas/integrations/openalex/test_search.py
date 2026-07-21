"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
Free-text OpenAlex search: the ``search=`` relevance query, its year-window
date filter, and node normalization. ``client.request`` is faked — no network.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

import urllib.parse

from atlas.integrations.openalex import client, search


def _work(work_id, *, doi=None, year=2020, cites=0, title="T"):
    """A minimal raw OpenAlex work object for building fake responses."""
    return {
        "id": f"https://openalex.org/{work_id}",
        "doi": f"https://doi.org/{doi}" if doi else None,
        "title": title,
        "publication_year": year,
        "publication_date": None,
        "cited_by_count": cites,
        "authorships": [],
        "locations": [],
    }


def _query(url):
    """Parse a works URL's query params into a flat dict."""
    return {key: values[0] for key, values in
            urllib.parse.parse_qs(urllib.parse.urlparse(url).query).items()}


def test_search_uses_the_relevance_search_param(monkeypatch):
    """A plain query goes through OpenAlex's ``search=`` param (relevance sort),
    capped by per-page, and comes back as normalized node dicts."""
    def fake_request(url):
        params = _query(url)
        assert params["search"] == "graph neural networks"
        assert params["per-page"] == "5"
        assert "filter" not in params  # no year window
        return {"results": [_work("W1", doi="10/a", cites=99, title="GNN"),
                            _work("W2", doi="10/b", cites=5, title="Another")]}

    monkeypatch.setattr(client, "request", fake_request)
    hits = search.search_papers("graph neural networks", limit=5)
    assert [hit["id"] for hit in hits] == ["DOI:10/a", "DOI:10/b"]
    assert hits[0]["title"] == "GNN" and hits[0]["citation_count"] == 99


def test_search_year_window_becomes_a_date_filter(monkeypatch):
    """Year bounds become from/to_publication_date clauses (Jan-1 / Dec-31)."""
    def fake_request(url):
        params = _query(url)
        assert params["filter"] == "from_publication_date:2018-01-01,to_publication_date:2020-12-31"
        return {"results": []}

    monkeypatch.setattr(client, "request", fake_request)
    search.search_papers("ssm", limit=10, year_from=2018, year_to=2020)


def test_search_single_year_bound(monkeypatch):
    """A single bound emits only its own clause."""
    captured = {}

    def fake_request(url):
        captured["filter"] = _query(url).get("filter")
        return {"results": []}

    monkeypatch.setattr(client, "request", fake_request)
    search.search_papers("x", limit=10, year_from=2021)
    assert captured["filter"] == "from_publication_date:2021-01-01"


def test_search_field_filter_becomes_topics_field_id(monkeypatch):
    """Field ids become a topics.field.id OR clause, combined with the year
    window in one comma-joined filter value."""
    captured = {}

    def fake_request(url):
        captured["filter"] = _query(url).get("filter")
        return {"results": []}

    monkeypatch.setattr(client, "request", fake_request)
    search.search_papers("x", limit=10, year_from=2020, fields=["17", "26"])
    assert captured["filter"] == (
        "topics.field.id:fields/17|fields/26,from_publication_date:2020-01-01"
    )


def test_search_drops_unresolvable_works(monkeypatch):
    """A work with no usable id (node() returns None) is skipped, not crashed on."""
    monkeypatch.setattr(client, "request",
                        lambda url: {"results": [{"id": None}, _work("W9", doi="10/ok")]})
    hits = search.search_papers("q", limit=10)
    assert [hit["id"] for hit in hits] == ["DOI:10/ok"]
