"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
Seed discovery over the local snapshot cache.

``local_search`` scans the graph snapshots already sitting in the SQLite cache
and matches papers by title/authors. It answers instantly and works even when
the provider is rate-limiting us — if you've seen a paper on a graph before,
you can find it again offline.

**Live search used to live here too** (``live_search``: query-analyst expansion,
verified title matches, then a lexical provider search). It was retired in
v7.6.0 along with the ``query_analyst`` agent, because the paper scout does all
three jobs better — it reformulates instead of expanding once, it resolves
recalled titles through ``match_title``, and it can look at what came back and
try again. Two implementations of "search papers" was the same duplication the
v7.0.0 worker split was made to end. This module kept the half the scout
doesn't do: reading the cache, which the scout now calls *into* rather than
duplicating.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

import time

from ...config import config
from ...integrations import openalex
from ...integrations import semantic_scholar as s2
from ...storage import cache
from ..graph import Provider, snapshot_prefix


def cached_nodes(
    query: str,
    limit: int = 10,
    year_from: int | None = None,
    year_to: int | None = None,
    provider: Provider = "s2",
) -> list[dict]:
    """:func:`local_search`'s hits, ready to hand out as papers.

    Shared by the two callers that want cached papers in the shape everything
    else speaks: the scout's ``search`` tool (which merges them with live hits,
    dropping ``has_graph`` on the way) and ``/api/search`` (which streams them
    as an instant first list, before the scout has finished its first provider
    call, and *keeps* ``has_graph`` — a paper whose own graph is already on
    disk opens with no provider call at all, which is worth telling the
    reader).

    Args:
        query: The search text.
        limit: Maximum hits.
        year_from: Earliest publication year (inclusive), or None.
        year_to: Latest publication year (inclusive), or None.
        provider: The selected backend — only its snapshots are searched.

    Returns:
        Node dicts (including ``has_graph``), best match first. Empty when
        nothing matches.

    Raises:
        sqlite3.Error: On cache database failures (callers degrade to empty).
    """
    return local_search(query, limit, year_from, year_to, provider)


def valid_fields(provider: Provider, values: list[str]) -> list[str]:
    """Keep only the field-filter values that exist in a provider's vocabulary.

    The two vocabularies are disjoint — S2 filters on its own field *names*,
    OpenAlex on numeric ``topics.field.id`` values — so a value that survives a
    provider switch is meaningless rather than merely stale. Dropping it beats
    passing it on: the filter binds every search now, and one nonsense value
    would narrow a search to nothing while the UI still showed a chip.

    Shared by both routes that accept a filter (direct search and ask), so the
    same value is judged the same way whichever bar sent it.

    Args:
        provider: ``s2`` or ``openalex`` — whose vocabulary to validate against.
        values: Candidate field values, as received from the client.

    Returns:
        The surviving values, in the order given. Empty when none survive.
    """
    if provider == "openalex":
        known: frozenset[str] = openalex.vocab.valid_field_ids()
    else:
        known = s2.vocab.valid_fields()
    return [value for value in values if value in known]


