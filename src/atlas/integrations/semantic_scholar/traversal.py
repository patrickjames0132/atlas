"""Hydrating known papers and walking the citation graph from a seed:
batch detail lookup, references, citations, and similarity recommendations.
"""

from __future__ import annotations

import urllib.parse
from collections import defaultdict

from ...config import config
from . import client, nodes

_BATCH_MAX = 500  # S2 caps /paper/batch at 500 ids per call.

# S2's /citations and /references endpoints take no `sort` param — they come
# back in whatever order S2's index has them, which in practice skews toward
# the most recently ingested (i.e. most recently published) neighbor, not the
# most cited one. For a heavily-cited seed, that means a small `limit` fills
# up entirely with this year's obscure citing papers before a single famous,
# decades-old citing paper is ever seen. So we over-fetch up to this many
# candidates in one call (S2 accepts it; still one request) and rank locally
# by citation count before trimming to the caller's `limit`.
_RANK_POOL = 1000

# Stratified sampling for the citation pool. A single page is S2's *newest*
# citing papers (offset 0), so for a mega-cited seed the whole pool is one
# recent slice and there's nothing older to spread across. When a seed has
# more citations than fit in one page, we instead sample several offset
# windows spanning S2's newest->oldest citation list, so the pool covers the
# paper's whole descendant era. ``_MAX_OFFSET`` is S2's practical ceiling (it
# rejects offset+limit past ~10k); windows it won't serve are skipped, so we
# degrade to whatever range we could reach.
_STRATA = 5
_STRATUM_LIMIT = 200
_MAX_OFFSET = 9000


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


def _select_by_influence(entries: list[dict], limit: int) -> list[dict]:
    """Keep the most-cited entries, most-cited first (the references default)."""
    return sorted(entries, key=_influence, reverse=True)[:limit]


def _select_even_by_year(entries: list[dict], limit: int) -> list[dict]:
    """Spread the budget across publication years, most-cited within each.

    Instead of the global top-``limit`` (which clumps in whichever years the
    field was most active), bucket the pool by year and round-robin across the
    buckets — each round takes the next most-cited paper from every year — so
    the selection is spread across the paper's whole descendant timeline. The
    fixed budget self-distributes: sparse years contribute what little they
    have, dense years keep filling in later rounds, and no single year
    dominates. Undated papers sort last (only filled once every year is).

    (Only spreads across the years *present in the pool* — hence the
    stratified offset sampling in ``_stratified_pool`` for seeds whose
    citation list overflows a single ``_RANK_POOL`` page.)
    """
    buckets: dict[int | None, list[dict]] = defaultdict(list)
    for entry in entries:
        buckets[entry["node"].get("year")].append(entry)
    for bucket in buckets.values():
        bucket.sort(key=_influence, reverse=True)
    # Years oldest-first (so the earliest descendants are represented before
    # the budget runs out); undated papers last.
    years: list[int | None] = []
    years.extend(sorted(year for year in buckets if year is not None))
    if None in buckets:
        years.append(None)

    selected: list[dict] = []
    depth = 0
    while len(selected) < limit and any(len(buckets[year]) > depth for year in years):
        for year in years:
            if depth < len(buckets[year]):
                selected.append(buckets[year][depth])
                if len(selected) >= limit:
                    break
        depth += 1
    return selected


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


