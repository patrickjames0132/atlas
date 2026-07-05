"""node(): normalizing a raw S2 paper object into the app's graph-node shape."""

from __future__ import annotations

import pytest

from arxiv_digest.integrations.semantic_scholar import nodes


def test_node_normalizes_rich_paper():
    raw = {
        "paperId": "abc",
        "externalIds": {"ArXiv": "1706.03762"},
        "title": "Attention",
        "abstract": "We propose...",
        "tldr": {"model": "v2", "text": "Attention is enough."},
        "year": 2017,
        "publicationDate": "2017-06-12",
        "citationCount": 100000,
        "authors": [{"name": "Vaswani"}, {"name": ""}, {"name": "Shazeer"}],
    }
    node = nodes.node(raw)
    assert node["id"] == "abc" and node["arxiv_id"] == "1706.03762"
    assert node["tldr"] == "Attention is enough."
    assert node["month"] == 6 and node["pub_date"] == "2017-06-12"
    assert node["authors"] == "Vaswani, Shazeer"  # blanks dropped
    assert node["url"] == "https://arxiv.org/abs/1706.03762"


def test_node_handles_sparse_paper():
    node = nodes.node({"paperId": "xyz"})
    assert node["title"] == "(untitled)" and node["arxiv_id"] is None
    assert node["month"] is None and node["authors"] is None
    assert node["url"] == "https://www.semanticscholar.org/paper/xyz"


@pytest.mark.parametrize(
    "pub,month",
    [
        ("2017-06-12", 6),
        ("2017-13-01", None),
        ("2017", None),
        (None, None),
        ("2017-0x-01", None),
    ],
)
def test_node_month_parsing(pub, month):
    node = nodes.node({"paperId": "a", "publicationDate": pub})
    assert node["month"] == month


def test_node_none_for_unresolved():
    assert nodes.node(None) is None
    assert nodes.node({}) is None
    assert nodes.node({"title": "no paperId"}) is None


def test_from_papers_wraps_and_skips_unresolved():
    raw = [{"paperId": "r1", "title": "Resolved"}, None, {"title": "no paperId"}]
    assert nodes.from_papers(raw) == [{"node": nodes.node({"paperId": "r1", "title": "Resolved"})}]