def local_search(
    query: str,
    limit: int = 10,
    year_from: int | None = None,
    year_to: int | None = None,
    provider: Provider = "s2",
) -> list[dict]:
    """Search papers already sitting in the local graph-snapshot cache, scoped to
    one provider.

    Returns **whole node dicts** (plus a ``has_graph`` badge), because one
    caller builds graph nodes straight out of them; :func:`display_hits`
    trims them for the search list.

    Matches every whitespace token of ``query`` against a paper's title +
    authors (case-insensitive substring). Stale snapshots still count — a
    paper's title doesn't expire. Results are deduped across snapshots (keeping
    whichever record carries more detail) and ranked: whole-phrase title matches
    first, then papers explored directly as seeds, then by citation count.

    **Scoped to ``provider``:** since snapshots are cached per provider
    (``snapshot_prefix``), only the selected backend's snapshots are
    scanned — so a cached paper surfaces here (and the ``has_graph`` "instant"
    badge is truthful) only when it can actually be explored *instantly under
    the provider the user has selected*, not merely because some *other*
    provider once cached it.

    Args:
        query: The search text; blank/whitespace-only returns no hits.
        limit: Maximum hits to return.
        year_from: Earliest publication year (inclusive), or None. When a bound
            is set, papers with no known year are excluded — a user filtering by
            date doesn't want undatable hits.
        year_to: Latest publication year (inclusive), or None.
        provider: The selected backend — only its snapshots are searched.

    Returns:
        The matching **graph nodes**, each with an added ``has_graph`` —
        True when a *fresh* snapshot exists for the paper as a seed under this
        provider, i.e. exploring it won't touch the provider's API. (No field
        filter here — these are cached nodes, matched purely on text.)

    Raises:
        sqlite3.Error: On cache database failures.
    """
    tokens = [token for token in (query or "").lower().split() if token]
    if not tokens:
        return []
    phrase = " ".join(tokens)

    def year_ok(node: dict) -> bool:
        """Apply the optional year window to a candidate node.

        Args:
            node: The candidate node dict.

        Returns:
            True when no bound is set, or the node's year falls inside the
            window (unknown years fail a bounded filter).
        """
        if year_from is None and year_to is None:
            return True
        year_value = node.get("year")
        if not isinstance(year_value, int):
            return False
        if year_from is not None and year_value < year_from:
            return False
        if year_to is not None and year_value > year_to:
            return False
        return True

    now = time.time()
    fresh_seeds: set[str] = set()  # ids whose own graph is cached & unexpired
    best: dict[str, dict] = {}  # paper id -> richest matching record

    for _key, snapshot, created in cache.scan(snapshot_prefix(provider)):
        if not isinstance(snapshot, dict):
            continue
        if (now - created) <= config.graph.cache_ttl:
            seed = snapshot.get("seed") or {}
            fresh_seeds.update(
                value for value in (seed.get("arxiv_id"), seed.get("id")) if value
            )
        for node in snapshot.get("nodes") or []:
            paper_id = node.get("id")
            title = node.get("title") or ""
            if not paper_id or not title:
                continue
            haystack = f"{title} {node.get('authors') or ''}".lower()
            if not all(token in haystack for token in tokens):
                continue
            if not year_ok(node):
                continue
            previous = best.get(paper_id)
            # Across snapshots the same paper may appear as a bare neighbor or a
            # hydrated seed — keep whichever record carries more detail.
            if previous is None or (node.get("authors") and not previous.get("authors")):
                best[paper_id] = node

    def rank(node: dict) -> tuple:
        """Sort key: phrase-in-title first, then seeds, then citation count.

        Args:
            node: A candidate node dict.

        Returns:
            A tuple that sorts better matches first.
        """
        return (
            phrase not in (node.get("title") or "").lower(),  # phrase-in-title first
            not node.get("is_seed"),  # papers you explored directly next
            -(node.get("citation_count") or 0),
        )

    hits = sorted(best.values(), key=rank)[:limit]
    # **The whole node, not a projection of it.** These are real graph nodes
    # lifted out of cached snapshots, and one caller — the paper scout — turns
    # them straight into `DiscoveredNode`s, which requires the full shape.
    # Returning the search list's display fields instead used to make every
    # cache hit raise a `ValidationError` inside `find_papers`, retry once, and
    # kill the entire answer (see `docs/bugs.md`). The wire shape belongs at
    # the wire: `display_hits` does that projection for the route.
    return [
        {
            **node,
            "has_graph": bool(
                fresh_seeds & {ident for ident in (node["id"], node.get("arxiv_id")) if ident}
            ),
        }
        for node in hits
    ]


#: What the search list actually renders. Abstracts are large and the list
#: shows none of them, so the projection is worth keeping — it just belongs
#: here, at the boundary, rather than in the shared cache lookup.
_DISPLAY_FIELDS = ("id", "arxiv_id", "title", "authors", "year", "citation_count", "url")


def display_hits(nodes: list[dict]) -> list[dict]:
    """Trim cached nodes to what the search list shows.

    Args:
        nodes: Full node dicts from :func:`local_search`.

    Returns:
        One dict per node with the display fields plus ``has_graph``.
    """
    return [
        {**{key: node.get(key) for key in _DISPLAY_FIELDS}, "has_graph": node.get("has_graph", False)}
        for node in nodes
    ]
