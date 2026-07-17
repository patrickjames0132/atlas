"""Resolving a seed to its OpenAlex work and walking its citers — the OpenAlex
half of the hybrid graph build.

This is the payoff of the 2026-07-09 spike: a seed's citers come from
**server-sorted** ``cites:`` queries, edge guaranteed by the filter. That retires
the entire S2 ``_mined_landmarks`` apparatus (harvest → co-citation rank →
verify), which existed only to work around S2's newest-first, offset-capped
citation endpoint. The citation relation is:

* **landmark** (*Field Landmarks*) — the all-time most-cited citers
  (``cited_by_count:desc``). The historic giants; naturally old.
* **latest** (*Latest Publications*) — recent citers as per-year bands: one
  ``cited_by_count:desc`` query *per year* from the band start up to the current
  year (so no single year dominates — a subtlety we hit live), no separate
  newest-date window. A recent paper that's also an all-time giant stays a
  landmark, not double-shown; the rest ship oldest-first (the reveal slider walks
  toward the present).

The landmark/latest split is by **publication year**, not an exact date, because
OpenAlex dating is coarse (many works are year-only, defaulted to ``01-01``) —
an exact rolling window silently drops recent-year citers. Nodes come out
already S2-resolvable (see ``nodes.py``), so the existing paper routes hydrate
their TL;DRs and re-seed them unchanged.
"""

from __future__ import annotations

import datetime
import logging
import re
from collections.abc import Sequence
from typing import Callable

from ...config import config
from .. import arxiv
from . import client, nodes

log = logging.getLogger(__name__)

# OpenAlex caps ``per-page`` at 200.
_PER_PAGE = 200

# OpenAlex caps an OR filter (``a|b|c``) at 50 values per request.
_OR_FILTER_MAX = 50

# The landmark/latest split is by **publication YEAR**, not an exact date, on
# purpose: OpenAlex dates are coarse — a large fraction of works carry a
# year-only ``publication_date`` defaulted to ``<year>-01-01`` — so a rolling
# 12-month *date* window (what the S2 path used) silently drops almost every
# recent-year citer (verified live: DQN had 1 citer in a from-date window vs 30
# in the same year). ``_LATEST_YEARS`` marks the boundary: citers from the last
# ``_LATEST_YEARS`` calendar years are never landmarks (always ``latest`` bands);
# ``landmark`` = the all-time most-cited up to the year below that.
_LATEST_YEARS = 2  # current year + previous year are latest-only, never landmarks

# How many landmark citers to pull for an *unbounded* relation (config ship count
# = ``null``). Server-sorted, so these are the top-N by citation count — plenty of
# range for the frontend's reveal-on-demand slider without paging a mega seed's
# entire citer list (Hawking has ~5.7k; "Attention" ~150k). An explicit numeric
# limit overrides this.
UNBOUNDED_LANDMARK_CAP = 500


def landmark_max_year(as_of: datetime.date) -> int:
    """The last calendar year that still counts as landmark-era.

    Everything published after this year falls in the newest ``latest`` window
    (the last ``_LATEST_YEARS`` calendar years). Public because the
    ``latest_gap`` corpus collector must cap its citer-year pulls at exactly
    this bound to mirror the build's landmark query.

    Args:
        as_of: The date the split is computed from (today at build time).

    Returns:
        The landmark-era cutoff year (e.g. 2024 when ``as_of`` is in 2026).
    """
    return as_of.year - _LATEST_YEARS


def _clean_search(title: str) -> str:
    """Strip a title down to search-safe text for a ``title.search`` filter.

    OpenAlex's ``filter=`` grammar uses ``,`` and ``:`` as separators, and a
    literal ``?`` (or other punctuation) in the value returns HTTP 400. The
    search itself is fuzzy/stemmed, so dropping non-alphanumerics costs nothing
    — ``"Black hole explosions?"`` → ``"Black hole explosions"`` still matches.
    """
    return re.sub(r"\s+", " ", re.sub(r"[^0-9A-Za-z ]+", " ", title)).strip()


