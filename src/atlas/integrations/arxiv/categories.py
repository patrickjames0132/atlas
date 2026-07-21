"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
Fetch a paper's OWN per-id metadata from arXiv's export API — its category
tags and its title.

Semantic Scholar gives us abstracts and TL;DRs but not a paper's arXiv category
codes (``cs.LG``, ``math.PR``, …) — only arXiv itself has those. arXiv's export
API (https://export.arxiv.org/api/query, an Atom feed built for exactly this
kind of per-id metadata lookup) returns them as ``<category term="...">``
elements on the paper's ``<entry>``, alongside its ``<title>``. We label each
code via ``vocab.name_for`` and cache the result in SQLite (the same thin cache
as graph snapshots, figures, and code links).

The title lookup (:func:`get_title`) shares the same fetch and serves a
different consumer: OpenAlex seed resolution, which falls back to a title
search when a bare arXiv id doesn't resolve through the arXiv-minted DOI (a
published paper's canonical OpenAlex record isn't aliased to it — e.g. AIAYN).

Not every id resolves — a malformed or since-withdrawn id comes back as a feed
with no ``<entry>`` at all (HTTP 200, not 404); that's ``available: False``,
same as ar5iv's own "no render" miss, and cached the same way.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from ...config import config
from ...storage import cache
from . import vocab

EXPORT_HOST = "export.arxiv.org"
BASE_URL = f"https://{EXPORT_HOST}/api/query"
# A distinct UA from client.py's — that one's ar5iv-specific; this hits arXiv's
# own export API, a different host entirely.
_USER_AGENT = {"User-Agent": "atlas/1.1 (https://github.com/patrickjames0132/arxiv-digest)"}
# A paper's categories are essentially permanent (arXiv allows cross-listing
# changes, but they're rare and non-urgent) — cache as long as figures/code.
CACHE_TTL = 60 * 60 * 24 * 30

_ATOM_NS = "{http://www.w3.org/2005/Atom}"


def _fetch_entry(arxiv_id: str) -> ET.Element | None:
    """Fetch a paper's ``<entry>`` element from arXiv's export API.

    The shared fetch behind :func:`fetch_categories` and :func:`get_title` — one
    id lookup, parsed to its Atom entry.

    Args:
        arxiv_id: A bare arXiv id (version already stripped).

    Returns:
        The paper's ``<entry>`` element, or None when the feed has no entry for
        the id (bad id, or arXiv is listing nothing for it).

    Raises:
        urllib.error.HTTPError: On HTTP failures.
        urllib.error.URLError: On network failures.
        ET.ParseError: If arXiv ever returns malformed XML.
    """
    url = f"{BASE_URL}?id_list={urllib.parse.quote(arxiv_id)}"
    request = urllib.request.Request(url, headers=_USER_AGENT)
    with urllib.request.urlopen(request, timeout=config.providers.s2.timeout) as response:
        body = response.read()
    return ET.fromstring(body).find(f"{_ATOM_NS}entry")


def fetch_categories(arxiv_id: str) -> list[str] | None:
    """Fetch the raw category codes arXiv lists for a paper.

    Args:
        arxiv_id: A bare arXiv id (version already stripped).

    Returns:
        The paper's category codes in arXiv's own order (primary first), or
        None when the feed has no entry for the id (bad id, or arXiv is
        listing nothing for it).

    Raises:
        urllib.error.HTTPError: On HTTP failures.
        urllib.error.URLError: On network failures.
        ET.ParseError: If arXiv ever returns malformed XML.
    """
    entry = _fetch_entry(arxiv_id)
    if entry is None:
        return None
    return [
        term
        for category in entry.findall(f"{_ATOM_NS}category")
        if (term := category.get("term"))
    ]


def get_title(arxiv_id: str) -> str | None:
    """Fetch a paper's title from arXiv (for OpenAlex title-search fallback).

    A bare arXiv id that doesn't resolve through OpenAlex's arXiv-DOI path (a
    published paper's canonical OpenAlex record isn't aliased to the
    arXiv-minted DOI) still resolves by **title**, and arXiv is the title's
    home. Uncached — it's only hit on the rare OpenAlex-resolution miss, and the
    resulting graph snapshot is cached whole.

    Args:
        arxiv_id: The paper's arXiv id (a version suffix is stripped).

    Returns:
        The paper's title (whitespace collapsed), or None when the id is blank,
        arXiv has no entry for it, or the entry carries no title.

    Raises:
        urllib.error.HTTPError: On non-transient arXiv HTTP failures.
        urllib.error.URLError: On network failures.
    """
    arxiv_id = (arxiv_id or "").strip().split("v")[0]
    if not arxiv_id:
        return None
    entry = _fetch_entry(arxiv_id)
    if entry is None:
        return None
    title_element = entry.find(f"{_ATOM_NS}title")
    if title_element is None or not title_element.text:
        return None
    return " ".join(title_element.text.split())


def get_categories(arxiv_id: str, *, refresh: bool = False) -> dict:
    """Fetch and label a paper's own arXiv category tags, cached.

    Args:
        arxiv_id: The paper's arXiv id (a version suffix is stripped).
        refresh: When True, bypass the cache and re-fetch from arXiv.

    Returns:
        ``{"available": bool, "categories": [{"code", "name"}]}``, primary
        category first. ``name`` falls back to the bare code when arXiv has
        retired/renamed it out of the bundled taxonomy. ``available`` is
        False when arXiv has no entry for the id; that miss is cached too.
        A paper cross-listed in two codes that share one display name (the
        taxonomy has six such pairs, e.g. ``cs.LG``/``stat.ML`` — both
        "Machine Learning") only gets one tag, arXiv's first-listed code.

    Raises:
        urllib.error.HTTPError: On non-transient arXiv HTTP failures.
        urllib.error.URLError: On network failures.
    """
    arxiv_id = (arxiv_id or "").strip().split("v")[0]
    if not arxiv_id:
        return {"available": False, "categories": []}

    key = f"arxiv_categories:{arxiv_id}"
    if not refresh:
        cached = cache.get(key, CACHE_TTL)
        if cached is not None:
            return cached

    codes = fetch_categories(arxiv_id)
    if codes is None:
        result = {"available": False, "categories": []}
        cache.set(key, result)
        return result

    # Some arXiv codes are cross-listed pairs that happen to share one
    # display name (cs.LG/stat.ML both "Machine Learning") — a paper tagged
    # with both would otherwise show the same label twice. Keep the first
    # code seen per name, dropping the redundant duplicate outright.
    seen_names: set[str] = set()
    categories_out = []
    for code in codes:
        name = vocab.name_for(code) or code
        if name in seen_names:
            continue
        seen_names.add(name)
        categories_out.append({"code": code, "name": name})

    result = {"available": True, "categories": categories_out}
    cache.set(key, result)
    return result
