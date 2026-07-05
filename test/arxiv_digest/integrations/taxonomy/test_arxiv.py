"""taxonomy.arxiv: the bundled arXiv category taxonomy (groups + valid_codes).

Loads the real taxonomy.json (static bundled data — no network, no fixture).
"""

from __future__ import annotations

from arxiv_digest.integrations.taxonomy import arxiv


def test_groups_returns_areas_with_categories():
    groups = arxiv.groups()
    assert len(groups) == 8  # arXiv's 8 top-level areas
    for group in groups:
        assert group["group"] and isinstance(group["categories"], list)
        for category in group["categories"]:
            assert category["code"] and category["name"]

    # A well-known area/category is present and correctly labelled.
    cs = next(g for g in groups if g["group"] == "Computer Science")
    machine_learning = next(c for c in cs["categories"] if c["code"] == "cs.LG")
    assert machine_learning["name"] == "Machine Learning"


def test_valid_codes_contains_real_codes_and_rejects_junk():
    codes = arxiv.valid_codes()
    assert "cs.LG" in codes
    assert "math.PR" in codes
    assert "not.a.real.code" not in codes


def test_valid_codes_covers_exactly_the_codes_in_groups():
    from_groups = {
        category["code"] for group in arxiv.groups() for category in group["categories"]
    }
    assert arxiv.valid_codes() == from_groups


def test_valid_codes_is_memoized():
    # lru_cache returns the same frozenset object on repeat calls.
    assert arxiv.valid_codes() is arxiv.valid_codes()
