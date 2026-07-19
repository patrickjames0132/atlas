"""Where a paper's open-access PDF lives — resolved once, cached, shared.

Three tiers, cheapest first:

* An **arXiv id** needs no lookup at all: ``arxiv.org/pdf/<id>`` is always
  open access (used when ar5iv has no render to mine instead).
* A **known URL** (a node hydrated with ``oa_pdf`` in hand) is cached for
  later callers via ``prime`` — the detail route primes on hydration so the
  figures route that fires moments later doesn't re-ask the provider.
* Otherwise the **provider** is asked (S2's ``openAccessPdf`` / OpenAlex's
  location ``pdf_url``, both surfaced as the node dict's ``oa_pdf``), and the
  answer — including "this paper has no OA PDF" — is cached for a month so
  repeat reads and panel opens cost nothing.
"""

from __future__ import annotations

import logging

from ...integrations import openalex
from ...integrations import semantic_scholar as s2
from ...storage import cache
from ..graph import Provider

log = logging.getLogger(__name__)

# OA status changes about as slowly as citation data; a month matches the
# mined-content TTL so the whole pipeline expires together.
CACHE_TTL = 60 * 60 * 24 * 30


def arxiv_pdf_url(arxiv_id: str) -> str:
    """The always-open-access PDF URL for an arXiv paper.

    Args:
        arxiv_id: A bare arXiv id (version suffix fine).

    Returns:
        The ``arxiv.org/pdf`` URL.
    """
    return f"https://arxiv.org/pdf/{arxiv_id}"


def _cache_key(node_id: str) -> str:
    """The cache key for one node's resolved OA-PDF URL.

    Args:
        node_id: The paper's provider node id.

    Returns:
        The cache key.
    """
    return f"oa_pdf:{node_id}"


def prime(node_id: str, oa_pdf: str | None) -> None:
    """Record a node's OA-PDF URL learned as a side effect of hydration.

    Args:
        node_id: The paper's provider node id.
        oa_pdf: The URL, or None ("no OA PDF" is worth caching too).

    Returns:
        None.
    """
    cache.set(_cache_key(node_id), {"url": oa_pdf})


def resolve_oa_pdf(node_id: str, provider: Provider) -> str | None:
    """The node's open-access PDF URL, from cache or the graph's provider.

    Args:
        node_id: The paper's provider node id (an S2 paperId, or an
            S2-resolvable ``DOI:``/``ARXIV:``/``W…`` id from OpenAlex).
        provider: Which backend to ask on a cache miss — the same one the
            graph was built from, like every other hydration.

    Returns:
        The URL, or None when the paper has no known OA PDF (or the provider
        lookup failed — logged, cached only when the provider answered).
    """
    cached = cache.get(_cache_key(node_id), CACHE_TTL)
    if isinstance(cached, dict):
        url = cached.get("url")
        return url if isinstance(url, str) and url else None
    try:
        if provider == "openalex":
            node = openalex.get_paper(node_id)
        else:
            node = s2.get_paper(node_id)
    except (s2.S2Error, openalex.OpenAlexError) as exc:
        # Not cached: a transient provider failure shouldn't pin "no PDF"
        # onto this paper for a month.
        log.warning("OA-PDF resolution failed for %s (%s): %s", node_id, provider, exc)
        return None
    oa_pdf = (node or {}).get("oa_pdf")
    oa_pdf = oa_pdf if isinstance(oa_pdf, str) and oa_pdf else None
    prime(node_id, oa_pdf)
    return oa_pdf
