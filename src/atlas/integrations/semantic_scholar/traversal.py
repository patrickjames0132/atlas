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

#: The most citers a deep-paged live fetch can ever return: the last servable
#: page's window end (``_MAX_OFFSET + _RANK_POOL``). Public because the
#: ``live_pool_validation`` pipeline simulates this exact truncation against the
#: offline corpus — the constant must be the pager's own, not a copied number.
REACHABLE_CITERS = _MAX_OFFSET + _RANK_POOL

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


def _fetch_page_with_next(path: str, key: str, limit: int,
                          offset: int = 0) -> tuple[list[dict], bool]:
    """Fetch one page of references/citations, and whether the list continues.

    The continuation flag is primarily S2's own ``next`` field, NOT an
    entry-count check — a page can come back short of ``limit`` mid-list when S2
    fails to resolve some of its papers (they're skipped here), so a short
    *entries* list does not mean "end of list". A full *raw* page (before the
    resolve-skip) also counts as continuation, as a belt-and-suspenders against
    a response missing ``next`` on a full page — at worst it costs one extra
    request that comes back empty. The deep pager's completeness verdict rides
    on this flag being conservative in exactly that direction.

    Args:
        path: The endpoint path under ``/paper/`` (quoted id + relation).
        key: The nested paper key — ``"citedPaper"`` or ``"citingPaper"``.
        limit: Page size to request.
        offset: Where to start in S2's (newest-first) list.

    Returns:
        ``([{"node", "influential"}] entries, has_more)`` — entries skip papers
        S2 couldn't resolve; ``has_more`` is True when the list continues past
        this page.

    Raises:
        client.S2Error: When the request fails after retries.
    """
    url = (
        f"{config.providers.s2.graph_url}/paper/{path}"
        f"?fields={urllib.parse.quote(nodes.NEIGHBOR_FIELDS)}&limit={limit}&offset={offset}"
    )
    data = client.request(url)
    raw_items = (data.get("data") or []) if isinstance(data, dict) else []
    entries: list[dict] = []
    for item in raw_items:
        node = nodes.node(item.get(key))
        if node:
            entries.append({"node": node, "influential": bool(item.get("isInfluential"))})
    has_more = isinstance(data, dict) and (
        data.get("next") is not None or len(raw_items) == limit
    )
    return entries, has_more


