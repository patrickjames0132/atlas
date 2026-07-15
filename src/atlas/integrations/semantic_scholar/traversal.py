"""Hydrating known papers and walking the citation graph from a seed:
batch detail lookup, references, citations, and similarity recommendations.
"""

from __future__ import annotations

import datetime
import logging
import urllib.parse
from collections.abc import Sequence
from typing import Callable

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

# Deepest offset a citations page may request. S2 rejects a page whose window
# reaches ~10k — verified live 2026-07-15: ``offset=9000&limit=1000`` is an HTTP
# 400 (on two different seeds), while ``offset=8000`` serves fine. So 8000 is the
# last servable page and the reachable pool tops out at ~9k citers, not the 10k
# the arithmetic suggests. Anything older is unreachable from the live API at any
# price — only the offline citations corpus has it.
_MAX_OFFSET = 8000

# The "latest" citation window: a citer whose publication date falls within
# this many months of today is the recent *frontier* (its own graph relation),
# not a historic landmark. A rolling window, not a calendar year, so it stays
# populated year-round (a hard "current year" cut is near-empty every January).
_LATEST_WINDOW_MONTHS = 12
# Citation traversal here is the s2 provider's FALLBACK path, used when the
# offline citations corpus can't serve a seed. Its landmark story is a scar worth
# knowing: v3.1.0 mined landmarks from past the offset ceiling (harvest citers'
# reference lists, co-citation rank, verify), v3.4.0 added the deep pager to fill
# the *latest* window, and v4.0.0 retired the mining when OpenAlex's sorted
# ``cites:`` queries made it redundant. That left the landmark relation riding on
# a pager built for a different purpose — and when v5.0.0 promoted s2 back to a
# first-class provider, nothing replaced the mining. v5.5.0 stops the pager
# short-changing landmarks (it now pages the whole reachable list, not just the
# latest window); reaching *past* the ceiling is the corpus's job, not this
# module's.


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
    url = f"{config.providers.s2.graph_url}/paper/batch?fields={urllib.parse.quote(fields)}"
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
    proxy for how landmark a paper is, and the within-pool ranking key.
    """
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

    True when the node's ``pub_date`` is at or after ``cutoff`` — or, when S2
    gave no date at all, when its ``year`` alone settles it: a citer from a year
    *after* the cutoff's year is inside the window no matter which month it came
    out. Only the cutoff's own year is genuinely ambiguous (January is outside
    the window, December is in), and that stays a ``citation`` — the conservative
    read, since a landmark misfiled as frontier is the worse error.

    The year fallback matters because S2's dating is patchy on exactly the papers
    this decides: without it, a **2026** citer with no ``publicationDate`` gets
    filed as a historic Field Landmark, which is nonsense — it's months old. Those
    then pile onto one x in the timeline (no month → the year's gridline), and
    they're a bare vertical line the moment the Latest chip is toggled off. The
    OpenAlex traversal hit the same trap and answered it the same way (it splits
    by year outright, its dating being coarser still — see its module docstring).
    """
    node = entry["node"]
    pub_date = node.get("pub_date")
    if pub_date:
        return pub_date >= cutoff
    year = node.get("year")
    return bool(year) and year > int(cutoff[:4])


def _latest_order(entry: dict) -> str:
    """A latest citer's recency sort key: its ``pub_date``, or Jan 1 of its year.

    The year fallback keeps the reveal order and the timeline's x placement in
    agreement — a citer with only a year is drawn on that year's gridline (the
    January position), so it should sort there too rather than ahead of every
    dated paper in the window.

    Args:
        entry: A ``{"node", "influential"}`` citer entry.

    Returns:
        An ISO-ish ``YYYY-MM-DD`` string, comparable lexicographically; ``""``
        for a citer with neither a date nor a year.
    """
    node = entry["node"]
    pub_date = node.get("pub_date")
    if pub_date:
        return str(pub_date)
    year = node.get("year")
    return f"{year:04d}-01-01" if year else ""


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
        f"{config.providers.s2.graph_url}/paper/{path}"
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
    ``deep=True`` (the seed build) pages S2's newest-first citation list all the
    way down: 1000-id pages (offset 0, 1000, 2000, …) until the list runs out or
    the ``_MAX_OFFSET`` ceiling is hit, giving up to ~9k citers.

    **It pages the whole list, not just the ``latest`` window** — and that's the
    whole point, because the *landmarks* are what live down there. Until v5.5.0
    this stopped at the first page holding no in-window citer, on the reasoning
    that the window was then behind us and the boundary page's overshoot would
    seed the landmark "middle band". For a hyper-cited seed that reasoning quietly
    gutted the landmark relation: measured live on DQN, page 1 holds exactly ONE
    in-window citer and page 2 holds none, so paging stopped at offset 2000 with a
    pool covering 2024–2026 — while the full reachable list runs back to **2019**
    and holds the citers anyone would call landmarks (Conservative Q-Learning,
    Decision Transformer, Dota 2). Six-sevenths of the reachable pool was never
    fetched, so "Field Landmarks" ranked whatever recent survey happened to be in
    the overshoot.

    Paging on changes ``latest`` not at all — every deeper page is older than the
    window, so they feed only the landmark pool — but it does cost requests the
    window alone wouldn't need, scaling with the citer list up to the ceiling
    (measured on a cache miss, authenticated: QMIX 4 pages / ~8s, DQN 9 pages /
    ~15s). Only a seed whose citers fit in one page is free. That's the trade: a
    slower cold build for a landmark relation that isn't noise. Snapshots cache
    for a day, and the build's progress bar covers the wait.

    Args:
        paper_id: An S2 paperId or prefixed id.
        deep: Page the whole reachable list (seed build) vs. one page (expansion).

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

    pool: list[dict] = []
    seen: set[str] = set()
    offset = 0
    while offset <= _MAX_OFFSET:
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
        offset += _RANK_POOL
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