def _try_entity(entity_id: str, select: str) -> dict | None:
    """Fetch one work by a path id (``W…`` / ``doi:…``), or None on a 404.

    The FREE id-lookup path. A 404 (OpenAlex has no such work) is treated as
    data, not an error — the caller falls back to search.
    """
    try:
        result = client.request(client.entity_url(entity_id, {"select": select}))
    except client.OpenAlexError as exc:
        if exc.status == 404:
            return None
        raise
    return result if isinstance(result, dict) else None


def resolve_work(
    *, arxiv_id: str | None, title: str | None, select: str = nodes.NEIGHBOR_SELECT
) -> dict | None:
    """Find the OpenAlex work for a seed given its arXiv id and/or title.

    arXiv→work resolution is the spike's known friction point (OpenAlex has no
    filterable arXiv id, and the arXiv-minted DOI only resolves for
    preprint-only papers — a journal version's canonical record uses the
    *published* DOI). So we try cheapest-first:

    1. **arXiv-DOI id lookup** (free) — resolves papers whose canonical record
       *is* the arXiv preprint.
    2. **Title search, most-cited first** — the robust general fallback: a
       seed's title is distinctive and its own paper is overwhelmingly the
       top-cited match. We deliberately do **not** pin ``publication_year`` —
       OpenAlex's year is sometimes wrong (the transformer record reports 2025
       for a 2017 paper), and a hard year filter turns that into a total
       resolution miss (verified live: it silently forced the S2 fallback).

    Args:
        arxiv_id: The seed's bare arXiv id, when it has one.
        title: The seed's title, when known (the title-search fallback needs it).
        select: The OpenAlex ``select`` field list to request — defaults to the
            light ``NEIGHBOR_SELECT``; a seed resolve passes ``DETAIL_SELECT`` so
            the resolved work carries its abstract.

    Returns:
        The raw OpenAlex work object (carrying ``id``), or None when neither
        path finds it.
    """
    if arxiv_id:
        work = _try_entity(f"doi:10.48550/arXiv.{arxiv_id}", select)
        if work:
            return work
    cleaned = _clean_search(title or "")
    if not cleaned:
        return None
    params = {
        "filter": f"title.search:{cleaned}",
        "sort": "cited_by_count:desc",
        "per-page": "1",
        "select": select,
    }
    data = client.request(client.works_url(params))
    results = data.get("results") if isinstance(data, dict) else None
    return results[0] if results else None


def resolve_seed_work(seed_ref: str) -> dict | None:
    """Resolve a seed reference to its OpenAlex work, hydrated for the seed node.

    The OpenAlex twin of the S2 seed lookup (``s2.get_paper``): it accepts every
    id form a seed can arrive as — a bare **arXiv id** (a fresh search), or one
    of the S2-resolvable ids an OpenAlex graph node carries when the user
    re-seeds on it: ``DOI:<doi>``, ``ARXIV:<id>``, or a bare OpenAlex ``W…``
    (see ``nodes.resolvable_id``). Uses ``DETAIL_SELECT`` so the resolved seed
    carries its abstract — the seed node is grounding context, unlike the light
    neighbor traversals.

    Resolution friction (the spike's, handled here): a bare arXiv id resolves
    cheapest-first through the arXiv-minted DOI. That misses entirely for a paper
    whose canonical OpenAlex record is a *published* version not aliased to the
    arXiv DOI (e.g. "Attention Is All You Need" — ``doi:10.48550/arXiv.1706.03762``
    is a 404 in OpenAlex). So on that miss we fetch the paper's **title from
    arXiv** and title-search OpenAlex, which lands the canonical (most-cited)
    record. If a paper genuinely resolves to its preprint stub instead, its count
    reads lower than S2's — an accepted OpenAlex-provider tradeoff.

    Args:
        seed_ref: A bare arXiv id, ``DOI:…``, ``ARXIV:…``, or a bare ``W…`` id.

    Returns:
        The raw OpenAlex work (carrying ``id`` for ``cites:``/``cited_by:``
        queries and the fields :func:`nodes.node` needs), or None when
        unresolvable.

    Raises:
        client.OpenAlexError: When a non-404 request fails after retries.
    """
    ref = (seed_ref or "").strip()
    if not ref:
        return None
    # An OpenAlex/DOI node-id form → a free path lookup (no title-search needed).
    if re.fullmatch(r"W\d+", ref):
        return _try_entity(ref, nodes.DETAIL_SELECT)
    if ref[:4].upper() == "DOI:":
        return _try_entity(f"doi:{ref[4:]}", nodes.DETAIL_SELECT)
    # A bare arXiv id, or an ``ARXIV:`` node id → the arXiv-DOI/title path.
    arxiv_id = ref[6:] if ref[:6].upper() == "ARXIV:" else ref
    work = resolve_work(arxiv_id=arxiv_id, title=None, select=nodes.DETAIL_SELECT)
    if work:
        return work
    # The arXiv-DOI missed (published paper's canonical record not aliased to it).
    # Fall back to the arXiv title → an OpenAlex title search finds the canonical
    # record. arXiv is the arXiv id's home, and openalex already depends on it.
    title = arxiv.get_title(arxiv_id)
    if title:
        return resolve_work(arxiv_id=None, title=title, select=nodes.DETAIL_SELECT)
    return None


