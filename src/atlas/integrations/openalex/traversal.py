"""Resolving a seed to its OpenAlex work and walking its citers — the OpenAlex
half of the hybrid graph build.

This is the payoff of the 2026-07-09 spike: a seed's citers come from
**server-sorted** ``cites:`` queries, edge guaranteed by the filter. That retires
the entire S2 ``_mined_landmarks`` apparatus (harvest → co-citation rank →
verify), which existed only to work around S2's newest-first, offset-capped
citation endpoint. The citation relation is:

* **landmark** (*Field Landmarks*) — the all-time most-cited citers
  (``cited_by_count:desc``). The historic giants; naturally old.
* **latest** (*Latest Publications*) — recent citers: the newest window (by date)
  plus per-year bands over the years just below it (one ``cited_by_count:desc``
  query *per year*, so no single year dominates — a subtlety we hit live). A
  recent paper that's also an all-time giant stays a landmark, not double-shown;
  the rest ship oldest-first (the reveal slider walks toward the present).

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

from ...config import config
from . import client, nodes

log = logging.getLogger(__name__)

# OpenAlex caps ``per-page`` at 200.
_PER_PAGE = 200

# The landmark/latest split is by **publication YEAR**, not an exact date, on
# purpose: OpenAlex dates are coarse — a large fraction of works carry a
# year-only ``publication_date`` defaulted to ``<year>-01-01`` — so a rolling
# 12-month *date* window (what the S2 path used) silently drops almost every
# recent-year citer (verified live: DQN had 1 citer in a from-date window vs 30
# in the same year). So ``latest`` = citers from the last ``_LATEST_YEARS``
# calendar years; ``landmark`` = everything older.
_LATEST_YEARS = 2  # current year + previous year → the recent frontier

# How many citers to pull for an *unbounded* relation (config ship count =
# ``null``). Server-sorted, so these are the top-N by the relation's key — plenty
# of range for the frontend's reveal-on-demand slider without paging a mega
# seed's entire citer list (Hawking has ~5.7k; "Attention" ~150k). An explicit
# numeric limit overrides this.
_UNBOUNDED_LANDMARK_CAP = 500
_UNBOUNDED_LATEST_CAP = 200


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


def resolve_work(*, arxiv_id: str | None, title: str | None) -> dict | None:
    """Find the OpenAlex work for a seed the app resolved through S2.

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
        title: The seed's title (from the S2 seed node).

    Returns:
        The raw OpenAlex work object (carrying ``id``), or None when neither
        path finds it.
    """
    if arxiv_id:
        work = _try_entity(f"doi:10.48550/arXiv.{arxiv_id}", nodes.NEIGHBOR_SELECT)
        if work:
            return work
    cleaned = _clean_search(title or "")
    if not cleaned:
        return None
    params = {
        "filter": f"title.search:{cleaned}",
        "sort": "cited_by_count:desc",
        "per-page": "1",
        "select": nodes.NEIGHBOR_SELECT,
    }
    data = client.request(client.works_url(params))
    results = data.get("results") if isinstance(data, dict) else None
    return results[0] if results else None


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
    year — the ``""`` date floor."""
    node = entry["node"]
    return (node.get("year") or 0, node.get("pub_date") or "")


def citation_relations(
    work_id: str,
    *,
    landmark_limit: int | None,
    latest_limit: int | None,
) -> tuple[list[dict], list[dict]]:
    """Split a seed's OpenAlex citers into landmark and latest relations.

    * **landmark** (green, *Field Landmarks*) — the **all-time most-cited**
      citers: ``to_publication_date:<end of the last landmark year>``,
      ``sort=cited_by_count:desc``. The historic giants; naturally old.
    * **latest** (light-green, *Latest Publications*) — **recent** citers, from:
      - the newest window — ``from_publication_date:<first latest year>-01-01``,
        ``sort=publication_date:desc`` (the last ``_LATEST_YEARS`` calendar years),
      - plus per-year bands — ``config.graph.latest_band_years`` separate
        ``publication_year:<Y>`` queries (each top ``latest_per_year`` by
        citations) over the years just below the window.
      Anything already a Field Landmark is excluded (a recent *giant* stays a
      landmark, not double-shown). A ``latest_limit`` keeps the **newest** N,
      but the returned order is **oldest-first** — the enumeration rank drives
      the frontend's reveal slider, which should walk toward the present.

    The split is by **publication year**, not an exact date, because OpenAlex
    dating is coarse — many works are year-only, defaulted to ``<year>-01-01``,
    which an exact rolling window would wrongly drop. Per-year banding of the
    recent side gives *even* coverage: a single recent-window query sorted by
    citations lets its oldest year (longest to accrue citations) dominate.

    Args:
        work_id: The seed's bare OpenAlex id (``W…``).
        landmark_limit: Max all-time landmarks, or None for the unbounded cap.
        latest_limit: Max latest citers (keeps the newest), or None for all.

    Returns:
        ``(landmark_entries, latest_entries)`` — each ``[{"node", "influential"}]``.

    Raises:
        client.OpenAlexError: When a query fails after retries.
    """
    current_year = datetime.date.today().year
    latest_from_year = current_year - (_LATEST_YEARS - 1)  # newest window: years ≥ this
    landmark_max_year = latest_from_year - 1  # landmarks capped here; below-window bands end here
    cap = landmark_limit if landmark_limit is not None else _UNBOUNDED_LANDMARK_CAP
    per_year = config.graph.latest_per_year

    # FIELD LANDMARKS: the all-time giants, up to the last landmark year.
    landmark = _fetch_citers(
        f"cites:{work_id},to_publication_date:{landmark_max_year}-12-31",
        "cited_by_count:desc",
        cap,
        nodes.NEIGHBOR_SELECT,
    )
    landmark_ids = {entry["node"]["id"] for entry in landmark}

    # LATEST PUBLICATIONS: the newest window (by date) + per-year recent bands (by
    # citations, one query each so no single year dominates), excluding giants.
    recent = _fetch_citers(
        f"cites:{work_id},from_publication_date:{latest_from_year}-01-01",
        "publication_date:desc",
        latest_limit if latest_limit is not None else _UNBOUNDED_LATEST_CAP,
        nodes.NEIGHBOR_SELECT,
    )
    earliest_band_year = landmark_max_year - config.graph.latest_band_years + 1
    for year in range(earliest_band_year, landmark_max_year + 1):
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
        limit if limit is not None else _UNBOUNDED_LANDMARK_CAP,
        nodes.NEIGHBOR_SELECT,
    )
