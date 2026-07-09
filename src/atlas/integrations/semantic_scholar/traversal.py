"""Hydrating known papers and walking the citation graph from a seed:
batch detail lookup, references, citations, and similarity recommendations.
"""

from __future__ import annotations

import datetime
import logging
import urllib.parse

from ...config import config
from . import client, nodes

log = logging.getLogger(__name__)

_BATCH_MAX = 500  # S2 caps /paper/batch at 500 ids per call.

# S2's /citations and /references endpoints take no `sort` param — they come
# back in whatever order S2's index has them, which in practice skews toward
# the most recently ingested (i.e. most recently published) neighbor, not the
# most cited one. For a heavily-cited seed, that means a small `limit` fills
# up entirely with this year's obscure citing papers before a single famous,
# decades-old citing paper is ever seen. So we over-fetch up to this many
# candidates in one call (S2 accepts it; still one request) and rank locally
# by citation count before trimming to the caller's `limit`. Also the page
# size for deep paging (below): S2's max per-request `limit`.
_RANK_POOL = 1000

# Deepest offset a citations page may request. S2 rejects offset+limit past
# ~10k, so with a 1000-id page the last servable window is offset 9000
# (9000+1000 = 10000). Deep paging stops here; anything older is only
# reachable via landmark mining.
_MAX_OFFSET = 9000

# The "latest" citation window: a citer whose publication date falls within
# this many months of today is the recent *frontier* (its own graph relation),
# not a historic landmark. A rolling window, not a calendar year, so it stays
# populated year-round (a hard "current year" cut is near-empty every January).
_LATEST_WINDOW_MONTHS = 12
# Citation traversal here is the FALLBACK path: since v4.0.0 the primary
# landmark/latest source is OpenAlex (``integrations/openalex``), whose sorted
# ``cites:`` queries need no mining. This module runs only when OpenAlex can't
# resolve a seed — so it keeps deep paging (fill the latest window + reachable
# mid band) but the reference-list mining/verification apparatus is gone.


def get_papers(paper_ids: list[str], fields: str = nodes.DETAIL_FIELDS) -> dict[str, dict]:
    """Hydrate paper details for many ids via ``POST /paper/batch``.

    The batch endpoint is used deliberately: the single-paper GET 429s almost
    immediately unauthenticated, while batch is lenient and bulk-friendly.

    Args:
        paper_ids: S2 paperIds or prefixed ids like ``ARXIV:1706.03762``.
            Falsy entries are dropped. Chunked to respect the 500-id batch cap.
        fields: Comma-separated S2 field list to request.

    Returns:
        A map of the *requested* id to its normalized node dict. Ids S2 can't
        resolve are omitted.

    Raises:
        client.S2Error: When a batch request fails after retries.
    """
    paper_ids = [paper_id for paper_id in paper_ids if paper_id]
    if not paper_ids:
        return {}
    out: dict[str, dict] = {}
    url = f"{config.s2.graph_url}/paper/batch?fields={urllib.parse.quote(fields)}"
    for start in range(0, len(paper_ids), _BATCH_MAX):
        chunk = paper_ids[start : start + _BATCH_MAX]
        data = client.request(url, method="POST", body={"ids": chunk})
        # S2 returns a list aligned to the input ids, with null for unknowns
        # (anything else — request() types its JSON as object — means no rows).
        papers = data if isinstance(data, list) else []
        for requested_id, paper in zip(chunk, papers):
            node = nodes.node(paper)
            if node:
                out[requested_id] = node
    return out


def get_paper(paper_id: str) -> dict | None:
    """Fetch details for a single paper.

    Args:
        paper_id: An S2 paperId or a prefixed id like ``ARXIV:1706.03762``.

    Returns:
        The normalized node dict, or None when S2 has no such paper.

    Raises:
        client.S2Error: When the underlying batch request fails after retries.
    """
    return get_papers([paper_id]).get(paper_id)


def _influence(entry: dict) -> int:
    """The citation count of a neighbor entry (0 when S2 reports none) — the
    proxy for how landmark a paper is, and the within-pool ranking key."""
    return entry["node"].get("citation_count") or 0


def _select_by_influence(entries: list[dict], limit: int | None) -> list[dict]:
    """Keep the most-cited entries, most-cited first (the references default).

    ``limit=None`` keeps them all (an unbounded relation — the config ship count
    set to ``null``); ``[:None]`` is the whole list.
    """
    return sorted(entries, key=_influence, reverse=True)[:limit]


def _latest_cutoff() -> str:
    """The ISO date bound for the "latest" window: today minus
    ``_LATEST_WINDOW_MONTHS``, as ``YYYY-MM-DD``.

    Returned as a string, not a ``date``, because S2 publication dates are
    ``YYYY-MM-DD`` strings compared lexicographically (ISO dates sort
    chronologically as text), which also sidesteps month-arithmetic edge cases
    like a Feb-29 today.
    """
    today = datetime.date.today()
    months = today.year * 12 + (today.month - 1) - _LATEST_WINDOW_MONTHS
    return f"{months // 12:04d}-{months % 12 + 1:02d}-{today.day:02d}"