def get_paper(ref: str) -> dict | None:
    """Hydrate a single paper's full detail node from OpenAlex.

    The OpenAlex twin of ``s2.get_paper``, used to fill a clicked node's detail
    panel when the graph was built with the OpenAlex provider. Resolves any ref
    form (arXiv id / ``DOI:`` / ``ARXIV:`` / ``W…``) via ``resolve_seed_work``
    (which requests ``DETAIL_SELECT``), so the node carries its abstract and
    OpenAlex topic tags.

    Args:
        ref: The paper's arXiv id or an OpenAlex node id.

    Returns:
        The normalized detail node, or None when OpenAlex can't resolve the ref.

    Raises:
        client.OpenAlexError: When a non-404 request fails after retries.
    """
    work = resolve_seed_work(ref)
    return nodes.node(work) if work else None


def references(work_id: str, limit: int | None) -> list[dict]:
    """The papers a seed CITES — its bibliography (the OpenAlex twin of
    ``s2.references``).

    A ``cited_by:<work_id>`` filter returns exactly the works in the seed's own
    reference list (outbound citations). OpenAlex sorts them server-side by
    ``cited_by_count:desc``, so — unlike the S2 path, whose endpoint offers no
    ``sort`` and must over-fetch a pool and rank locally — the most-cited
    references come back directly.

    Args:
        work_id: The seed's bare OpenAlex id (``W…``).
        limit: Max references to return, or None for the unbounded cap.

    Returns:
        ``[{"node", "influential"}]`` entries, most-cited first (``influential``
        always False — OpenAlex has no influential-citation flag).

    Raises:
        client.OpenAlexError: When a page request fails after retries.
    """
    return _fetch_citers(
        f"cited_by:{work_id}",
        "cited_by_count:desc",
        limit if limit is not None else UNBOUNDED_LANDMARK_CAP,
        nodes.NEIGHBOR_SELECT,
    )


def bare_work_id(work: dict) -> str | None:
    """The bare OpenAlex id (``W…``) for use in a ``cites:`` filter."""
    return nodes.bare_openalex_id(work.get("id"))


def _fetch_citers(filter_clause: str, sort: str, cap: int | None, select: str) -> list[dict]:
    """Cursor-page a ``cites:`` query into normalized node entries.

    Args:
        filter_clause: The full ``filter=`` value (e.g.
            ``cites:W123,to_publication_date:2025-07-09``).
        sort: The ``sort=`` value (``cited_by_count:desc`` or
            ``publication_date:desc``).
        cap: Maximum citers to return; None uses the relation's unbounded cap.
        select: The ``select=`` field list.

    Returns:
        ``[{"node": <node dict>, "influential": False}]`` entries in server
        order (so enumeration index is the display rank), deduped by node id.
        ``influential`` is always False — OpenAlex has no influential-citation
        flag (the spike's finding); the key is present only for shape parity
        with the S2 traversal that graph assembly consumes.

    Raises:
        client.OpenAlexError: When a page request fails after retries.
    """
    target = cap if cap is not None else 0
    entries: list[dict] = []
    seen: set[str] = set()
    cursor: str | None = "*"
    while cursor and len(entries) < target:
        remaining = target - len(entries)
        params = {
            "filter": filter_clause,
            "sort": sort,
            "per-page": str(min(_PER_PAGE, remaining)),
            "cursor": cursor,
            "select": select,
        }
        data = client.request(client.works_url(params))
        results = data.get("results") if isinstance(data, dict) else None
        if not results:
            break
        for work in results:
            node = nodes.node(work)
            if node and node["id"] not in seen:
                seen.add(node["id"])
                entries.append({"node": node, "influential": False})
        cursor = ((data.get("meta") or {}).get("next_cursor")) if isinstance(data, dict) else None
    # Trim to the cap: the API respects ``per-page``, but a page that returns
    # more than requested (or the final partial page) shouldn't overshoot.
    return entries[:target]