#: Injected landmark selector: ``(ranked citer years) -> indices to ship | None``.
#: ``services/graph`` passes ``budget.density_selection``, which bands the ranking
#: by year; None falls back to the flat ``landmark_limit``. It takes years and
#: returns indices because the rule only reasons about *when* citers were
#: published — the entries themselves stay here. A parameter, not an import, so
#: ``integrations`` stays below ``services`` in the dependency order — the same
#: shape as OpenAlex's ``BandStartFn``.
LandmarkSelectFn = Callable[[Sequence[int | None]], list[int] | None]


def citation_relations(
    paper_id: str,
    *,
    landmark_limit: int | None,
    latest_limit: int | None,
    landmark_select: LandmarkSelectFn | None = None,
) -> tuple[list[dict], list[dict]]:
    """Split a seed's citers into two relations: landmarks and the latest frontier.

    The FALLBACK path (used only when the offline citations corpus can't serve the
    seed). The whole reachable citer list is paged in (``_fetch_citers`` with
    ``deep=True`` — up to ~9k) then partitioned by publication date: citers inside
    the rolling ``_LATEST_WINDOW_MONTHS`` window are the recent **frontier**
    (``latest``, shipped oldest-first so the reveal slider walks toward the
    present; a limit keeps the newest), and everything older competes as a
    historic **landmark** (``citation``, most-cited first). The two are disjoint,
    so a recent-but-highly-cited paper shows once, as ``latest``.

    Paging the whole list rather than just the window is what gives ``landmark``
    anything to rank: on DQN it's the difference between a pool covering 2024–2026
    and one running back to 2019 (see :func:`_fetch_citers`). What's still missing
    is everything past the offset ceiling — for DQN, its 2013–2018 citers, the
    real giants — which no amount of paging reaches. That's the corpus's job.

    Having the pool in memory is also why the landmark trim takes a
    ``landmark_select`` rule rather than a flat count. A count can only ever keep a
    *prefix* of the ranking, which on a seed like DQN is all one era — the top 29
    are 2019–2023 and 2024–2025 never appear, leaving a visible hole before the
    Latest frontier. A selector bands the ranking by year instead, so every year
    from the ceiling to the window gets its slice. See ``budget.density_selection``.

    Args:
        paper_id: An S2 paperId or prefixed id.
        landmark_limit: Maximum landmark (historic) citers to return, or ``None``
            for all (the whole deep-paged older pool). Used when no
            ``landmark_select`` is supplied, or when it declines to pick.
        latest_limit: Maximum recent-frontier citers to return, or ``None`` for all.
        landmark_select: Optional rule choosing which of the *ranked* landmark pool
            to ship, from its citer years (see :data:`LandmarkSelectFn`); its pick
            wins over ``landmark_limit``. None (the default) uses the flat limit.

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
    #
    # A dateless citer sorts as Jan 1 of its year, which is exactly where the
    # timeline draws it (no month -> the year's gridline), so the reveal order
    # and the on-screen order agree. Bare `or ""` would instead rank it before
    # every dated paper in the window while drawing it in the middle of them.
    latest = sorted(recent, key=_latest_order, reverse=True)
    latest = latest[:latest_limit]
    latest.reverse()
    # Rank the whole older pool first: the selector reads that ranking's years and
    # answers in its indices, so it can only run after the sort and before the trim.
    ranked_older = _select_by_influence(older, None)
    keep: list[int] | None = None
    if landmark_select is not None:
        keep = landmark_select([entry["node"].get("year") for entry in ranked_older])
    if keep is None:
        return ranked_older[:landmark_limit], latest
    return [ranked_older[index] for index in keep], latest


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
        f"{config.providers.s2.recs_url}/papers/forpaper/{client.quote(paper_id)}"
        f"?fields={urllib.parse.quote(nodes.NEIGHBOR_FIELDS)}&limit={page}&from={pool}"
    )
    data = client.request(url)
    recommended_papers = data.get("recommendedPapers") if isinstance(data, dict) else None
    return nodes.from_papers(recommended_papers or [])
