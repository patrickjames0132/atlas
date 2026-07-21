"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
Caption-anchored float mining over synthetic, in-test PDFs.

Each test builds a tiny PDF with pymupdf itself — vector drawings, hairline
rules, and caption text laid out like a real paper — so extraction runs the
real geometry pipeline with zero network and zero fixture files.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

from pathlib import Path

import fitz
import pytest

from atlas.services.pdf import PdfError, floats


def _extract(pdf: Path, max_floats: int = 12, max_pages: int = 80) -> list[dict]:
    """Run extraction with paper-sized default caps (tests override per case)."""
    return floats.extract_floats(pdf, max_floats=max_floats, max_pages=max_pages)


def _make_pdf(path: Path, draw) -> Path:
    """Write a one-page PDF whose content the ``draw(page)`` callback paints.

    Args:
        path: Where to save the file.
        draw: Callback receiving the fresh page.

    Returns:
        The saved path.
    """
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    draw(page)
    doc.save(path)
    doc.close()
    return path


def test_figure_above_caption_is_found(tmp_path):
    def draw(page):
        page.draw_rect(fitz.Rect(100, 100, 300, 250), color=(0, 0, 0), width=1)
        page.insert_text((100, 285), "Figure 1: A synthetic diagram.")

    pdf = _make_pdf(tmp_path / "fig.pdf", draw)
    mined = _extract(pdf)
    assert len(mined) == 1
    entry = mined[0]
    assert entry["kind"] == "figure" and entry["page"] == 1
    assert entry["caption"].startswith("Figure 1:")
    # The region covers the drawn content, not the caption text below it.
    x0, y0, x1, y1 = entry["region"]
    assert y0 <= 100 and y1 >= 245 and y1 < 280


def test_prose_reference_is_not_a_caption(tmp_path):
    def draw(page):
        page.draw_rect(fitz.Rect(100, 100, 300, 250), color=(0, 0, 0), width=1)
        page.insert_text((100, 285), "Figure 1 provides another source of intuition.")

    pdf = _make_pdf(tmp_path / "prose.pdf", draw)
    assert _extract(pdf) == []


def test_algorithm_between_rules(tmp_path):
    def draw(page):
        page.draw_line((100, 100), (400, 100))  # top rule
        page.insert_text((102, 112), "Algorithm 1 Synthetic Optimizer")
        page.draw_line((100, 118), (400, 118))  # header rule
        page.insert_text((102, 140), "for step = 1 to N do things")
        page.draw_line((100, 170), (400, 170))  # bottom rule

    pdf = _make_pdf(tmp_path / "algo.pdf", draw)
    mined = _extract(pdf)
    assert len(mined) == 1
    entry = mined[0]
    assert entry["kind"] == "algorithm"
    assert entry["caption"].startswith("Algorithm 1")
    x0, y0, x1, y1 = entry["region"]
    assert y0 <= 100 and y1 >= 170  # spans top rule to bottom rule


def test_algorithm_prose_mention_without_rule_is_skipped(tmp_path):
    def draw(page):
        page.insert_text((100, 400), "Algorithm 1 shows the training loop in detail.")

    pdf = _make_pdf(tmp_path / "algoprose.pdf", draw)
    assert _extract(pdf) == []


def test_booktabs_table_below_caption(tmp_path):
    def draw(page):
        page.insert_text((100, 300), "Table 1: Synthetic results.")
        page.draw_line((100, 312), (400, 312))  # top rule
        page.draw_line((100, 332), (400, 332))  # header rule
        page.insert_text((110, 350), "row one 0.9")
        page.draw_line((100, 370), (400, 370))  # bottom rule

    pdf = _make_pdf(tmp_path / "table.pdf", draw)
    mined = _extract(pdf)
    assert len(mined) == 1
    entry = mined[0]
    assert entry["kind"] == "table"
    assert entry["caption"].startswith("Table 1:")
    x0, y0, x1, y1 = entry["region"]
    # Caption included (a table's caption is part of its visual identity).
    assert y0 < 300 and y1 >= 370


def test_max_floats_cap(tmp_path):
    def draw(page):
        for slot in range(4):
            top = 60 + slot * 170
            page.draw_rect(fitz.Rect(100, top, 300, top + 90), color=(0, 0, 0), width=1)
            page.insert_text((100, top + 125), f"Figure {slot + 1}: Diagram {slot + 1}.")

    pdf = _make_pdf(tmp_path / "many.pdf", draw)
    assert len(_extract(pdf, max_floats=2)) == 2


def test_unparseable_file_yields_no_floats(tmp_path):
    bogus = tmp_path / "not.pdf"
    bogus.write_bytes(b"this is not a pdf at all")
    assert _extract(bogus) == []


def test_render_float_returns_png(tmp_path):
    def draw(page):
        page.draw_rect(fitz.Rect(100, 100, 300, 250), color=(0, 0, 0), width=1)
        page.insert_text((100, 285), "Figure 1: A synthetic diagram.")

    pdf = _make_pdf(tmp_path / "render.pdf", draw)
    entry = _extract(pdf)[0]
    payload = floats.render_float(pdf, entry["page"], entry["region"])
    assert payload.startswith(b"\x89PNG")


def test_render_float_rejects_bad_page(tmp_path):
    def draw(page):
        page.insert_text((100, 100), "hello")

    pdf = _make_pdf(tmp_path / "bad.pdf", draw)
    with pytest.raises(PdfError):
        floats.render_float(pdf, 7, [0, 0, 10, 10])


def test_max_pages_cap(tmp_path):
    """Pages beyond the cap are never scanned — and the cap is the caller's,
    so library mining can raise it for textbooks (the Sarsa(λ) lesson)."""
    doc = fitz.open()
    for page_number in range(3):
        page = doc.new_page(width=612, height=792)
        page.draw_rect(fitz.Rect(100, 100, 300, 250), color=(0, 0, 0), width=1)
        page.insert_text((100, 285), f"Figure {page_number + 1}: Diagram.")
    pdf = tmp_path / "long.pdf"
    doc.save(pdf)
    doc.close()
    assert len(_extract(pdf, max_pages=1)) == 1
    assert len(_extract(pdf, max_pages=3)) == 3