def _by_citation(entry: dict) -> int:
    """A citer entry's citation count (0 when unknown) — the landmark rank key."""
    return entry["node"].get("citation_count") or 0


def _by_recency(entry: dict) -> tuple:
    """A citer entry's recency sort key (year then date), newest-first when
    reverse-sorted. Papers with only a year (no ``pub_date``) sort last in their
    year — the ``""`` date floor.
    """
    node = entry["node"]
    return (node.get("year") or 0, node.get("pub_date") or "")


#: Injected boundary chooser: ``(landmark_years, landmark_max_year) -> first band
#: year | None``. ``services/graph`` passes ``bands.earliest_band_year`` (the
#: trained per-seed rule); None keeps the fixed ``latest_band_years`` span. A
#: parameter, not an import, so ``integrations`` stays below ``services`` in the
#: dependency order.
BandStartFn = Callable[[list[int], int], int | None]

#: Injected landmark budget: ``(ranked citer years) -> how many to ship | None``.
#: ``services/graph`` passes ``budget.computed_cite_limit`` — the same STOP rule
#: the corpus path runs — and None (from the rule) falls back to the flat cap.
#: Identical to the corpus source's ``LandmarkBudgetFn``: a **count** for a
#: citation-ranked prefix, because this path's landmark pool is a whole-history
#: ranking too (see :func:`_budgeted_landmarks` for why computing it here is
#: as cheap as predicting was).
LandmarkBudgetFn = Callable[[Sequence[int | None]], int | None]


def _budgeted_landmarks(filter_clause: str, cap: int,
                        landmark_budget: LandmarkBudgetFn | None) -> list[dict]:
    """Fetch the landmark band, sized by the STOP rule when a budget is injected.

    Without a ``landmark_budget`` this is one capped fetch — the flat behavior.
    With one, the fetch is a **probe of a single ranked page** (200, the API's
    ``per-page`` maximum), and the rule runs over its years. That works because
    the STOP rule is **prefix-local** — it never reads past the first year to
    overflow — and the server sort puts that prefix at the top of page one, so
    for nearly every seed the exact budget is computable from the one request
    the predicted path was already making (computed budgets across the 58-seed
    validation corpus: mean ~76, max 176). This is what retired the trained
    ``cite_budget`` model from serving: its reason to exist was that computing
    was assumed to need the *whole* pool (~30k citers for DQN) across the
    network, and it doesn't — it needs the top of the ranking, which is one page.

    The probe is conclusive when the rule stops inside it or the citer list
    itself ends inside it. A seed whose top-200 spread so evenly that no year
    overflows pays for one second, ceiling-sized fetch and re-measures over the
    longer ranking (and a rule answer of None — the adaptive toggle off — falls
    back to the flat ``cap``, extending the same way).

    Trimming to the rule's count also restores the ``PER_YEAR_CAP`` invariant
    on this path: a predicted count could only *size* the band, so a blockbuster
    year could exceed the cap; a STOP prefix cannot.

    Args:
        filter_clause: The landmark ``filter=`` value (``cites:`` + date bound).
        cap: The ceiling — the configured ``cite_limit``, or the unbounded cap.
        landmark_budget: Optional rule measuring how many of the ranked pool to
            ship (see :data:`LandmarkBudgetFn`).

    Returns:
        The landmark entries, most-cited first, trimmed to the budget (or cap).

    Raises:
        client.OpenAlexError: When a page request fails after retries.
    """
    if landmark_budget is None:
        return _fetch_citers(filter_clause, "cited_by_count:desc", cap, nodes.NEIGHBOR_SELECT)
    probe_cap = min(_PER_PAGE, cap)
    landmark = _fetch_citers(
        filter_clause, "cited_by_count:desc", probe_cap, nodes.NEIGHBOR_SELECT
    )
    budget = landmark_budget([entry["node"].get("year") for entry in landmark])
    ranking_continues = len(landmark) == probe_cap and probe_cap < cap
    if ranking_continues and (budget is None or budget >= probe_cap):
        landmark = _fetch_citers(filter_clause, "cited_by_count:desc", cap, nodes.NEIGHBOR_SELECT)
        budget = landmark_budget([entry["node"].get("year") for entry in landmark])
    return landmark[:budget] if budget is not None else landmark[:cap]


