"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
Normalizing an OpenAlex work into the app's node shape: id resolution,
inverted-index abstracts, arXiv-id extraction, and shape parity with S2.

Pure functions — no network.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
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


def _arxiv_work(**overrides) -> dict:
    """A raw OpenAlex work carrying an arXiv location (so arxiv_id resolves)."""
    return {
        "id": "https://openalex.org/W1",
        "doi": "https://doi.org/10/x",
        "title": "T",
        "authorships": [],
        "locations": [
            {
                "landing_page_url": "https://arxiv.org/abs/1706.03762",
                "source": {"display_name": "arXiv"},
            }
        ],
        **overrides,
    }


def test_arxiv_date_parses_only_new_format_ids():
    assert nodes._arxiv_date("1706.03762") == (2017, 6)
    assert nodes._arxiv_date("2412.00001") == (2024, 12)
    assert nodes._arxiv_date("hep-th/9901001") is None  # old-format → OpenAlex's date
    assert nodes._arxiv_date("1799.00001") is None  # month 99 invalid
    assert nodes._arxiv_date(None) is None


def test_node_prefers_arxiv_date_when_openalex_year_disagrees():
    """OpenAlex's misdated year (AIAYN → 2025) is corrected from the new-format
    arXiv id's encoded year+month."""
    node = nodes.node(_arxiv_work(publication_year=2025, publication_date="2025-08-23"))
    assert node["year"] == 2017 and node["month"] == 6 and node["pub_date"] == "2017-06"


def test_node_keeps_openalex_date_when_year_matches():
    """When the arXiv year agrees with OpenAlex's, keep OpenAlex's fuller date."""
    node = nodes.node(_arxiv_work(publication_year=2017, publication_date="2017-06-12"))
    assert node["year"] == 2017 and node["pub_date"] == "2017-06-12"  # day preserved


def test_fields_of_study_from_topics_deduped_and_capped():
    """OpenAlex topics become the node's field tags: deduped, order-preserving,
    capped at _MAX_TOPICS. Absent topics (light neighbor nodes) → []."""
    work = {
        "id": "https://openalex.org/W1",
        "doi": "https://doi.org/10/x",
        "title": "T",
        "topics": [
            {"display_name": "Machine Learning"},
            {"display_name": "Machine Learning"},  # dupe dropped
            {"display_name": "Reinforcement Learning"},
            *[{"display_name": f"Topic {index}"} for index in range(10)],  # over the cap
        ],
        "authorships": [],
        "locations": [],
    }
    node = nodes.node(work)
    assert node is not None
    assert node["fields_of_study"][:2] == ["Machine Learning", "Reinforcement Learning"]
    assert len(node["fields_of_study"]) == nodes._MAX_TOPICS  # capped
    # A work without topics (a neighbor traversal) carries no field tags.
    assert nodes.node({"id": "https://openalex.org/W2", "doi": "https://doi.org/10/y",
                       "title": "N", "authorships": [], "locations": []})["fields_of_study"] == []


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
        "venue": None,
        "oa_pdf": None,
    }


def test_node_venue_from_primary_location():
    """The venue is the primary location's source name; absent → None."""
    work = {
        "id": "https://openalex.org/W2",
        "doi": "https://doi.org/10.1038/248030a0",
        "title": "T",
        "publication_year": 1974,
        "publication_date": None,
        "cited_by_count": 1,
        "authorships": [],
        "locations": [],
        "primary_location": {"source": {"display_name": "Nature"}},
    }
    assert nodes.node(work)["venue"] == "Nature"
    # A neighbor traversal never selects primary_location — venue stays None.
    work.pop("primary_location")
    assert nodes.node(work)["venue"] is None
    # A sourceless primary location (repository oddities) is also None.
    work["primary_location"] = {"source": None}
    assert nodes.node(work)["venue"] is None


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


def test_node_oa_pdf_prefers_open_access_location():
    """An is_oa location's pdf_url wins; any pdf_url is the fallback."""
    work = {
        "id": "https://openalex.org/W1",
        "doi": "https://doi.org/10.1/x",
        "title": "T",
        "locations": [
            {"source": {"display_name": "Elsevier"}, "pdf_url": "https://closed/x.pdf"},
            {
                "source": {"display_name": "PubMed Central"},
                "pdf_url": "https://pmc/x.pdf",
                "is_oa": True,
            },
        ],
    }
    assert nodes.node(work)["oa_pdf"] == "https://pmc/x.pdf"
    work["locations"] = [work["locations"][0]]
    assert nodes.node(work)["oa_pdf"] == "https://closed/x.pdf"
    work["locations"] = []
    assert nodes.node(work)["oa_pdf"] is None
