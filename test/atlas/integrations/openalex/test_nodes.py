"""Normalizing an OpenAlex work into the app's node shape: id resolution,
inverted-index abstracts, arXiv-id extraction, and shape parity with S2.

Pure functions — no network.
"""

from __future__ import annotations

from atlas.integrations.openalex import nodes


def test_reconstruct_abstract_orders_by_position():
    inverted = {"world": [1], "Hello": [0], "again": [2, 4], "hello": [3]}
    assert nodes.reconstruct_abstract(inverted) == "Hello world again hello again"


def test_reconstruct_abstract_empty_is_none():
    assert nodes.reconstruct_abstract(None) is None
    assert nodes.reconstruct_abstract({}) is None


def test_bare_doi_strips_url_and_prefix():
    assert nodes._bare_doi("https://doi.org/10.1038/248030a0") == "10.1038/248030a0"
    assert nodes._bare_doi("doi:10.1/x") == "10.1/x"
    assert nodes._bare_doi(None) is None


def test_bare_openalex_id_from_url():
    assert nodes.bare_openalex_id("https://openalex.org/W123") == "W123"
    assert nodes.bare_openalex_id(None) is None


def test_arxiv_id_from_locations_landing_url():
    work = {
        "locations": [
            {"source": {"display_name": "Journal X"}, "landing_page_url": "https://x/y"},
            {
                "source": {"display_name": "arXiv (Cornell University)"},
                "landing_page_url": "http://arxiv.org/abs/1706.03762",
            },
        ]
    }
    assert nodes.arxiv_id_from_work(work) == "1706.03762"


def test_arxiv_id_from_arxiv_minted_doi():
    work = {
        "locations": [
            {
                "source": {"display_name": "arXiv (Cornell University)"},
                "landing_page_url": "",
                "doi": "https://doi.org/10.48550/arXiv.2101.00001",
            }
        ]
    }
    assert nodes.arxiv_id_from_work(work) == "2101.00001"


def test_arxiv_id_none_when_not_on_arxiv():
    work = {"locations": [{"source": {"display_name": "Nature"}, "landing_page_url": "https://n/1"}]}
    assert nodes.arxiv_id_from_work(work) is None


def test_resolvable_id_prefers_doi_then_arxiv_then_openalex():
    assert nodes.resolvable_id({"doi": "https://doi.org/10.1/x"}, "1706.03762") == "DOI:10.1/x"
    assert nodes.resolvable_id({"doi": None, "id": "https://openalex.org/W9"}, "1706.03762") == (
        "ARXIV:1706.03762"
    )
    assert nodes.resolvable_id({"doi": None, "id": "https://openalex.org/W9"}, None) == "W9"


def test_node_full_shape_parity_and_month():
    work = {
        "id": "https://openalex.org/W2065805883",
        "doi": "https://doi.org/10.1038/248030a0",
        "title": "Black hole explosions?",
        "publication_year": 1974,
        "publication_date": "1974-03-01",
        "cited_by_count": 5649,
        "authorships": [{"author": {"display_name": "S. W. Hawking"}}],
        "locations": [],
        "abstract_inverted_index": {"Foo": [0], "bar": [1]},
    }
    node = nodes.node(work)
    assert node == {
        "id": "DOI:10.1038/248030a0",
        "arxiv_id": None,
        "title": "Black hole explosions?",
        "abstract": "Foo bar",
        "tldr": None,
        "year": 1974,
        "month": 3,
        "pub_date": "1974-03-01",
        "citation_count": 5649,
        "authors": "S. W. Hawking",
        "url": "https://doi.org/10.1038/248030a0",
        "fields_of_study": [],
    }


def test_node_arxiv_url_and_id_when_on_arxiv():
    work = {
        "id": "https://openalex.org/W1",
        "doi": None,
        "title": "T",
        "publication_year": 2017,
        "publication_date": None,
        "cited_by_count": None,
        "authorships": [],
        "locations": [
            {
                "source": {"display_name": "arXiv (Cornell University)"},
                "landing_page_url": "https://arxiv.org/abs/1706.03762",
            }
        ],
    }
    node = nodes.node(work)
    assert node["arxiv_id"] == "1706.03762"
    assert node["id"] == "ARXIV:1706.03762"
    assert node["url"] == "https://arxiv.org/abs/1706.03762"
    assert node["month"] is None  # no publication_date


def test_node_none_for_empty_or_idless():
    assert nodes.node(None) is None
    assert nodes.node({}) is None  # no doi, no arxiv, no id
