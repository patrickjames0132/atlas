"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
Library figure mining (sources/figures.py): manifest from a stored PDF,
cached misses for sources without a file, and on-demand rendering.

The stored PDF is synthesized with pymupdf directly at ``store.pdf_path`` —
no ingestion needed, since mining only cares about the file.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

import fitz
import pytest

from atlas.services.pdf import PdfError
from atlas.services.sources import figures, store


def _store_pdf(source_id: str) -> None:
    """Write a one-page PDF with one caption-anchored figure for a source,
    and register the source row (resolve_page_figure validates against it)."""
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.draw_rect(fitz.Rect(100, 100, 300, 250), color=(0, 0, 0), width=1)
    page.insert_text((100, 285), "Figure 1: A synthetic diagram.")
    doc.save(store.pdf_path(source_id))
    doc.close()
    with store.connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO sources (id, title, kind, origin, pages, n_chunks) "
            "VALUES (?, ?, 'pdf', 'test.pdf', 1, 0)",
            (source_id, f"Book {source_id}"),
        )


def test_manifest_from_stored_pdf():
    _store_pdf("src1")
    mined = figures.get_source_figures("src1")
    assert mined["available"] is True
    entry = mined["floats"][0]
    assert entry["kind"] == "figure" and entry["page"] == 1
    assert entry["caption"].startswith("Figure 1:")


def test_no_stored_pdf_is_cached_unavailable():
    assert figures.get_source_figures("ghost") == {"available": False, "floats": []}
    # The miss answers from cache — a file appearing later needs refresh=True.
    _store_pdf("ghost")
    assert figures.get_source_figures("ghost")["available"] is False
    assert figures.get_source_figures("ghost", refresh=True)["available"] is True


def test_render_source_figure_png_and_range():
    _store_pdf("src2")
    payload = figures.render_source_figure("src2", 0)
    assert payload.startswith(b"\x89PNG")
    with pytest.raises(PdfError):
        figures.render_source_figure("src2", 9)
    with pytest.raises(PdfError):
        figures.render_source_figure("nope", 0)


def test_resolve_page_figure_miss_lists_candidates_with_captions():
    """A wrong-page miss steers with CAPTIONS, not bare page numbers — the
    model must be able to judge relevance before attaching (the
    backup-diagrams incident, docs/bugs.md)."""
    _store_pdf("src3")
    resolution, message = figures.resolve_page_figure("src3", 40, 1)
    # _store_pdf puts its one figure on page 1; page 40 has nothing.
    assert resolution is None
    assert "No extractable figures on page 40" in message
    assert 'p.1 "Figure 1: A synthetic diagram."' in message
    assert "caption matches" in message


def test_resolve_page_figure_success_carries_entry():
    _store_pdf("src4")
    resolution, message = figures.resolve_page_figure("src4", 1, 1)
    assert message == ""
    assert resolution["manifest_index"] == 0
    assert resolution["entry"]["caption"].startswith("Figure 1:")