def _stratified_pool(path: str, key: str, total_count: int) -> list[dict]:
    """Sample offset windows across S2's citation list to span its full range.

    S2 returns citing papers newest-first, so one page is only the recent tip.
    To let ``_select_even_by_year`` reach a mega-cited seed's older
    descendants, sample ``_STRATA`` evenly-spaced offset windows from newest
    (offset 0) to the oldest reachable (bounded by ``_MAX_OFFSET``), deduped.

    Args:
        path: The endpoint path (quoted id + ``/citations``).
        key: The nested paper key (``"citingPaper"``).
        total_count: The seed's citation count, used to space the windows.

    Returns:
        The combined, deduped pool of entries.

    Raises:
        client.S2Error: When the *newest* window (offset 0) fails — that's a
            real outage, not a too-deep offset. Deeper windows S2 rejects (past
            the offset ceiling / the end of the list) are skipped, degrading to
            whatever range was reachable.
    """
    reach = min(total_count, _MAX_OFFSET + _STRATUM_LIMIT)
    span = max(reach - _STRATUM_LIMIT, 0)
    offsets = sorted({span * stratum // (_STRATA - 1) for stratum in range(_STRATA)})
    pool: list[dict] = []
    seen: set[str] = set()
    for index, offset in enumerate(offsets):
        try:
            page = _fetch_page(path, key, _STRATUM_LIMIT, offset=offset)
        except client.S2Error:
            if index == 0:
                raise  # the newest window failing is an outage, not a skip
            continue  # a deep window S2 won't serve — take the range we reached
        for entry in page:
            paper_id = entry["node"]["id"]
            if paper_id not in seen:
                seen.add(paper_id)
                pool.append(entry)
    return pool


def _neighbors(path: str, key: str, limit: int) -> list[dict]:
    """Fetch one over-fetched page and keep the most-cited entries.

    The references selection: over-fetch a pool of ``_RANK_POOL`` (S2 offers
    no server-side sorting and its default order skews to the most recent
    neighbor, not the most cited) and rank it by citation count before
    trimming to ``limit``. (A reference list is small enough that one page IS
    the whole list, and it's naturally spread across years already — so no
    even-by-year pass here, unlike ``citations``.)

    Args:
        path: The endpoint path under ``/paper/`` (quoted id + relation).
        key: The nested paper key — ``"citedPaper"`` or ``"citingPaper"``.
        limit: Maximum neighbors to return.

    Returns:
        A list of ``{"node": <node dict>, "influential": bool}`` entries,
        most-cited first.

    Raises:
        client.S2Error: When the request fails after retries.
    """
    pool = _fetch_page(path, key, max(limit, _RANK_POOL))
    return _select_by_influence(pool, limit)


def references(paper_id: str, limit: int) -> list[dict]:
    """Fetch the papers this one CITES (its intellectual ancestors).

    Args:
        paper_id: An S2 paperId or prefixed id.
        limit: Maximum references to return.

    Returns:
        A list of ``{"node": <node dict>, "influential": bool}`` entries.

    Raises:
        client.S2Error: When the request fails after retries.
    """
    return _neighbors(f"{client.quote(paper_id)}/references", "citedPaper", limit)


def citations(paper_id: str, limit: int, *, total_count: int | None = None) -> list[dict]:
    """Fetch the papers that CITE this one (its descendants).

    The selection is *even by year*: the most-cited citing papers within each
    publication year, spread across the paper's whole descendant timeline (see
    ``_select_even_by_year``) — not the global most-cited, which clumps in the
    field's busiest years, and not S2's raw order, which is just the newest.

    Args:
        paper_id: An S2 paperId or prefixed id.
        limit: Maximum citations to return.
        total_count: The paper's total citation count, when the caller knows
            it. When it exceeds one page (``_RANK_POOL``), the pool is built by
            *stratified sampling* across S2's citation list (see
            ``_stratified_pool``) so the spread can reach older descendants,
            not just the recent tip. Omitted/None falls back to one page.

    Returns:
        A list of ``{"node": <node dict>, "influential": bool}`` entries.

    Raises:
        client.S2Error: When the request fails after retries.
    """
    path = f"{client.quote(paper_id)}/citations"
    if total_count and total_count > _RANK_POOL:
        pool = _stratified_pool(path, "citingPaper", total_count)
    else:
        pool = _fetch_page(path, "citingPaper", max(limit, _RANK_POOL))
    return _select_even_by_year(pool, limit)


def recommendations(paper_id: str, limit: int, pool: str | None = None) -> list[dict]:
    """Fetch embedding-based related papers (similarity neighbors).

    Args:
        paper_id: An S2 paperId or prefixed id.
        limit: Maximum recommendations to return.
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
    url = (
        f"{config.s2.recs_url}/papers/forpaper/{client.quote(paper_id)}"
        f"?fields={urllib.parse.quote(nodes.NEIGHBOR_FIELDS)}&limit={limit}&from={pool}"
    )
    data = client.request(url)
    recommended_papers = data.get("recommendedPapers") if isinstance(data, dict) else None
    return nodes.from_papers(recommended_papers or [])
