"""fulltext: html_to_text extraction, and the cached get_fulltext() reader.

client.fetch_html is faked directly — no network.
"""

from __future__ import annotations

from arxiv_digest.integrations.arxiv import client, fulltext


def test_html_to_text_keeps_block_level_text():
    html = "<h1>Title</h1><p>Some  \n  body text.</p><li>a point</li>"
    assert fulltext.html_to_text(html) == "Title\n\nSome body text.\n\na point"


def test_html_to_text_drops_math_scripts_and_citations():
    html = (
        "<p>Before.</p>"
        "<math>x^2 + y^2</math>"
        "<script>evil()</script>"
        "<style>.x{color:red}</style>"
        "<cite>Smith et al.</cite>"
        "<p>After.</p>"
    )
    assert fulltext.html_to_text(html) == "Before.\n\nAfter."


def test_html_to_text_drops_figure_subtrees():
    html = '<p>Body.</p><figure><figcaption>A caption.</figcaption></figure>'
    assert fulltext.html_to_text(html) == "Body."


def test_html_to_text_empty_document():
    assert fulltext.html_to_text("<div>no block tags here</div>") == ""


def test_get_fulltext_extracts_text(monkeypatch):
    monkeypatch.setattr(client, "fetch_html", lambda arxiv_id: "<p>Full paper text.</p>")
    result = fulltext.get_fulltext("2406.12345")
    assert result == {"available": True, "text": "Full paper text."}


def test_get_fulltext_unavailable_when_ar5iv_has_no_render(monkeypatch):
    monkeypatch.setattr(client, "fetch_html", lambda arxiv_id: None)
    assert fulltext.get_fulltext("2406.12345") == {"available": False, "text": ""}


def test_get_fulltext_blank_id_short_circuits(monkeypatch):
    monkeypatch.setattr(
        client, "fetch_html", lambda arxiv_id: (_ for _ in ()).throw(AssertionError("no fetch"))
    )
    assert fulltext.get_fulltext("") == {"available": False, "text": ""}


def test_get_fulltext_caches_across_calls(monkeypatch):
    calls = []
    monkeypatch.setattr(
        client, "fetch_html", lambda arxiv_id: calls.append(arxiv_id) or "<p>Text.</p>"
    )

    fulltext.get_fulltext("2406.12345")
    fulltext.get_fulltext("2406.12345")

    assert len(calls) == 1  # second call served from cache


def test_get_fulltext_refresh_bypasses_cache(monkeypatch):
    calls = []
    monkeypatch.setattr(
        client, "fetch_html", lambda arxiv_id: calls.append(arxiv_id) or "<p>Text.</p>"
    )

    fulltext.get_fulltext("2406.12345")
    fulltext.get_fulltext("2406.12345", refresh=True)

    assert len(calls) == 2


def test_get_fulltext_strips_version_suffix(monkeypatch):
    ids_seen = []
    monkeypatch.setattr(
        client, "fetch_html", lambda arxiv_id: ids_seen.append(arxiv_id) or "<p>Text.</p>"
    )
    fulltext.get_fulltext("2406.12345v2")
    assert ids_seen == ["2406.12345"]
