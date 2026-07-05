"""Shared HTTP transport for ar5iv (arXiv's LaTeX→HTML renderer).

``figures.py`` and ``fulltext.py`` each extract something different from the
same ar5iv HTML render, so the raw fetch (and its cache TTL) live here once
instead of one module reaching into the other's internals.
"""

from __future__ import annotations

import urllib.error
import urllib.parse
import urllib.request

from ...config import config

AR5IV_HOST = "ar5iv.labs.arxiv.org"
BASE_URL = f"https://{AR5IV_HOST}"
_USER_AGENT = {"User-Agent": "arxiv-atlas/1.1 (https://github.com/patrickjames0132/arxiv-digest)"}
# ar5iv renders are static; cache figures/fulltext (and "not available" misses)
# for a month. Bump `refresh` on the caller to force a re-fetch.
CACHE_TTL = 60 * 60 * 24 * 30


def fetch_html(arxiv_id: str) -> str | None:
    """Fetch the ar5iv HTML render for a paper.

    Args:
        arxiv_id: A bare arXiv id (version already stripped).

    Returns:
        The decoded HTML document, or None when ar5iv has no render for the
        paper (HTTP 404 — LaTeX-conversion failure or PDF-only submission).

    Raises:
        urllib.error.HTTPError: On non-404 HTTP failures.
        urllib.error.URLError: On network failures.
    """
    url = f"{BASE_URL}/html/{urllib.parse.quote(arxiv_id)}"
    request = urllib.request.Request(url, headers=_USER_AGENT)
    try:
        with urllib.request.urlopen(request, timeout=config.s2.timeout) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            return response.read().decode(charset, "replace")
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise


def is_ar5iv_url(url: str) -> bool:
    """Check a URL against the figure proxy's allowlist.

    Args:
        url: The URL the browser asked the proxy to fetch.

    Returns:
        True only for https URLs on the ar5iv host — anything else is refused
        so the proxy can't be abused as an open relay (SSRF).
    """
    try:
        parts = urllib.parse.urlparse(url)
    except ValueError:
        return False
    return parts.scheme == "https" and parts.netloc == AR5IV_HOST


def fetch_image(url: str) -> tuple[bytes, str]:
    """Fetch an ar5iv image for the same-origin proxy.

    The caller must allowlist the URL with ``is_ar5iv_url`` first — this
    function fetches whatever it's given.

    Args:
        url: An absolute ar5iv image URL.

    Returns:
        A ``(bytes, content_type)`` tuple; the content type falls back to
        ``image/png`` when ar5iv doesn't declare one.

    Raises:
        urllib.error.HTTPError: On HTTP failures.
        urllib.error.URLError: On network failures.
    """
    request = urllib.request.Request(url, headers=_USER_AGENT)
    with urllib.request.urlopen(request, timeout=config.s2.timeout) as response:
        return response.read(), response.headers.get_content_type() or "image/png"
