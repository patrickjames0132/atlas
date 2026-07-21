"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
Full paper text from ar5iv, for the agentic teacher to read into context.

Semantic Scholar gives abstracts + TL;DRs; when the Q&A agent needs specifics
(methods, results, numbers) it reads the full text. We reuse the ar5iv fetch that
``figures.py`` already relies on (arXiv's LaTeX→HTML render), strip the body to
readable text, and cache it in SQLite (same thin cache as graph snapshots).

Only papers with an arXiv id and an ar5iv render have full text; everything else
falls back to the abstract (handled by the caller). The extracted text is cached
whole; the caller truncates to a char budget at read time.

Equations survive: ar5iv carries each formula's source LaTeX in the MathML
``alttext``, and the reader lifts it inline as ``$…$`` / ``$$…$$`` (``keep_math``)
so a reader — the researcher, and the seed-reading intuition lecture — can quote a
paper's actual math, which the frontend renders with KaTeX.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

from html.parser import HTMLParser

from ...storage import cache
from . import client

# Block-level tags whose text we keep (paragraphs, headings, list items).
_TEXT_TAGS = {"p", "h1", "h2", "h3", "h4", "h5", "h6", "li"}
# Subtrees to drop entirely: these aren't body text. ``math`` is handled
# separately (``_TextParser`` either drops it or lifts its LaTeX out, per
# ``keep_math``) — its noisy MathML subtree is always suppressed either way.
_SKIP_TAGS = {"script", "style", "figure", "nav", "cite"}


class _TextParser(HTMLParser):
    """Collect readable body text: the text of each block-level element, with
    scripts / figures / citations dropped. Blocks join with blank lines. Math
    is either dropped or lifted out as LaTeX (see ``keep_math``); its MathML
    subtree is always suppressed so the formula's markup never leaks into prose.
    """

    def __init__(self, keep_math: bool = False) -> None:
        """Set up empty block/depth accumulators.

        Args:
            keep_math: When True, a ``<math>`` element's ``alttext`` LaTeX is
                emitted (delimited) in place of the dropped formula.
        """
        super().__init__(convert_charrefs=True)
        self.blocks: list[str] = []
        self._in_text = 0  # depth inside a kept block tag
        self._skip = 0  # depth inside a dropped subtree
        self._cur: list[str] = []
        self._keep_math = keep_math

    def handle_starttag(self, tag: str, attrs: list) -> None:
        """Open a kept block, a skipped subtree, or a math formula.

        Args:
            tag: The tag name.
            attrs: The tag's attributes (read for a ``<math>``'s ``alttext``).
        """
        if tag == "math":
            # ar5iv renders every formula as MathML carrying the source LaTeX in
            # `alttext`. When keeping math we lift that LaTeX into the paragraph
            # (delimited for KaTeX) — `$$` for a displayed equation, `$` inline —
            # while still suppressing the noisy MathML subtree below.
            if self._keep_math and self._in_text and not self._skip:
                attributes = dict(attrs)
                latex = (attributes.get("alttext") or "").strip()
                if latex:
                    fence = "$$" if attributes.get("display") == "block" else "$"
                    self._cur.append(f" {fence}{latex}{fence} ")
            self._skip += 1
        elif tag in _SKIP_TAGS:
            self._skip += 1
        elif tag in _TEXT_TAGS and not self._skip:
            self._in_text += 1

    def handle_endtag(self, tag: str) -> None:
        """Close a scope; a completed block is flushed with whitespace collapsed.

        Args:
            tag: The tag name.
        """
        if (tag == "math" or tag in _SKIP_TAGS) and self._skip:
            self._skip -= 1
        elif tag in _TEXT_TAGS and self._in_text and not self._skip:
            self._in_text -= 1
            if self._in_text == 0:
                text = " ".join("".join(self._cur).split())
                if text:
                    self.blocks.append(text)
                self._cur = []

    def handle_data(self, data: str) -> None:
        """Accumulate text while inside a kept block (and not a skipped subtree).

        Args:
            data: The raw character data.
        """
        if self._in_text and not self._skip:
            self._cur.append(data)


def html_to_text(html: str, *, keep_math: bool = False) -> str:
    """Strip an HTML document down to readable body text.

    Keeps block-level elements (paragraphs, headings, list items); drops
    scripts, figures, and citations. Shared by the ar5iv paper reader and the
    bring-your-own-sources web-page ingester (``library/sources.py``) — this
    function has nothing ar5iv-specific about it, it's generic HTML-to-text.

    Args:
        html: The full HTML document.
        keep_math: When True, a MathML ``<math>``'s ``alttext`` LaTeX is kept
            inline (fenced ``$…$`` / ``$$…$$`` for KaTeX) instead of the whole
            formula being dropped. The ar5iv reader opts in so a lecture can
            quote a paper's equations; the web-page ingester keeps the default
            (drop) since arbitrary pages carry no reliable ``alttext``.

    Returns:
        The extracted text, blocks joined by blank lines.
    """
    parser = _TextParser(keep_math=keep_math)
    parser.feed(html)
    return "\n\n".join(parser.blocks)


def get_fulltext(arxiv_id: str, *, refresh: bool = False) -> dict:
    """Fetch a paper's readable body text from ar5iv, cached.

    Args:
        arxiv_id: The paper's arXiv id (a version suffix is stripped).
        refresh: When True, bypass the cache and re-fetch from ar5iv.

    Returns:
        ``{"available": bool, "text": str}``. ``available`` is False (with
        empty text) when ar5iv has no render for the paper or the id is
        blank; misses are cached too. The text is cached whole — callers
        truncate to their own char budget at read time.

    Raises:
        urllib.error.HTTPError: On non-404 ar5iv HTTP failures.
        urllib.error.URLError: On network failures.
    """
    arxiv_id = (arxiv_id or "").strip().split("v")[0]
    if not arxiv_id:
        return {"available": False, "text": ""}

    key = f"fulltext:{arxiv_id}"
    if not refresh:
        cached = cache.get(key, client.CACHE_TTL)
        if cached is not None:
            return cached

    html = client.fetch_html(arxiv_id)
    if html is None:
        result = {"available": False, "text": ""}
        cache.set(key, result)
        return result

    result = {"available": True, "text": html_to_text(html, keep_math=True)}
    cache.set(key, result)
    return result
