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
