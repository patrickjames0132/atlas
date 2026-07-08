"""Hydrating known papers and walking the citation graph from a seed:
batch detail lookup, references, citations, and similarity recommendations.
"""

from __future__ import annotations

import logging
import urllib.parse
from collections import defaultdict

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

# Landmark mining for citation lists the offset ceiling truncates. A paper
# with more citations than S2 will ever page through (e.g. ~150k for
# "Attention Is All You Need") has its famous mid-era citers — BERT-class
# landmarks — sitting far past the ceiling, unreachable by any offset. But
# landmarks are exactly the papers everyone ELSE cites: harvest the
# reference lists of the pool's most-cited reachable citers (surveys are
# goldmines — they cite every landmark), rank the candidates by their own
# citation count, and VERIFY each one actually cites the seed before
# keeping it — co-appearing in reference lists is not proof, and the graph
# must never invent a citation edge. Verified landmarks join the pool the
# even-by-year selection draws from. The whole mine costs exactly TWO batch
# requests (harvest + verify) — per-source /references calls at S2's
# throttle made mega builds crawl.
_MINE_SOURCES = 12  # reachable citers whose reference lists are mined
# Candidates sent to verification. Generous on purpose: verification is ONE
# batch request regardless of count, and reference lists are dominated by
# giants that predate the seed (rank-by-citations alone would spend every
# slot on papers that can't possibly cite it). Candidates published before
# the seed are pruned first; the cap just keeps the batch payload sane.
_MINE_CANDIDATES = 200


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


def _cites_seed(candidate_ids: list[str], seed_id: str) -> set[str]:
    """The subset of candidates whose reference lists contain the seed.

    One batched ``references.paperId`` lookup — the honesty gate of landmark
    mining: only a candidate PROVEN to cite the seed may enter the citation
    pool (and become a citation edge). A candidate whose references can't be
    checked counts as unverified and is dropped — the graph never guesses.

    Args:
        candidate_ids: S2 paperIds of the mined candidates, best-first.
        seed_id: The seed's S2 paperId to look for.

    Returns:
        The verified candidate ids (empty when the batch request fails —
        mining is best-effort, never a build dependency).
    """
    if not candidate_ids:
        return set()
    url = f"{config.s2.graph_url}/paper/batch?fields=references.paperId"
    try:
        data = client.request(url, method="POST", body={"ids": candidate_ids})
    except client.S2Error as exc:
        log.warning("landmark verification batch failed (%s); keeping no mined citers", exc)
        return set()
    papers = data if isinstance(data, list) else []
    verified: set[str] = set()
    for candidate_id, paper in zip(candidate_ids, papers):
        references = (paper or {}).get("references") or []
        if any(reference.get("paperId") == seed_id for reference in references):
            verified.add(candidate_id)
    return verified