def citation_relations(
    work_id: str,
    *,
    landmark_limit: int | None,
    latest_limit: int | None,
    band_start: BandStartFn | None = None,
    landmark_budget: LandmarkBudgetFn | None = None,
) -> tuple[list[dict], list[dict]]:
    """Split a seed's OpenAlex citers into landmark and latest relations.

    * **landmark** (green, *Field Landmarks*) — the **all-time most-cited**
      citers: ``to_publication_date:<end of the last landmark year>``,
      ``sort=cited_by_count:desc``. The historic giants; naturally old. With a
      ``landmark_budget`` the band's length is **computed** from the ranking's
      years (the STOP rule over a one-page probe — see
      :func:`_budgeted_landmarks`); without one it's the flat cap.
    * **latest** (light-green, *Latest Publications*) — **recent** citers as
      **per-year bands**: one ``publication_year:<Y>`` query per year (each top
      ``latest_per_year`` by citations), from the band start up to the current
      year. The band span defaults to ``config.graph.latest_band_years`` (below
      the landmark cutoff) plus the ``_LATEST_YEARS`` latest-only years above it,
      but when a ``band_start`` chooser is supplied it may **widen** per seed to
      close the landmark→latest gap (see :func:`bands.earliest_band_year`).
      Anything already a Field Landmark is excluded (a recent *giant* stays a
      landmark, not double-shown). A ``latest_limit`` keeps the **newest** N,
      but the returned order is **oldest-first** — the enumeration rank drives
      the frontend's reveal slider, which should walk toward the present.

    The split is by **publication year**, not an exact date, because OpenAlex
    dating is coarse — many works are year-only, defaulted to ``<year>-01-01``,
    which an exact date window would wrongly drop. Per-year banding gives *even*
    coverage the whole way: a single multi-year query sorted by citations lets its
    oldest year (longest to accrue citations) dominate and starve the newest.

    Args:
        work_id: The seed's bare OpenAlex id (``W…``).
        landmark_limit: Max all-time landmarks, or None for the unbounded cap.
        latest_limit: Max latest citers (keeps the newest), or None for all.
        band_start: Optional per-seed band-start chooser (the shipped landmarks'
            years and the landmark-max year → first band year, or None to keep
            the fixed span). None (the default) always uses the fixed
            ``latest_band_years`` span.
        landmark_budget: Optional rule computing how many of the ranked landmark
            pool to ship (see :data:`LandmarkBudgetFn`); its count wins over
            ``landmark_limit``, which stays the ceiling. None (the default)
            ships the flat cap.

    Returns:
        ``(landmark_entries, latest_entries)`` — each ``[{"node", "influential"}]``.

    Raises:
        client.OpenAlexError: When a query fails after retries.
    """
    current_year = datetime.date.today().year
    max_landmark_year = landmark_max_year(datetime.date.today())
    cap = landmark_limit if landmark_limit is not None else UNBOUNDED_LANDMARK_CAP
    per_year = config.graph.latest_per_year

    # FIELD LANDMARKS: the all-time giants, up to the last landmark year.
    landmark = _budgeted_landmarks(
        f"cites:{work_id},to_publication_date:{max_landmark_year}-12-31",
        cap,
        landmark_budget,
    )
    landmark_ids = {entry["node"]["id"] for entry in landmark}

    # LATEST PUBLICATIONS: one ``publication_year`` band per year, from the band
    # start up to the current year (by citations, one query each so no single year
    # dominates), excluding giants. Uniform per-year bands the whole way — no
    # separate newest-date window — so every recent year gets its own fair slice.
    earliest_band_year = max_landmark_year - config.graph.latest_band_years + 1
    if band_start is not None:
        landmark_years = [entry["node"].get("year") for entry in landmark]
        adaptive_start = band_start(
            [year for year in landmark_years if year], max_landmark_year
        )
        if adaptive_start is not None:
            earliest_band_year = adaptive_start
    recent: list[dict] = []
    for year in range(earliest_band_year, current_year + 1):
        recent += _fetch_citers(
            f"cites:{work_id},publication_year:{year}",
            "cited_by_count:desc",
            per_year,
            nodes.NEIGHBOR_SELECT,
        )
    latest: list[dict] = []
    seen: set[str] = set()
    for entry in recent:
        node_id = entry["node"]["id"]
        if node_id not in seen and node_id not in landmark_ids:
            seen.add(node_id)
            latest.append(entry)
    # Select newest-first (so a limit keeps the newest N), then flip: rank 0 is
    # the OLDEST banded year and the frontier comes last, so the frontend's
    # reveal slider walks forward through time toward the present.
    latest.sort(key=_by_recency, reverse=True)
    if latest_limit is not None:
        latest = latest[:latest_limit]
    latest.reverse()

    return landmark, latest


