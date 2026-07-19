"""Caption-anchored float mining: a PDF's figures, tables, and algorithms.

A paper PDF carries no semantic markup — just text, embedded images, and
vector drawings — so "the paper's figures" have to be reconstructed from
layout. Mining is **caption-first**: find the caption blocks (``Figure N:``,
``Table N:``, ``Algorithm N``), then locate each float's content region
relative to its caption, which both finds the right pixels and rejects junk
(a drawing cluster with no caption is a decoration, not a figure):

* **Figure** — captions sit BELOW their content (fallback: above). The region
  seeds from every image rect / vector-drawing cluster adjacent to the
  caption, then grows by axis-aware chaining (``_chain_near``) so side-by-side
  subfigures, film-strip tiles, and the scattered pieces of sparse line
  drawings all join in. Size is judged at the answer: candidate clusters may
  be tiny (``_MIN_CLUSTER_AREA`` only drops dust), but the grown region must
  clear ``_MIN_REGION_AREA``. The package README's "The geometry, precisely"
  section walks the whole pipeline with its terminology.
* **Table** — captions sit ABOVE (fallback: below). Tries pymupdf's
  ``find_tables`` bbox first, then a span of same-width horizontal rules
  (booktabs tables are rules-only and invisible to ``find_tables``), then a
  drawing-skeleton cluster widened to the caption's x-span (tables whose only
  ink is a header rule plus column tick marks).
* **Algorithm** — the caption sits just under the float's TOP rule; the
  region runs to the last same-width rule. The rule anchor doubles as the
  prose filter ("Algorithm 1 shows…" body text has no rule above it).

The caption regex requires ``:``/``.`` after a Figure/Table number precisely
because in-prose references ("Figure 2 provides…") start identically.

Floats made purely of text (no images, drawings, or rules — e.g. a
pseudo-code figure in a very old PDF) are the known miss: nothing anchors
them geometrically, so they're skipped rather than guessed at.

Beware one pymupdf trap (cost this module a debugging session in the spike):
a hairline rule is an EMPTY rect (zero height), and ``Rect.__or__`` silently
ignores empty operands — rule spans are therefore built from raw
coordinates, never with ``|``.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING

from ...config import config
from .errors import PdfError

if TYPE_CHECKING:  # pymupdf is imported lazily (heavy native module)
    import fitz

log = logging.getLogger(__name__)

CAPTION_RE = re.compile(r"^(?:(Figure|Fig|Table)\.?\s+\d+\s*[:.]|(Algorithm)\s+\d+\b)")
_MAX_CAPTION = 600  # chars — same cap as the ar5iv figure extractor
_MIN_TILE = 30  # pt — keep film-strip tiles, drop glyph-sized fragments
_MIN_CLUSTER_AREA = 100  # pt² — admit small pieces (a diagram may be a swarm
# of tiny arrows/nodes — Sutton & Barto's backup diagrams); only dust is
# dropped here, because the REGION floor below is what rejects junk.
_MIN_REGION_AREA = 4000  # pt² — a grown region must be figure-sized; a lone
# underline or footnote rule near a caption never becomes a "figure".
_GAP = 60  # max pt between a caption and its content
_CHAIN_GAP = 60  # max pt a content piece may sit from the region (one axis)
# while overlapping it in the other — sparse line drawings (arrows-and-nodes
# backup diagrams) are swarms of small pieces a contact-only chain can't walk.
_RULE_SPAN_MAX_STEP = 320  # max pt between consecutive rules of one float
_RULE_X_TOLERANCE = 8  # pt — how exactly two rules must agree to share a float
_PAD = 4  # pt of margin around a rendered region


def _horizontal_rules(page: fitz.Page) -> list[fitz.Rect]:
    """Thin, wide horizontal drawing rects (float-bounding rules), top-down.

    Args:
        page: The loaded page.

    Returns:
        The rule rects sorted by their top edge.
    """
    rules = []
    for drawing in page.get_drawings():
        rect = drawing["rect"]
        if rect.height <= 3 and rect.width >= 100:
            rules.append(rect)
    return sorted(rules, key=lambda rect: rect.y0)


def _content_rects(page: fitz.Page) -> list[fitz.Rect]:
    """Candidate content regions: image rects plus sizeable drawing clusters.

    Args:
        page: The loaded page.

    Returns:
        Rects for every embedded image placement at least ``_MIN_TILE`` on a
        side, and every vector-drawing cluster of at least
        ``_MIN_CLUSTER_AREA``.
    """
    rects = []
    for image_entry in page.get_images(full=True):
        for rect in page.get_image_rects(image_entry[0]):
            if rect.width >= _MIN_TILE and rect.height >= _MIN_TILE:
                rects.append(rect)
    for rect in page.cluster_drawings():
        if rect.width * rect.height >= _MIN_CLUSTER_AREA:
            rects.append(rect)
    return rects


def _overlap_x(first: fitz.Rect, second: fitz.Rect) -> bool:
    """Whether two rects overlap horizontally.

    Args:
        first: One rect.
        second: The other rect.

    Returns:
        True when their x-extents intersect.
    """
    return first.x0 < second.x1 and second.x0 < first.x1


def _chain_near(region: fitz.Rect, rect: fitz.Rect) -> bool:
    """Whether a content piece belongs to the growing region.

    True when the two overlap in one axis and sit within ``_CHAIN_GAP`` in
    the other — the shape of both subfigure tiles (touching) and a sparse
    line drawing's scattered pieces (nearby columns/rows of arrows and
    nodes).

    Args:
        region: The region grown so far.
        rect: The candidate piece.

    Returns:
        True when the piece should join.
    """
    x_overlap = rect.x0 < region.x1 and region.x0 < rect.x1
    y_overlap = rect.y0 < region.y1 and region.y0 < rect.y1
    x_gap = max(region.x0 - rect.x1, rect.x0 - region.x1)
    y_gap = max(region.y0 - rect.y1, rect.y0 - region.y1)
    return (x_overlap and y_gap <= _CHAIN_GAP) or (y_overlap and x_gap <= _CHAIN_GAP)


def _grab_adjacent(
    caption: fitz.Rect, rects: list[fitz.Rect], above: bool
) -> fitz.Rect | None:
    """Union of content rects near the caption, grown by adjacency chaining.

    Seeds with every rect on the chosen side of the caption (top edge above
    it / bottom edge below it) within ``_GAP``, x-overlapping the caption —
    an overlapping rect (a cluster that visually contains its caption) counts
    as "above" too. Then any rect intersecting the padded region joins, so
    subfigure tiles — and the tiny pieces of an arrows-and-nodes line
    drawing — chain in. The candidates may individually be small
    (``_MIN_CLUSTER_AREA`` only drops dust); what must be figure-sized is
    the grown region (``_MIN_REGION_AREA``).

    Args:
        caption: The caption block's rect.
        rects: Candidate content rects on the page.
        above: Search above the caption (True) or below it (False).

    Returns:
        The unioned region, or None when nothing sits on that side — or when
        what does is too small to be a figure.
    """
    region: fitz.Rect | None = None
    remaining = list(rects)
    for rect in list(remaining):
        if above:
            near = rect.y0 < caption.y0 and (caption.y0 - rect.y1) <= _GAP
        else:
            near = rect.y1 > caption.y1 and (rect.y0 - caption.y1) <= _GAP
        if near and _overlap_x(rect, caption):
            region = rect if region is None else region | rect
            remaining.remove(rect)
    if region is None:
        return None
    changed = True
    while changed:
        changed = False
        for rect in list(remaining):
            if _chain_near(region, rect):
                region = region | rect
                remaining.remove(rect)
                changed = True
    if region.width * region.height < _MIN_REGION_AREA:
        return None
    return region


def _rule_span(caption: fitz.Rect, rules: list[fitz.Rect], below: bool) -> fitz.Rect | None:
    """A float bounded by same-width horizontal rules on one side of a caption.

    Seeds from the nearest rule within ``_GAP`` on the chosen side that
    x-overlaps the caption, then extends through same-x-span rules stepping
    away from the caption (each step at most ``_RULE_SPAN_MAX_STEP``) — the
    shape of a booktabs table's top/header/bottom rules.

    Args:
        caption: The caption block's rect.
        rules: The page's horizontal rules (as from ``_horizontal_rules``).
        below: Search below the caption (True) or above it (False).

    Returns:
        The span from first to last rule, or None when no anchored,
        multi-rule span exists on that side.
    """
    import fitz

    if below:
        candidates = sorted(
            (rule for rule in rules if rule.y0 >= caption.y1 - 3),
            key=lambda rule: rule.y0,
        )
    else:
        candidates = sorted(
            (rule for rule in rules if rule.y1 <= caption.y0 + 3),
            key=lambda rule: -rule.y1,
        )
    seed = None
    for rule in candidates:
        gap = (rule.y0 - caption.y1) if below else (caption.y0 - rule.y1)
        if gap <= _GAP and _overlap_x(rule, caption):
            seed = rule
            break
    if seed is None:
        return None
    # Raw min/max coordinates on purpose: hairline rules are EMPTY rects and
    # `Rect | Rect` ignores empty operands entirely (see module docstring).
    top_y, bottom_y = seed.y0, seed.y1
    last = seed
    for rule in candidates:
        if rule is seed:
            continue
        same_width = (
            abs(rule.x0 - seed.x0) < _RULE_X_TOLERANCE
            and abs(rule.x1 - seed.x1) < _RULE_X_TOLERANCE
        )
        step = abs(rule.y0 - last.y1) if below else abs(last.y0 - rule.y1)
        if same_width and step <= _RULE_SPAN_MAX_STEP:
            top_y, bottom_y = min(top_y, rule.y0), max(bottom_y, rule.y1)
            last = rule
    if bottom_y - top_y < 10:  # a single rule is not a table
        return None
    return fitz.Rect(seed.x0, top_y, seed.x1, bottom_y)


def _algorithm_region(caption: fitz.Rect, rules: list[fitz.Rect]) -> fitz.Rect | None:
    """From the rule just above an Algorithm caption to the last same-width rule.

    Args:
        caption: The caption block's rect.
        rules: The page's horizontal rules.

    Returns:
        The float's region, or None when the caption has no rule directly
        above it (an in-prose "Algorithm 1 shows…" mention) or the float has
        no closing rule.
    """
    import fitz

    anchored = [
        rule for rule in rules if rule.y1 <= caption.y0 + 3 and _overlap_x(rule, caption)
    ]
    if not anchored:
        return None
    top = max(anchored, key=lambda rule: rule.y1)
    if caption.y0 - top.y1 > 20:
        return None
    span = [
        rule
        for rule in rules
        if rule.y0 >= top.y0
        and abs(rule.x0 - top.x0) < _RULE_X_TOLERANCE
        and abs(rule.x1 - top.x1) < _RULE_X_TOLERANCE
    ]
    if len(span) < 2:
        return None
    return fitz.Rect(top.x0, top.y0, top.x1, span[-1].y1)


def _table_region(
    page: fitz.Page,
    caption: fitz.Rect,
    rects: list[fitz.Rect],
    rules: list[fitz.Rect],
) -> fitz.Rect | None:
    """A table's content region, by descending reliability of table anatomy.

    Args:
        page: The loaded page (for ``find_tables``).
        caption: The caption block's rect.
        rects: Candidate content rects on the page.
        rules: The page's horizontal rules.

    Returns:
        The region, or None when nothing table-shaped sits near the caption.
    """
    import fitz

    for table in page.find_tables().tables:
        table_rect = fitz.Rect(table.bbox)
        gap_below = table_rect.y0 - caption.y1
        gap_above = caption.y0 - table_rect.y1
        if (-15 <= gap_below <= _GAP or -15 <= gap_above <= _GAP) and _overlap_x(
            table_rect, caption
        ):
            return table_rect
    region = _rule_span(caption, rules, below=True)
    if region is None:
        region = _rule_span(caption, rules, below=False)
    if region is None:
        # Rules-and-ticks skeleton (header rule + column separators): cluster
        # the drawings, then widen to the caption's x-span so text columns
        # outside the drawn skeleton aren't cropped.
        region = _grab_adjacent(caption, rects, above=False)
        if region is None:
            region = _grab_adjacent(caption, rects, above=True)
        if region is not None:
            region = fitz.Rect(
                min(region.x0, caption.x0),
                region.y0 - 6,
                max(region.x1, caption.x1),
                region.y1 + 6,
            )
    return region


def extract_floats(path: str | Path, *, max_floats: int, max_pages: int) -> list[dict]:
    """Mine a PDF's caption-anchored floats: figures, tables, algorithms.

    The caps are the caller's, on purpose: a paper wants paper-sized limits
    (``config.pdf.research_papers``), while an uploaded textbook
    must be mined cover to cover (``config.pdf.library_documents`` — a 550-page book
    keeps its chapter-12 figures; see docs/bugs.md, the Sarsa(λ) incident).

    Args:
        path: Filesystem path to the PDF.
        max_floats: Stop after this many mined floats.
        max_pages: Scan at most this many pages.

    Returns:
        Up to ``max_floats`` dicts, in page order:
        ``{"kind": "figure"|"table"|"algorithm", "page": 1-based page number,
        "caption": str, "region": [x0, y0, x1, y1]}``. The region covers the
        content for figures and content+caption for tables/algorithms (whose
        captions are part of the float's visual identity), ready for
        ``render_float``. Unparseable files yield ``[]`` (never raise) —
        figures are a nicety, not the read.
    """
    import fitz

    try:
        doc = fitz.open(path)
    except Exception:
        log.warning("pymupdf couldn't open %s", path, exc_info=True)
        return []
    found: list[dict] = []
    try:
        for page_index in range(min(doc.page_count, max_pages)):
            if len(found) >= max_floats:
                break
            page = doc.load_page(page_index)
            captions: list[tuple[fitz.Rect, str, str]] = []
            for block in page.get_text("blocks"):
                text = " ".join(str(block[4]).split())
                match = CAPTION_RE.match(text)
                if match:
                    kind = "algorithm" if match.group(2) else "figure"
                    if match.group(1) and match.group(1).lower() == "table":
                        kind = "table"
                    captions.append((fitz.Rect(block[:4]), kind, text))
            if not captions:
                continue
            rects = _content_rects(page)
            rules = _horizontal_rules(page)
            for caption_rect, kind, caption_text in captions:
                if len(found) >= max_floats:
                    break
                if kind == "algorithm":
                    region = _algorithm_region(caption_rect, rules)
                elif kind == "table":
                    region = _table_region(page, caption_rect, rects, rules)
                else:
                    region = _grab_adjacent(caption_rect, rects, above=True)
                    if region is None:
                        region = _grab_adjacent(caption_rect, rects, above=False)
                if region is None:
                    continue
                clip = region if kind == "figure" else region | caption_rect
                clip = (clip + (-_PAD, -_PAD, _PAD, _PAD)) & page.rect
                if clip.is_empty:
                    continue
                found.append(
                    {
                        "kind": kind,
                        "page": page_index + 1,
                        "caption": caption_text[:_MAX_CAPTION],
                        "region": [clip.x0, clip.y0, clip.x1, clip.y1],
                    }
                )
    except Exception:
        log.warning("float mining failed for %s", path, exc_info=True)
    finally:
        doc.close()
    return found


def render_float(path: str | Path, page_number: int, region: list[float]) -> bytes:
    """Render one manifest entry's page region to PNG bytes.

    Args:
        path: Filesystem path to the PDF.
        page_number: The float's 1-based page number (as from
            ``extract_floats``).
        region: The float's ``[x0, y0, x1, y1]`` region on that page.

    Returns:
        PNG bytes rendered at ``config.pdf.render_dpi``.

    Raises:
        PdfError: When the page or region is invalid or rendering fails.
    """
    import fitz

    try:
        doc = fitz.open(path)
    except Exception as exc:
        raise PdfError(f"pymupdf couldn't open {path}") from exc
    try:
        if not 1 <= page_number <= doc.page_count:
            raise PdfError(f"page {page_number} out of range for {path}")
        page = doc.load_page(page_number - 1)
        clip = fitz.Rect(region) & page.rect
        if clip.is_empty:
            raise PdfError(f"empty render region {region} on page {page_number}")
        pixmap = page.get_pixmap(clip=clip, dpi=config.pdf.render_dpi)
        return pixmap.tobytes("png")
    except PdfError:
        raise
    except Exception as exc:
        raise PdfError(f"couldn't render page {page_number} of {path}") from exc
    finally:
        doc.close()