def _mined_landmarks(seed_id: str, pool: list[dict], year: int | None) -> list[dict]:
    """Landmark citers recovered from beyond S2's offset ceiling.

    Mines the reference lists of the pool's ``_MINE_SOURCES`` most-cited
    reachable citers for papers not already in the pool, keeps the
    ``_MINE_CANDIDATES`` most-cited candidates **published in or after the
    seed's year** (a paper from before the seed can't cite it — without
    this prune, the ranking drowns in pre-seed giants like optimizer and
    dataset papers and the true descendants never reach verification), and
    returns only the ones ``_cites_seed`` verifies. The harvest is ONE
    ``references.*`` batch request covering every source at once (nested
    reference lists come back with the neighbor fields, no per-source
    calls), and verification is one more — two requests total. Best-effort
    throughout: either batch failing degrades to fewer (or no) landmarks
    rather than failing the graph build.

    Args:
        seed_id: The seed's S2 paperId (the verification target).
        pool: The reachable citation pool (mined ids are excluded from it).
        year: The seed's publication year (None skips the year prune;
            undated candidates are kept for verification to judge).

    Returns:
        Verified landmark entries, ``{"node": ..., "influential": False}``
        (the influence flag is per-citation data only the /citations
        endpoint reports — unknowable here).
    """
    sources = _select_by_influence(pool, _MINE_SOURCES)
    if not sources:
        return []

    fields = ",".join(f"references.{field}" for field in nodes.NEIGHBOR_FIELDS.split(","))
    url = f"{config.s2.graph_url}/paper/batch?fields={urllib.parse.quote(fields)}"
    try:
        data = client.request(
            url, method="POST", body={"ids": [source["node"]["id"] for source in sources]}
        )
    except client.S2Error as exc:
        # Mining is strictly a cheap bonus — the reachable pool still serves.
        log.warning("landmark harvest batch failed for %s (%s); skipping mining", seed_id, exc)
        return []
    harvested: list[dict] = []
    for paper in data if isinstance(data, list) else []:
        for reference in (paper or {}).get("references") or []:
            candidate = nodes.node(reference)
            if candidate:
                harvested.append(candidate)

    pooled_ids = {entry["node"]["id"] for entry in pool}
    candidates: dict[str, dict] = {}
    for candidate in harvested:
        candidate_id = candidate["id"]
        if candidate_id == seed_id or candidate_id in pooled_ids:
            continue
        if year is not None and candidate.get("year") is not None and candidate["year"] < year:
            continue  # published before the seed — it can't cite it
        if candidate_id not in candidates:
            candidates[candidate_id] = candidate

    ranked = sorted(
        candidates.values(), key=lambda node: node.get("citation_count") or 0, reverse=True
    )[:_MINE_CANDIDATES]
    verified = _cites_seed([node["id"] for node in ranked], seed_id)
    return [{"node": node, "influential": False} for node in ranked if node["id"] in verified]


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


def citations(
    paper_id: str, limit: int, *, total_count: int | None = None, year: int | None = None
) -> list[dict]:
    """Fetch the papers that CITE this one (its descendants).

    The selection is *even by year*: the most-cited citing papers within each
    publication year, spread across the paper's whole descendant timeline (see
    ``_select_even_by_year``) — not the global most-cited, which clumps in the
    field's busiest years, and not S2's raw order, which is just the newest.

    The pool that selection draws from is built in three tiers by how many
    citations the paper has (``total_count``):

    * **<= one page** (``_RANK_POOL``, or ``total_count`` omitted): a single
      over-fetched page — for modestly-cited papers that IS the complete
      list, so selection is exact.
    * **past one page**: *stratified sampling* across S2's newest-first
      citation list (``_stratified_pool``), so the pool spans the reachable
      descendant era instead of just the recent tip.
    * **past the offset ceiling** (``_MAX_OFFSET``): the stratified pool is
      additionally enriched with *mined landmarks* (``_mined_landmarks``) —
      the famous citers living beyond what S2 will ever page to, recovered
      from the reference lists of reachable citers and verified to actually
      cite this paper before they may join.

    Args:
        paper_id: An S2 paperId or prefixed id.
        limit: Maximum citations to return.
        total_count: The paper's total citation count, when the caller knows
            it (drives the tier dispatch above). Omitted/None falls back to
            one page.
        year: The paper's own publication year, when the caller knows it —
            lets landmark mining prune candidates that predate the paper
            (they can't cite it) before ranking, so the verification budget
            goes to plausible descendants instead of older mega-papers.

    Returns:
        A list of ``{"node": <node dict>, "influential": bool}`` entries.

    Raises:
        client.S2Error: When the request fails after retries (landmark
            mining never raises — it degrades to the reachable pool).
    """
    path = f"{client.quote(paper_id)}/citations"
    if total_count and total_count > _RANK_POOL:
        pool = _stratified_pool(path, "citingPaper", total_count)
        if total_count > _MAX_OFFSET + _STRATUM_LIMIT:
            # The ceiling truncates this paper's citation list — the pool
            # can't reach its older landmarks by offset. Mine them instead.
            pool = pool + _mined_landmarks(paper_id, pool, year)
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