def _is_latest(entry: dict, cutoff: str) -> bool:
    """Whether a citer falls in the recent "latest" window.

    True only when the node has a ``pub_date`` at or after ``cutoff``. A citer
    with no publication date can't be placed in the rolling window, so it
    competes as a historic ``citation`` rather than being guessed into
    ``latest``.
    """
    pub_date = entry["node"].get("pub_date")
    return bool(pub_date) and pub_date >= cutoff


def _fetch_page(path: str, key: str, limit: int, offset: int = 0) -> list[dict]:
    """Fetch one page of references/citations as normalized entries.

    Args:
        path: The endpoint path under ``/paper/`` (quoted id + relation).
        key: The nested paper key — ``"citedPaper"`` or ``"citingPaper"``.
        limit: Page size to request.
        offset: Where to start in S2's (newest-first) list.

    Returns:
        ``[{"node": <node dict>, "influential": bool}]`` entries, skipping
        papers S2 couldn't resolve.

    Raises:
        client.S2Error: When the request fails after retries.
    """
    url = (
        f"{config.s2.graph_url}/paper/{path}"
        f"?fields={urllib.parse.quote(nodes.NEIGHBOR_FIELDS)}&limit={limit}&offset={offset}"
    )
    data = client.request(url)
    entries: list[dict] = []
    for item in (data.get("data") or []) if isinstance(data, dict) else []:
        node = nodes.node(item.get(key))
        if node:
            entries.append({"node": node, "influential": bool(item.get("isInfluential"))})
    return entries


def _neighbors(path: str, key: str, limit: int | None) -> list[dict]:
    """Fetch one over-fetched page and keep the most-cited entries.

    The references selection: fetch a pool of ``_RANK_POOL`` (S2 offers no
    server-side sorting and its default order skews to the most recent neighbor,
    not the most cited — and one page is the whole list, since a reference list
    fits), rank it by citation count, and trim to ``limit`` (``None`` keeps them
    all). No landmark/latest split or mining, unlike ``citations``.

    Args:
        path: The endpoint path under ``/paper/`` (quoted id + relation).
        key: The nested paper key — ``"citedPaper"`` or ``"citingPaper"``.
        limit: Maximum neighbors to return, or ``None`` for all fetched.

    Returns:
        A list of ``{"node": <node dict>, "influential": bool}`` entries,
        most-cited first.

    Raises:
        client.S2Error: When the request fails after retries.
    """
    pool = _fetch_page(path, key, _RANK_POOL)
    return _select_by_influence(pool, limit)


def references(paper_id: str, limit: int | None) -> list[dict]:
    """Fetch the papers this one CITES (its intellectual ancestors).

    Args:
        paper_id: An S2 paperId or prefixed id.
        limit: Maximum references to return, or ``None`` for all fetched.

    Returns:
        A list of ``{"node": <node dict>, "influential": bool}`` entries.

    Raises:
        client.S2Error: When the request fails after retries.
    """
    return _neighbors(f"{client.quote(paper_id)}/references", "citedPaper", limit)


def _fetch_citers(paper_id: str, *, deep: bool) -> list[dict]:
    """Fetch the reachable citer pool, newest-first, deduped.

    ``deep=False`` (graph expansion) is a single newest page — the recent tip.
    ``deep=True`` (the seed build) pages S2's newest-first citation list until
    the whole rolling ``latest`` window is captured: it keeps fetching 1000-id
    pages (offset 0, 1000, 2000, …) and stops once a page holds NO in-window
    citer (so the window boundary is behind us), the list runs out, or the
    ``_MAX_OFFSET`` ceiling is hit. For a hyper-cited seed whose newest 1000
    citers are all inside the window, that means paging deep — up to ~10k
    citers — which is the point: it both completes ``latest`` and surfaces the
    mid-era citers just past the boundary (the landmark "middle band" one page
    overshoots).

    Args:
        paper_id: An S2 paperId or prefixed id.
        deep: Page to the window boundary/ceiling (seed build) vs. one page.

    Returns:
        The deduped ``[{"node", "influential"}]`` pool, newest-first.

    Raises:
        client.S2Error: When the *newest* page (offset 0) fails — a real
            outage. A deeper page S2 rejects is swallowed (degrade to the
            range reached), matching the offset-ceiling reality.
    """
    path = f"{client.quote(paper_id)}/citations"
    if not deep:
        return _fetch_page(path, "citingPaper", _RANK_POOL)

    cutoff = _latest_cutoff()
    pool: list[dict] = []
    seen: set[str] = set()
    offset = 0
    while True:
        try:
            page = _fetch_page(path, "citingPaper", _RANK_POOL, offset=offset)
        except client.S2Error:
            if offset == 0:
                raise  # the newest page failing is an outage, not a deep-window skip
            break  # a page past the ceiling / list end S2 won't serve — take what we have
        if not page:
            break  # ran off the end of the citation list
        for entry in page:
            paper = entry["node"]["id"]
            if paper not in seen:
                seen.add(paper)
                pool.append(entry)
        # Newest-first: once a page holds no in-window citer, the rolling window
        # is fully behind us — stop. Otherwise keep paging (bounded by the ceiling).
        if not any(_is_latest(entry, cutoff) for entry in page):
            break
        offset += _RANK_POOL
        if offset > _MAX_OFFSET:
            break
    return pool