def _fetch_page(path: str, key: str, limit: int, offset: int = 0) -> list[dict]:
    """One page of references/citations, entries only (see :func:`_fetch_page_with_next`).

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
    entries, _has_next = _fetch_page_with_next(path, key, limit, offset=offset)
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


def _fetch_reachable_pool(paper_id: str) -> tuple[list[dict], bool]:
    """Page the seed's whole reachable citer pool, newest-first, deduped —
    and report whether that pool is the seed's **complete** citation history.

    Pages S2's newest-first citation list all the way down: 1000-id pages
    (offset 0, 1000, 2000, …) until the list runs out or the ``_MAX_OFFSET``
    ceiling is hit, giving up to ~9k citers.

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

    **Completeness** is S2's own ``next`` flag, not a page-length heuristic (a
    page can come back short mid-list when S2 fails to resolve some papers): the
    pool is complete when the walk reached a page with no continuation before
    hitting the offset ceiling. Most seeds have well under ~9k citers, so
    complete pools are the *common* case — and a complete pool is a
    whole-history pool, which the caller may treat exactly as it would the
    corpus (see :func:`citation_relations`).

    Args:
        paper_id: An S2 paperId or prefixed id.

    Returns:
        ``(pool, complete)`` — the deduped ``[{"node", "influential"}]`` pool,
        newest-first, and whether it's the seed's whole citation history
        (False when the ceiling cut it off, or a deep page failed and the truth
        is unknowable).

    Raises:
        client.S2Error: When the *newest* page (offset 0) fails — a real
            outage. A deeper page S2 rejects is swallowed (degrade to the
            range reached), matching the offset-ceiling reality.
    """
    path = f"{client.quote(paper_id)}/citations"
    pool: list[dict] = []
    seen: set[str] = set()
    offset = 0
    complete = False
    while offset <= _MAX_OFFSET:
        try:
            page, has_more = _fetch_page_with_next(path, "citingPaper", _RANK_POOL, offset=offset)
        except client.S2Error:
            if offset == 0:
                raise  # the newest page failing is an outage, not a deep-window skip
            break  # a page S2 won't serve — take what we have; completeness unknowable
        for entry in page:
            paper = entry["node"]["id"]
            if paper not in seen:
                seen.add(paper)
                pool.append(entry)
        if not has_more:
            complete = True  # ran off the end of the citation list
            break
        offset += _RANK_POOL
    return pool, complete


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
    page = _fetch_page(f"{client.quote(paper_id)}/citations", "citingPaper", _RANK_POOL)
    return _select_by_influence(page, limit)


#: Injected landmark selector: ``(ranked citer years) -> indices to ship | None``.
#: ``services/graph`` passes ``budget.select_landmarks``, which bands the ranking
#: by year; None falls back to the flat ``landmark_limit``. It takes years and
#: returns indices because the rule only reasons about *when* citers were
#: published — the entries themselves stay here. A parameter, not an import, so
#: ``integrations`` stays below ``services`` in the dependency order — the same
#: shape as OpenAlex's ``BandStartFn``. **Truncated pools only** — a complete
#: pool takes the budget/band-start pair below instead.
LandmarkSelectFn = Callable[[Sequence[int | None]], list[int] | None]

#: Injected landmark budget for a COMPLETE pool: ``(ranked citer years) -> how
#: many to ship | None``. ``services/graph`` passes ``budget.computed_cite_limit``
#: — the STOP rule, identical to the corpus source's ``LandmarkBudgetFn``,
#: because a complete pool *is* a whole-history pool and gets the same treatment.
LandmarkBudgetFn = Callable[[Sequence[int | None]], int | None]

#: Injected Latest band-start chooser for a COMPLETE pool: ``(landmark_years,
#: landmark_max_year) -> first band year | None``. ``services/graph`` passes
#: ``bands.earliest_band_year`` — the same tau rule the corpus and OpenAlex
#: paths use; None keeps the fixed ``latest_band_years`` span.
BandStartFn = Callable[[list[int], int], int | None]


def _complete_pool_relations(
    pool: list[dict],
    *,
    landmark_limit: int | None,
    latest_limit: int | None,
    max_landmark_year: int,
    current_year: int,
    landmark_budget: LandmarkBudgetFn,
    band_start: BandStartFn | None,
) -> tuple[list[dict], list[dict]]:
    """The corpus shape, served from a live pool that is the seed's whole history.

    Mirrors ``corpus.source.citation_relations`` decision-for-decision, in Python
    over the in-memory pool instead of SQL over Parquet — because the *reason*
    the live path bands (SKIP) and rolls a 12-month window is that its pool is
    normally a truncated recency sliver, and for a fully-reachable seed that
    reason is gone. Concretely:

    * **Landmarks** — the citers up to ``max_landmark_year`` (an undated citer
      competes here, as in the corpus: it can't be banded, and dropping it could
      lose a giant), ranked most-cited first, shipped as a **prefix** whose
      length the STOP rule computes from the real years. Banding here would
      admit the best of a thin year over the 13th-best of a blockbuster one and
      flatten the year distribution the tau rule reads next.
    * **Latest** — per-year bands from the ``band_start`` rule (read off the
      shipped landmarks' years, which is why it runs second) up to
      ``current_year``, each year's top ``latest_per_year`` by citations; a
      giant appearing in both stays a landmark. Newest-first, trimmed to
      ``latest_limit`` (keeping the newest), then flipped oldest-first for the
      reveal slider.

    Args:
        pool: The complete citer pool (see :func:`_fetch_reachable_pool`).
        landmark_limit: The flat ceiling, used when the budget rule declines.
        latest_limit: Max latest citers (keeps the newest), or None for all.
        max_landmark_year: The last landmark-era year (inclusive).
        current_year: The last year to band, inclusive.
        landmark_budget: The STOP rule measuring the ranked pool's years.
        band_start: Optional per-seed band-start chooser; None (or a None
            answer) keeps the fixed ``latest_band_years`` span.

    Returns:
        ``(landmark_entries, latest_entries)`` — each ``[{"node", "influential"}]``.
    """
    era = [
        entry for entry in pool
        if entry["node"].get("year") is None or entry["node"]["year"] <= max_landmark_year
    ]
    ranked = _select_by_influence(era, None)
    budget = landmark_budget([entry["node"].get("year") for entry in ranked])
    # A None answer means the adaptive toggle is off — honour the flat ceiling.
    landmark = ranked[:budget] if budget is not None else ranked[:landmark_limit]

    earliest = max_landmark_year - config.graph.latest_band_years + 1
    if band_start is not None:
        adaptive = band_start(
            [year for year in (entry["node"].get("year") for entry in landmark) if year],
            max_landmark_year,
        )
        if adaptive is not None:
            earliest = adaptive
    by_year: dict[int, list[dict]] = {}
    for entry in pool:
        year = entry["node"].get("year")
        if year is not None and earliest <= year <= current_year:
            by_year.setdefault(year, []).append(entry)
    shipped = {entry["node"]["id"] for entry in landmark}
    recent: list[dict] = []
    for year_entries in by_year.values():
        recent += _select_by_influence(year_entries, config.graph.latest_per_year)
    latest = [entry for entry in recent if entry["node"]["id"] not in shipped]
    latest.sort(key=_latest_order, reverse=True)
    if latest_limit is not None:
        latest = latest[:latest_limit]
    latest.reverse()
    return landmark, latest


def citation_relations(
    paper_id: str,
    *,
    landmark_limit: int | None,
    latest_limit: int | None,
    max_landmark_year: int,
    current_year: int,
    landmark_select: LandmarkSelectFn | None = None,
    landmark_budget: LandmarkBudgetFn | None = None,
    band_start: BandStartFn | None = None,
) -> tuple[list[dict], list[dict]]:
    """Split a seed's citers into two relations: landmarks and the latest frontier.

    The FALLBACK path (used only when the offline citations corpus can't serve the
    seed). The whole reachable citer list is paged in
    (:func:`_fetch_reachable_pool` — up to ~9k), and **which shape ships depends
    on whether that pool is the seed's complete history**:

    * **Complete** (the list ended before the offset ceiling — the common case;
      most seeds have well under ~9k citers) and a ``landmark_budget`` was
      supplied: the pool is a *whole-history* pool, exactly what the corpus
      holds, so it ships the corpus shape — STOP-prefix landmarks plus
      tau-banded per-year Latest (:func:`_complete_pool_relations`). The
      truncation caveats below simply don't apply.
    * **Truncated** (the ceiling cut the list off): the pool is a recency
      sliver with no all-history ranking to prefix. Citers inside the rolling
      ``_LATEST_WINDOW_MONTHS`` window are the recent **frontier** (``latest``,
      shipped oldest-first so the reveal slider walks toward the present; a
      limit keeps the newest), and everything older competes as a historic
      **landmark** (most-cited first), banded by the ``landmark_select`` SKIP
      rule — a *prefix* of a truncated ranking is all one era (DQN's top 29 are
      2019–2023, an 18-month hole before the frontier), so every year gets its
      slice instead. What's past the ceiling — DQN's 2013–2018 citers, the real
      giants — no amount of paging reaches; that's the corpus's job.

    Args:
        paper_id: An S2 paperId or prefixed id.
        landmark_limit: Maximum landmark (historic) citers to return, or ``None``
            for all. Used when no rule is supplied, or when it declines.
        latest_limit: Maximum recent-frontier citers to return, or ``None`` for all.
        max_landmark_year: The last landmark-era year — the complete-pool split
            boundary (the same one the corpus and OpenAlex split on; passed in so
            the providers stay independent).
        current_year: The last year the complete-pool shape bands, inclusive.
        landmark_select: Optional SKIP rule for the **truncated** pool (see
            :data:`LandmarkSelectFn`); its pick wins over ``landmark_limit``.
        landmark_budget: Optional STOP rule for the **complete** pool (see
            :data:`LandmarkBudgetFn`); required for the corpus shape — without
            it a complete pool still ships the truncated shape.
        band_start: Optional Latest band-start chooser for the **complete** pool
            (see :data:`BandStartFn`).

    Returns:
        ``(landmark_entries, latest_entries)`` — each ``[{"node", "influential"}]``.

    Raises:
        client.S2Error: When the request fails after retries.
    """
    pool, complete = _fetch_reachable_pool(paper_id)
    if complete and landmark_budget is not None:
        log.debug("live s2 pool is the complete history (%d citers) — corpus shape", len(pool))
        return _complete_pool_relations(
            pool,
            landmark_limit=landmark_limit,
            latest_limit=latest_limit,
            max_landmark_year=max_landmark_year,
            current_year=current_year,
            landmark_budget=landmark_budget,
            band_start=band_start,
        )
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
