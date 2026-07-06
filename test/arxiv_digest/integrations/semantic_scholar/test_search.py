"""Ungrounded free-text search: the year-range filter and search_papers itself.

client.request is faked directly — no network.
"""

from __future__ import annotations

import pytest

from arxiv_digest.integrations.semantic_scholar import client, search


@pytest.mark.parametrize(
    "year_from,year_to,expected",
    [
        (2016, 2020, "2016-2020"),
        (2020, None, "2020-"),
        (None, 2015, "-2015"),
        (None, None, None),
    ],
)
def test_year_range(year_from, year_to, expected):
    assert search._year_range(year_from, year_to) == expected


def test_search_papers_url_carries_year_filter(monkeypatch):
    urls = []

    def fake_request(url, **kw):
        urls.append(url)
        return {"data": [{"paperId": "h1"}]}

    monkeypatch.setattr(client, "request", fake_request)
    (hit,) = search.search_papers("state space models", limit=8, year_from=2024)
    assert "year=2024-" in urls[0] and "state+space+models" in urls[0]
    assert hit["node"]["id"] == "h1"


def test_search_papers_url_carries_fields_of_study_filter(monkeypatch):
    urls = []

    def fake_request(url, **kw):
        urls.append(url)
        return {"data": []}

    monkeypatch.setattr(client, "request", fake_request)
    search.search_papers("transformers", limit=5, fields_of_study=["Computer Science", "Mathematics"])
    # Comma-joined and URL-encoded (space -> +, comma -> %2C).
    assert "fieldsOfStudy=Computer+Science%2CMathematics" in urls[0]


def test_search_papers_omits_fields_filter_when_empty(monkeypatch):
    urls = []
    monkeypatch.setattr(client, "request", lambda url, **kw: urls.append(url) or {"data": []})
    search.search_papers("transformers", limit=5, fields_of_study=[])
    assert "fieldsOfStudy" not in urls[0]


def test_match_title_resolves_the_best_match(monkeypatch):
    urls = []

    def fake_request(url, **kw):
        urls.append(url)
        return {"data": [{"paperId": "atari01", "title": "Playing Atari", "matchScore": 174.2}]}

    monkeypatch.setattr(client, "request", fake_request)
    node = search.match_title("Playing Atari with Deep Reinforcement Learning")
    assert "/paper/search/match?" in urls[0]
    assert node is not None and node["id"] == "atari01"


def test_match_title_treats_the_no_match_404_as_none(monkeypatch):
    def no_match(url, **kw):
        raise client.S2Error("S2 GET ... -> HTTP 404", status=404)

    monkeypatch.setattr(client, "request", no_match)
    assert search.match_title("A Paper The Model Made Up") is None


def test_match_title_reraises_real_failures(monkeypatch):
    def rate_limited(url, **kw):
        raise client.S2Error("S2 GET ... -> gave up after 4 tries")

    monkeypatch.setattr(client, "request", rate_limited)
    with pytest.raises(client.S2Error):
        search.match_title("Playing Atari")
