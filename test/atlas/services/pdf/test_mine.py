"""The cached mining API: memoized text/floats, token registry, render path.

The fetch layer is faked with a synthetic on-disk PDF, so these tests cover
exactly the caching/orchestration contract — one download + one mining pass
per PDF, misses cached, tokens resolvable, unknown tokens refused.
"""

from __future__ import annotations

import fitz
import pytest

from atlas.services.pdf import PdfError, fetch, mine


def _synthetic_pdf(tmp_path):
    """A one-page PDF with one caption-anchored figure and some body text."""
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((100, 60), "A synthetic paper about testing.")
    page.draw_rect(fitz.Rect(100, 100, 300, 250), color=(0, 0, 0), width=1)
    page.insert_text((100, 285), "Figure 1: A synthetic diagram.")
    path = tmp_path / "paper.pdf"
    doc.save(path)
    doc.close()
    return path


def test_text_and_floats_are_mined_once_then_cached(tmp_path, monkeypatch):
    path = _synthetic_pdf(tmp_path)
    fetches = []

    def fake_fetch(url):
        fetches.append(url)
        return path

    monkeypatch.setattr(mine.fetch, "fetch_pdf", fake_fetch)
    url = "https://host/paper.pdf"

    text_result = mine.get_pdf_text(url)
    assert text_result["available"] and "synthetic paper" in text_result["text"]
    floats_result = mine.get_pdf_floats(url)
    assert floats_result["available"] and len(floats_result["floats"]) == 1
    assert floats_result["token"] == fetch.url_token(url)

    # Cached: repeat calls never re-fetch or re-mine.
    fetch_count = len(fetches)
    assert mine.get_pdf_text(url) == text_result
    assert mine.get_pdf_floats(url) == floats_result
    assert len(fetches) == fetch_count


def test_download_failure_is_cached_as_unavailable(monkeypatch):
    def refuse(url):
        raise PdfError("nope")

    monkeypatch.setattr(mine.fetch, "fetch_pdf", refuse)
    url = "https://host/gone.pdf"
    assert mine.get_pdf_text(url) == {"available": False, "text": ""}
    token = fetch.url_token(url)
    assert mine.get_pdf_floats(url) == {"available": False, "token": token, "floats": []}

    # The cached miss answers without another fetch attempt.
    monkeypatch.setattr(
        mine.fetch, "fetch_pdf", lambda u: pytest.fail("cached miss re-fetched")
    )
    assert mine.get_pdf_text(url)["available"] is False
    assert mine.get_pdf_floats(url)["available"] is False


def test_render_figure_resolves_token_and_refuses_unknown(tmp_path, monkeypatch):
    path = _synthetic_pdf(tmp_path)
    monkeypatch.setattr(mine.fetch, "fetch_pdf", lambda url: path)
    url = "https://host/paper.pdf"
    mined = mine.get_pdf_floats(url)  # registers the token → URL mapping

    payload = mine.render_figure(mined["token"], 0)
    assert payload.startswith(b"\x89PNG")

    with pytest.raises(PdfError):
        mine.render_figure(mined["token"], 5)  # out of range
    with pytest.raises(PdfError):
        mine.render_figure("deadbeefdeadbeefdeadbeef", 0)  # never minted
