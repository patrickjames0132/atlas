"""Full paper text from ar5iv, for the agentic teacher to read into context.

Semantic Scholar gives abstracts + TL;DRs; when the Q&A agent needs specifics
(methods, results, numbers) it reads the full text. We reuse the ar5iv fetch that
``figures.py`` already relies on (arXiv's LaTeX→HTML render), strip the body to
readable text, and cache it in SQLite (same thin cache as graph snapshots).

Only papers with an arXiv id and an ar5iv render have full text; everything else
falls back to the abstract (handled by the caller). The extracted text is cached
whole; the caller truncates to a char budget at read time.
"""

from __future__ import annotations

from html.parser import HTMLParser

from ...storage import cache
from . import client

# Block-level tags whose text we keep (paragraphs, headings, list items).
_TEXT_TAGS = {"p", "h1", "h2", "h3", "h4", "h5", "h6", "li"}
# Subtrees to drop entirely: math renders as noisy markup, and these aren't body.
_SKIP_TAGS = {"math", "script", "style", "figure", "nav", "cite"}


class _TextParser(HTMLParser):
    """Collect readable body text: the text of each block-level element, with
    math / scripts / figures / citations dropped. Blocks join with blank lines."""

    def __init__(self) -> None:
        """Set up empty block/depth accumulators.

        Returns:
            None.
        """
        super().__init__(convert_charrefs=True)
        self.blocks: list[str] = []
        self._in_text = 0  # depth inside a kept block tag
        self._skip = 0  # depth inside a dropped subtree
        self._cur: list[str] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        """Open a kept block or a skipped subtree.

        Args:
            tag: The tag name.
            attrs: The tag's attributes (unused).
        """
        if tag in _SKIP_TAGS:
            self._skip += 1
        elif tag in _TEXT_TAGS and not self._skip:
            self._in_text += 1

    def handle_endtag(self, tag: str) -> None:
        """Close a scope; a completed block is flushed with whitespace collapsed.

        Args:
            tag: The tag name.
        """
        if tag in _SKIP_TAGS and self._skip:
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


def html_to_text(html: str) -> str:
    """Strip an HTML document down to readable body text.

    Keeps block-level elements (paragraphs, headings, list items); drops math,
    scripts, figures, and citations. Shared by the ar5iv paper reader and the
    bring-your-own-sources web-page ingester (``library/sources.py``) — this
    function has nothing ar5iv-specific about it, it's generic HTML-to-text.

    Args:
        html: The full HTML document.

    Returns:
        The extracted text, blocks joined by blank lines.
    """
    parser = _TextParser()
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

    result = {"available": True, "text": html_to_text(html)}
    cache.set(key, result)
    return result