def _hydrate_ids(work_ids: list[str]) -> list[dict]:
    """Batch-hydrate bare OpenAlex ids (``W…``) into node entries.

    Uses the ``openalex_id:`` OR filter (capped at ``_OR_FILTER_MAX`` values per
    request, so ids are chunked). The result order follows OpenAlex's, deduped.

    Args:
        work_ids: Bare OpenAlex work ids.

    Returns:
        ``[{"node": <node dict>}]`` entries (no ``influential`` — these aren't
        citations), skipping works with no usable id.

    Raises:
        client.OpenAlexError: When a request fails after retries.
    """
    entries: list[dict] = []
    seen: set[str] = set()
    for start in range(0, len(work_ids), _OR_FILTER_MAX):
        chunk = work_ids[start : start + _OR_FILTER_MAX]
        params = {
            "filter": "openalex_id:" + "|".join(chunk),
            "per-page": str(_OR_FILTER_MAX),
            "select": nodes.NEIGHBOR_SELECT,
        }
        data = client.request(client.works_url(params))
        results = data.get("results") if isinstance(data, dict) else None
        for work in results or []:
            node = nodes.node(work)
            if node and node["id"] not in seen:
                seen.add(node["id"])
                entries.append({"node": node})
    return entries


def related_works(work_id: str, limit: int | None) -> list[dict]:
    """A paper's OpenAlex *related works* — the OA analogue of S2's SPECTER2
    recommendations (the "similar" hop).

    Weaker than S2's embedding similarity: OpenAlex's ``related_works`` is
    concept/citation-overlap, and it can surface duplicates. Used only by the
    researcher's ``expand_node(relation="similar")`` under the OpenAlex provider
    (the seed-graph *Similar* relation was retired in v5.0.0). We read the work's
    ``related_works`` id list, then batch-hydrate them into nodes.

    Args:
        work_id: The seed's bare OpenAlex id (``W…``).
        limit: Max related works, or None for all of them.

    Returns:
        ``[{"node": <node dict>}]`` entries, in OpenAlex's related order.

    Raises:
        client.OpenAlexError: When a request fails after retries.
    """
    work = _try_entity(work_id, "id,related_works")
    if not work:
        return []
    related = [nodes.bare_openalex_id(url) for url in (work.get("related_works") or [])]
    ids = [work_ref for work_ref in related if work_ref]
    if limit is not None:
        ids = ids[:limit]
    return _hydrate_ids(ids)


def citations(work_id: str, limit: int | None) -> list[dict]:
    """A seed's landmark citers, most-cited first (the single-relation view for
    on-demand graph expansion — the OpenAlex twin of ``s2.citations``).

    Args:
        work_id: The seed's bare OpenAlex id (``W…``).
        limit: Max citers, or None for the unbounded cap.

    Returns:
        ``[{"node": <node dict>}]`` entries, most-cited first.

    Raises:
        client.OpenAlexError: When the query fails after retries.
    """
    return _fetch_citers(
        f"cites:{work_id}",
        "cited_by_count:desc",
        limit if limit is not None else UNBOUNDED_LANDMARK_CAP,
        nodes.NEIGHBOR_SELECT,
    )
