"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
Pull a paper's figures + captions from its ar5iv HTML render.

Semantic Scholar gives us abstracts and TL;DRs but not a paper's figures. ar5iv
(https://ar5iv.org) renders arXiv LaTeX to HTML whose ``<figure>`` elements carry
both the image and the paper's own ``<figcaption>`` — exactly the "figure + its
real caption" we want under the TL;DR in the detail panel.

We extract ``[{image, caption}]`` for figures that actually have an image (ar5iv
also emits ``<figure class="ltx_table">`` for tables, which we skip), absolutize
the image URLs against the ar5iv host, and cache the result in SQLite (the same
thin cache as graph snapshots) — ar5iv renders are static, so a long TTL is safe.

Captions carry math as ``<math>`` elements whose children are three redundant
text renderings of each formula (presentation MathML, content MathML, LaTeX).
The parser skips that subtree and emits the element's ``alttext`` LaTeX wrapped in
``$…$`` instead, so the frontend renders it with KaTeX rather than showing tripled
soup — see ``_FigureParser``.

Not every paper is on ar5iv (LaTeX-conversion failures, PDF-only submissions);
those return ``available: False`` and the UI simply shows no figures.

Images are served to the browser via a same-origin proxy (``client.fetch_image``
+ ``client.is_ar5iv_url``, wired up by the ``/api/figure_proxy`` route) so we
don't depend on ar5iv allowing hotlinks and never expose an open proxy — only
the ar5iv host is fetchable.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

from html.parser import HTMLParser

from ...storage import cache
from . import client

_MAX_FIGS = 8
_MAX_CAPTION = 600


class _FigureParser(HTMLParser):
    r"""Collect ``{image, caption}`` for each ``<figure>`` that contains an image.

    Tracks figure nesting so a stray inner figure can't corrupt the outer one,
    grabs the first ``<img>`` in a figure as its thumbnail, and accumulates the
    ``<figcaption>`` text (tags stripped, whitespace collapsed).

    Math in captions gets special handling. ar5iv renders each formula as a
    ``<math>`` element whose *children* are presentation MathML plus content-MathML
    and LaTeX annotations — three separate text renderings of the same formula.
    Tag-stripping all of it yields garbled, tripled soup
    (``Q(s,a)=V∗(s)+ϵa`` + ``subscriptitalic-ϵa`` + ``Q(s,a)=V_{*}(s)+\epsilon_{a}``).
    Instead we skip the ``<math>`` subtree entirely and emit its ``alttext``
    attribute — the clean LaTeX source — wrapped in ``$…$`` so the frontend's KaTeX
    renders it properly.
    """

    def __init__(self) -> None:
        """Set up empty figure/caption accumulators."""
        super().__init__(convert_charrefs=True)
        self.figures: list[dict] = []
        self._depth = 0  # how deep we are in nested <figure> tags
        self._img: str | None = None
        self._cap_depth = 0  # how deep we are in <figcaption>
        self._math_depth = 0  # how deep we are in a <math> subtree
        self._cap: list[str] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        """Track figure/img/figcaption openings and swap math for its LaTeX.

        Args:
            tag: The tag name.
            attrs: The tag's attributes as (name, value) pairs.
        """
        if tag == "figure":
            self._depth += 1
            if self._depth == 1:
                self._img = None
                self._cap = []
                self._cap_depth = 0
                self._math_depth = 0
        elif tag == "img" and self._depth and self._img is None:
            src = dict(attrs).get("src")
            if src:
                self._img = src
        elif tag == "figcaption" and self._depth:
            self._cap_depth += 1
        elif tag == "math" and self._cap_depth:
            # Emit the clean LaTeX from alttext once, on entering the outermost
            # <math>; the subtree's own text (garbled tripled MathML) is then
            # suppressed by handle_data until the matching close.
            if self._math_depth == 0:
                alttext = (dict(attrs).get("alttext") or "").strip()
                if alttext:
                    self._cap.append(f"${alttext}$")
            self._math_depth += 1

    def handle_endtag(self, tag: str) -> None:
        """Close figure/figcaption/math scopes, emitting a completed figure.

        Args:
            tag: The tag name.
        """
        if tag == "math" and self._math_depth:
            self._math_depth -= 1
        elif tag == "figcaption" and self._cap_depth:
            self._cap_depth -= 1
        elif tag == "figure" and self._depth:
            if self._depth == 1 and self._img:
                caption = " ".join("".join(self._cap).split())[:_MAX_CAPTION]
                self.figures.append({"image": self._img, "caption": caption})
            self._depth -= 1

    def handle_data(self, data: str) -> None:
        """Accumulate caption text while inside a ``<figcaption>``, skipping the
        text inside a ``<math>`` subtree (its LaTeX was emitted from ``alttext``).

        Args:
            data: The raw character data.
        """
        if self._cap_depth and not self._math_depth:
            self._cap.append(data)


def _abs_url(src: str) -> str:
    """Absolutize an ar5iv-relative image src against the ar5iv host.

    Args:
        src: The raw ``src`` attribute from an ar5iv ``<img>`` — absolute,
            host-relative (``/...``), or document-relative.

    Returns:
        An absolute URL on the ar5iv host (already-absolute URLs pass through).
    """
    if src.startswith("http://") or src.startswith("https://"):
        return src
    if src.startswith("/"):
        return client.BASE_URL + src
    return f"{client.BASE_URL}/{src.lstrip('./')}"


def get_figures(arxiv_id: str, *, refresh: bool = False) -> dict:
    """Extract a paper's figures + captions from its ar5iv render, cached.

    Args:
        arxiv_id: The paper's arXiv id (a version suffix is stripped).
        refresh: When True, bypass the cache and re-fetch from ar5iv.

    Returns:
        ``{"available": bool, "figures": [{"image", "caption"}]}``. ``image``
        is an absolute ar5iv URL — the route rewrites it to the same-origin
        proxy before sending it to the browser. ``available`` is False when
        ar5iv has no render; that miss is cached too.

    Raises:
        urllib.error.HTTPError: On non-404 ar5iv HTTP failures.
        urllib.error.URLError: On network failures.
    """
    arxiv_id = (arxiv_id or "").strip().split("v")[0]
    if not arxiv_id:
        return {"available": False, "figures": []}

    key = f"figures:{arxiv_id}"
    if not refresh:
        cached = cache.get(key, client.CACHE_TTL)
        if cached is not None:
            return cached

    html = client.fetch_html(arxiv_id)
    if html is None:
        result = {"available": False, "figures": []}
        cache.set(key, result)
        return result

    parser = _FigureParser()
    parser.feed(html)
    figures = [
        {"image": _abs_url(figure["image"]), "caption": figure["caption"]}
        for figure in parser.figures[:_MAX_FIGS]
    ]
    result = {"available": True, "figures": figures}
    cache.set(key, result)
    return result
