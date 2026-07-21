"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
categories: a paper's own arXiv category tags, labelled and cached.

categories.fetch_categories is faked directly — no network.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

from atlas.integrations.arxiv import categories


def test_get_categories_labels_known_codes(monkeypatch):
    monkeypatch.setattr(categories, "fetch_categories", lambda arxiv_id: ["cs.CL", "cs.LG"])

    result = categories.get_categories("1706.03762")

    assert result == {
        "available": True,
        "categories": [
            {"code": "cs.CL", "name": "Computation and Language"},
            {"code": "cs.LG", "name": "Machine Learning"},
        ],
    }


def test_get_categories_dedupes_codes_sharing_one_display_name(monkeypatch):
    # cs.LG and stat.ML are different codes that are both "Machine Learning" —
    # a paper cross-listed in both must only get one tag.
    monkeypatch.setattr(
        categories, "fetch_categories", lambda arxiv_id: ["cs.LG", "cs.CL", "stat.ML"]
    )

    result = categories.get_categories("1706.03762")

    assert result["categories"] == [
        {"code": "cs.LG", "name": "Machine Learning"},  # first-listed code wins
        {"code": "cs.CL", "name": "Computation and Language"},
    ]


def test_get_categories_falls_back_to_the_bare_code_when_unrecognized(monkeypatch):
    monkeypatch.setattr(categories, "fetch_categories", lambda arxiv_id: ["not.a.real.code"])

    result = categories.get_categories("2406.12345")

    assert result["categories"] == [{"code": "not.a.real.code", "name": "not.a.real.code"}]


def test_get_categories_unavailable_when_arxiv_has_no_entry(monkeypatch):
    monkeypatch.setattr(categories, "fetch_categories", lambda arxiv_id: None)
    assert categories.get_categories("9999.99999") == {"available": False, "categories": []}


def test_get_categories_blank_id_short_circuits(monkeypatch):
    monkeypatch.setattr(
        categories,
        "fetch_categories",
        lambda arxiv_id: (_ for _ in ()).throw(AssertionError("no fetch")),
    )
    assert categories.get_categories("") == {"available": False, "categories": []}


def test_get_categories_caches_across_calls(monkeypatch):
    calls = []
    monkeypatch.setattr(
        categories,
        "fetch_categories",
        lambda arxiv_id: calls.append(arxiv_id) or ["cs.LG"],
    )

    categories.get_categories("1706.03762")
    categories.get_categories("1706.03762")

    assert len(calls) == 1  # second call served from cache


def test_get_categories_refresh_bypasses_cache(monkeypatch):
    calls = []
    monkeypatch.setattr(
        categories,
        "fetch_categories",
        lambda arxiv_id: calls.append(arxiv_id) or ["cs.LG"],
    )

    categories.get_categories("1706.03762")
    categories.get_categories("1706.03762", refresh=True)

    assert len(calls) == 2


def test_get_categories_strips_version_suffix(monkeypatch):
    seen = []
    monkeypatch.setattr(
        categories, "fetch_categories", lambda arxiv_id: seen.append(arxiv_id) or ["cs.LG"]
    )

    categories.get_categories("1706.03762")
    categories.get_categories("1706.03762v7")

    assert seen == ["1706.03762"]  # same cache entry either way


def test_fetch_categories_parses_the_first_entrys_terms(monkeypatch):
    body = b"""<?xml version='1.0' encoding='UTF-8'?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <category term="cs.CL" scheme="http://arxiv.org/schemas/atom"/>
    <category term="cs.LG" scheme="http://arxiv.org/schemas/atom"/>
  </entry>
</feed>"""

    class FakeResponse:
        def read(self):
            return body

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr("urllib.request.urlopen", lambda request, timeout: FakeResponse())

    assert categories.fetch_categories("1706.03762") == ["cs.CL", "cs.LG"]


def test_fetch_categories_returns_none_for_an_empty_feed(monkeypatch):
    body = b"""<?xml version='1.0' encoding='UTF-8'?>
<feed xmlns="http://www.w3.org/2005/Atom"></feed>"""

    class FakeResponse:
        def read(self):
            return body

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr("urllib.request.urlopen", lambda request, timeout: FakeResponse())

    assert categories.fetch_categories("9999.99999") is None


def _fake_feed(monkeypatch, body: bytes) -> None:
    """Point urlopen at a canned Atom feed body."""

    class FakeResponse:
        def read(self):
            return body

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr("urllib.request.urlopen", lambda request, timeout: FakeResponse())


def test_get_title_reads_and_collapses_the_entry_title(monkeypatch):
    # arXiv titles often carry newlines / doubled spaces from line wrapping.
    _fake_feed(
        monkeypatch,
        b"""<?xml version='1.0' encoding='UTF-8'?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry><title>Attention Is All\n  You Need</title></entry>
</feed>""",
    )
    assert categories.get_title("1706.03762") == "Attention Is All You Need"


def test_get_title_none_for_empty_feed(monkeypatch):
    _fake_feed(
        monkeypatch,
        b"""<?xml version='1.0' encoding='UTF-8'?>
<feed xmlns="http://www.w3.org/2005/Atom"></feed>""",
    )
    assert categories.get_title("9999.99999") is None


def test_get_title_blank_id_short_circuits():
    assert categories.get_title("") is None
    assert categories.get_title("   ") is None