def citations(paper_id: str, limit: int) -> list[dict]:
    """Fetch the papers that CITE this one, most-cited first (its landmarks).

    The single-relation view used by on-demand graph expansion: one newest page
    (no deep paging — expansion wants the tip, fast), ranked by citation count.
    The seed-build path instead calls ``citation_relations``, which pages to the
    latest-window boundary and splits the pool into landmark vs recent
    (``latest``) citers.

    This is the FALLBACK for when OpenAlex can't resolve a seed — the primary
    landmark source is now ``integrations/openalex``.

    Args:
        paper_id: An S2 paperId or prefixed id.
        limit: Maximum citations to return.

    Returns:
        A list of ``{"node": <node dict>, "influential": bool}`` entries,
        most-cited first.

    Raises:
        client.S2Error: When the request fails after retries.
    """
    return _select_by_influence(_fetch_citers(paper_id, deep=False), limit)


def citation_relations(
    paper_id: str,
    *,
    landmark_limit: int | None,
    latest_limit: int | None,
) -> tuple[list[dict], list[dict]]:
    """Split a seed's citers into two relations: landmarks and the latest frontier.

    The FALLBACK path (used only when OpenAlex can't resolve the seed). The citer
    pool is paged to the latest-window boundary (``_fetch_citers`` with
    ``deep=True``) then partitioned by publication date: citers inside the
    rolling ``_LATEST_WINDOW_MONTHS`` window are the recent **frontier**
    (``latest``, shipped oldest-first so the reveal slider walks toward the
    present; a limit keeps the newest), and everything older competes as a
    historic **landmark** (``citation``, most-cited first). Deep paging means ``latest``
    covers the whole window (not just the newest page) and the citers just past
    the boundary fill the landmark middle band. The two are disjoint, so a
    recent-but-highly-cited paper shows once, as ``latest``. Without OpenAlex's
    sorted ``cites:`` queries this path is recency-biased past the ~10k offset
    ceiling — acceptable for the rare resolution miss it now serves.

    Args:
        paper_id: An S2 paperId or prefixed id.
        landmark_limit: Maximum landmark (historic) citers to return, or ``None``
            for all (the whole deep-paged older pool).
        latest_limit: Maximum recent-frontier citers to return, or ``None`` for all.

    Returns:
        ``(landmark_entries, latest_entries)`` — each ``[{"node", "influential"}]``.

    Raises:
        client.S2Error: When the request fails after retries.
    """
    pool = _fetch_citers(paper_id, deep=True)
    cutoff = _latest_cutoff()
    recent = [entry for entry in pool if _is_latest(entry, cutoff)]
    older = [entry for entry in pool if not _is_latest(entry, cutoff)]
    # Latest: selected newest-first by publication date (a limit keeps the
    # newest N) then flipped oldest-first to match the OpenAlex path — the
    # frontend's reveal slider walks toward the present. Landmark: most-cited
    # first.
    latest = sorted(recent, key=lambda entry: entry["node"].get("pub_date") or "", reverse=True)
    latest = latest[:latest_limit]
    latest.reverse()
    return _select_by_influence(older, landmark_limit), latest


def recommendations(paper_id: str, limit: int | None, pool: str | None = None) -> list[dict]:
    """Fetch embedding-based related papers (similarity neighbors).

    Args:
        paper_id: An S2 paperId or prefixed id.
        limit: Maximum recommendations to return, or ``None`` for as many as S2
            will give (its ``/recommendations`` page maxes at 500).
        pool: The candidate set — ``"all-cs"`` or ``"recent"``. Defaults to
            ``config.graph.recs_pool`` (``all-cs``; the ``recent`` pool
            returns nothing for older seeds).

    Returns:
        A list of ``{"node": <node dict>}`` entries (no influence flag — the
        recommendations endpoint doesn't report one).

    Raises:
        client.S2Error: When the request fails after retries.
    """
    pool = pool or config.graph.recs_pool
    # The recs endpoint needs a concrete page size; None ("unbounded") asks for
    # S2's maximum, 500.
    page = limit if limit is not None else 500
    url = (
        f"{config.s2.recs_url}/papers/forpaper/{client.quote(paper_id)}"
        f"?fields={urllib.parse.quote(nodes.NEIGHBOR_FIELDS)}&limit={page}&from={pool}"
    )
    data = client.request(url)
    recommended_papers = data.get("recommendedPapers") if isinstance(data, dict) else None
    return nodes.from_papers(recommended_papers or [])
