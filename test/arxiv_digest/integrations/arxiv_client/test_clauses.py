"""clauses: the date-range/category query filters (ID_RE now lives in arxiv)."""

from __future__ import annotations

import pytest

from arxiv_digest.integrations.arxiv_client import clauses


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
    assert clauses.date_clause(year_from, year_to) == expected


def test_category_clause_ors_multiple_categories():
    assert clauses.category_clause(["cs.LG", "cs.CV"]) == "(cat:cs.LG OR cat:cs.CV)"


def test_category_clause_drops_falsy_entries():
    assert clauses.category_clause(["cs.LG", "", None]) == "(cat:cs.LG)"


def test_category_clause_none_for_empty():
    assert clauses.category_clause(None) is None
    assert clauses.category_clause([]) is None
