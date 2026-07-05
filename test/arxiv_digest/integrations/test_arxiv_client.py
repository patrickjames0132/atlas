"""arxiv_client: id detection, query construction, and result normalization.

arxiv.Result objects are built directly (the package's real class, no fakes
needed); the shared _client is swapped for a stub that records the Search it
was given — no network.
"""

from __future__ import annotations

from datetime import datetime, timezone

import arxiv
import pytest

from arxiv_digest.integrations import arxiv_client


class _StubClient:
    """Stand-in for arxiv.Client: records every Search it's given, returns
    canned results."""

    def __init__(self, results: list[arxiv.Result]):
        self.results_to_return = results
        self.searches: list[arxiv.Search] = []

    def results(self, search: arxiv.Search):
        self.searches.append(search)
        return iter(self.results_to_return)


def _result(**overrides) -> arxiv.Result:
    """A minimal valid arxiv.Result, with overrides for the fields under test."""
    fields = {
        "entry_id": "http://arxiv.org/abs/1706.03762v5",
        "title": "Attention  Is\nAll You Need",
        "authors": [arxiv.Result.Author("Ashish Vaswani"), arxiv.Result.Author("Noam Shazeer")],
        "categories": ["cs.CL", "cs.LG"],
        "summary": "The dominant sequence   transduction models...",
        "published": datetime(2017, 6, 12, tzinfo=timezone.utc),
    }
    fields.update(overrides)
    return arxiv.Result(**fields)


# --- _short_id / _to_paper -----------------------------------------------------


def test_short_id_strips_version_suffix():
    assert arxiv_client._short_id(_result(entry_id="http://arxiv.org/abs/2406.12345v2")) == (
        "2406.12345"
    )


def test_short_id_handles_old_style_ids():
    assert arxiv_client._short_id(_result(entry_id="http://arxiv.org/abs/hep-th/9901001v1")) == (
        "hep-th/9901001"
    )


def test_to_paper_normalizes_a_result():
    paper = arxiv_client._to_paper(_result())
    assert paper["arxiv_id"] == "1706.03762"
    assert paper["title"] == "Attention Is All You Need"  # whitespace collapsed
    assert paper["authors"] == "Ashish Vaswani, Noam Shazeer"
    assert paper["categories"] == "cs.CL cs.LG"
    assert paper["abstract"] == "The dominant sequence transduction models..."
    assert paper["url"] == "https://arxiv.org/abs/1706.03762"
    assert paper["published"] == "2017-06-12"


# --- _date_clause / _category_clause -------------------------------------------


@pytest.mark.parametrize(
    "year_from,year_to,expected",
    [
        (2016, 2020, "submittedDate:[201601010000 TO 202012312359]"),
        (2020, None, "submittedDate:[202001010000 TO 209912312359]"),
        (None, 2015, "submittedDate:[199101010000 TO 201512312359]"),
        (None, None, None),
    ],
)
def test_date_clause(year_from, year_to, expected):
    assert arxiv_client._date_clause(year_from, year_to) == expected


def test_category_clause_ors_multiple_categories():
    assert arxiv_client._category_clause(["cs.LG", "cs.CV"]) == "(cat:cs.LG OR cat:cs.CV)"


def test_category_clause_drops_falsy_entries():
    assert arxiv_client._category_clause(["cs.LG", "", None]) == "(cat:cs.LG)"


def test_category_clause_none_for_empty():
    assert arxiv_client._category_clause(None) is None
    assert arxiv_client._category_clause([]) is None


# --- ID_RE ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "text,expected_id",
    [
        ("2406.12345", "2406.12345"),
        ("2406.12345v2", "2406.12345v2"),
        ("hep-th/9901001", "hep-th/9901001"),
        ("https://arxiv.org/abs/2406.12345", "2406.12345"),
        ("https://arxiv.org/pdf/2406.12345v1", "2406.12345v1"),
    ],
)
def test_id_re_matches_bare_and_wrapped_ids(text, expected_id):
    match = arxiv_client.ID_RE.fullmatch(text)
    assert match is not None and match.group(1) == expected_id


def test_id_re_does_not_match_keywords():
    assert arxiv_client.ID_RE.fullmatch("attention is all you need") is None


# --- search_arxiv -----------------------------------------------------------------


class _NeverCalledClient:
    """A client stub that fails the test if it's ever actually queried."""

    def results(self, search: arxiv.Search):
        pytest.fail("should not be called")


def test_search_arxiv_blank_query_short_circuits(monkeypatch):
    monkeypatch.setattr(arxiv_client, "_client", _NeverCalledClient())
    assert arxiv_client.search_arxiv("   ") == []


def test_search_arxiv_with_an_id_does_an_id_lookup(monkeypatch):
    stub = _StubClient([_result()])
    monkeypatch.setattr(arxiv_client, "_client", stub)

    papers = arxiv_client.search_arxiv("1706.03762")

    assert stub.searches[0].id_list == ["1706.03762"]
    assert papers[0]["arxiv_id"] == "1706.03762"


def test_search_arxiv_with_a_url_strips_and_matches(monkeypatch):
    stub = _StubClient([_result()])
    monkeypatch.setattr(arxiv_client, "_client", stub)

    arxiv_client.search_arxiv("https://arxiv.org/abs/1706.03762/")

    assert stub.searches[0].id_list == ["1706.03762"]


def test_search_arxiv_keyword_query_boosts_title_and_ands_filters(monkeypatch):
    stub = _StubClient([_result()])
    monkeypatch.setattr(arxiv_client, "_client", stub)

    arxiv_client.search_arxiv(
        "attention", year_from=2017, categories=["cs.LG"], max_results=10
    )

    query = stub.searches[0].query
    assert '(ti:"attention" OR abs:(attention))' in query
    assert "(cat:cs.LG)" in query
    assert "submittedDate:[201701010000 TO 209912312359]" in query
    assert stub.searches[0].max_results == 10


def test_search_arxiv_strips_quotes_and_parens_from_query(monkeypatch):
    """A user's raw quotes/parens must not break the query syntax we build."""
    stub = _StubClient([_result()])
    monkeypatch.setattr(arxiv_client, "_client", stub)

    arxiv_client.search_arxiv('some "quoted" (text)')

    query = stub.searches[0].query
    # Exactly the two quotes we add ourselves around ti:"..." — none from the
    # user's input survived.
    assert query.count('"') == 2
    assert "quoted" in query and "text" in query
