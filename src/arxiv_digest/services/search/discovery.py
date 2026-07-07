"""Seed discovery: a live relevance search across Semantic Scholar, plus an
instant search over the local snapshot cache.

arXiv Atlas doesn't store a paper corpus, so the live "search" is a thin pass
through to S2's ``/paper/search`` to find the paper you want to drop into the
graph; its id is then handed to ``graph.build_graph``. This replaced the earlier
arXiv-only search — S2 has far wider coverage (200M+ papers across venues, not
just arXiv preprints).

``local_search`` is the cache-first complement: it scans the graph snapshots
already sitting in the SQLite cache and matches papers by title/authors. It
answers instantly and works even when Semantic Scholar is rate-limiting us — if
you've seen a paper on a graph before, you can find it again offline.
"""

from __future__ import annotations

import time

from ...agents import query_analyst
from ...config import config
from ...integrations import arxiv
from ...integrations import semantic_scholar as s2
from ...storage import cache


def _analyze(query: str) -> query_analyst.Expansion:
    """Query-analysis seam — delegates to the query analyst agent.

    S2 search is lexical, so a seminal paper that never spells out an acronym
    in its title/abstract is unfindable from the acronym alone. The analyst
    attacks the gap from both ends: an expanded query ("DQN" -> "DQN deep
    Q-network deep Q-learning") for the lexical search, and the exact titles
    of confidently recalled papers for title-match verification. This seam
    started life as a documented passthrough so the call site wouldn't move
    when the agent arrived — and it didn't.

    Args:
        query: The raw user query.

    Returns:
        The analyst's ``Expansion`` — or a passthrough (query unchanged, no
        titles): ``analyze`` degrades on any failure, so search never breaks
        because the LLM hiccuped.
    """
    return query_analyst.analyze(query)


def _verified_titles(titles: list[str]) -> list[dict]:
    """Resolve analyst-suggested titles against S2's title match.

    Suggestions come from the model's parametric knowledge (the acronym→paper
    associations Google resolves via link text); this is the verification
    half — only papers S2 actually matches are returned, so an invented
    title costs one lookup and produces nothing. Match failures (including
    S2 errors) skip the title rather than break the search: these hits are
    an enhancement, and the lexical search still runs either way.

    Args:
        titles: Exact-title suggestions, most relevant first.

    Returns:
        The matched papers' node dicts, deduped, in suggestion order.
    """
    verified: list[dict] = []
    seen: set[str] = set()
    for title in titles:
        try:
            node = s2.match_title(title)
        except s2.S2Error:
            continue
        if node and node["id"] not in seen:
            seen.add(node["id"])
            verified.append(node)
    return verified


def live_search(
    query: str,
    limit: int = 25,
    year_from: int | None = None,
    year_to: int | None = None,
    fields_of_study: list[str] | None = None,
) -> list[dict]:
    """Relevance-search Semantic Scholar to find a seed paper.

    Args:
        query: Free-text search terms (keywords, a title, an author).
        limit: Maximum papers to return.
        year_from: Earliest publication year (inclusive), or None.
        year_to: Latest publication year (inclusive), or None.
        fields_of_study: S2 fields of study to restrict to (any-of), or None.
            Values are S2's own field names (see ``semantic_scholar.vocab``).

    Returns:
        Relevance-ranked node dicts (S2's node shape — the same shape a graph
        neighbor has). Empty list for a blank query. A pasted arXiv id/URL
        returns exactly that paper (or nothing when S2 doesn't know it).
        Results are cached for a day (same TTL as a graph snapshot), so a
        repeated search answers instantly — no analyst call, no S2.

    Raises:
        s2.S2Error: When the Semantic Scholar request fails after retries.
    """
    query = (query or "").strip()
    if not query:
        return []
    # A pasted arXiv id/URL is a statement of intent, not a query: skip
    # expansion (nothing to expand — an "improved" id could only be a wrong
    # one) and filters (they never apply to an explicit lookup), and land on
    # that exact paper. An id S2 doesn't know returns nothing — falling
    # through to a lexical search of the id text could only produce junk.
    pasted_id = arxiv.extract_id(query)
    if pasted_id:
        paper = s2.get_paper(f"ARXIV:{pasted_id}")
        return [paper] if paper else []

    # Whole-result cache: the expensive part of a live search is the analyst
    # call plus two-ish throttled S2 requests, and re-typing a recent query
    # is a common move — searching "DQN" a second time should be instant.
    # The key carries the filters (a filtered search is a different search);
    # the analyst's view is frozen for the TTL, which is fine for a day.
    fields_key = ",".join(fields_of_study) if fields_of_study else ""
    cache_key = (
        f"livesearch:{query.lower()}:{limit}:{year_from or ''}:{year_to or ''}:{fields_key}"
    )
    cached = cache.get(cache_key, config.graph.cache_ttl)
    if cached is not None:
        return cached

    analysis = _analyze(query)
    # Confidently recalled papers, verified via S2 title match, lead the
    # results — like the id path, an exact resolution outranks lexical hits
    # and bypasses the filters (it's the paper the query *means*).
    verified = _verified_titles(analysis.known_titles)
    hits = s2.search_papers(
        analysis.expanded_query,
        limit=limit,
        year_from=year_from,
        year_to=year_to,
        fields_of_study=fields_of_study,
    )
    # search_papers returns the traversal shape (``[{"node": ...}]``); unwrap to
    # bare node dicts so live and local search return the same thing.
    verified_ids = {node["id"] for node in verified}
    lexical = [hit["node"] for hit in hits if hit["node"]["id"] not in verified_ids]
    results = (verified + lexical)[:limit]
    cache.set(cache_key, results)
    return results


def local_search(
    query: str,
    limit: int = 10,
    year_from: int | None = None,
    year_to: int | None = None,
) -> list[dict]:
    """Search papers already sitting in the local graph-snapshot cache.

    Matches every whitespace token of ``query`` against a paper's title +
    authors (case-insensitive substring). Stale snapshots still count — a
    paper's title doesn't expire. Results are deduped across snapshots (keeping
    whichever record carries more detail) and ranked: whole-phrase title matches
    first, then papers explored directly as seeds, then by citation count.

    Args:
        query: The search text; blank/whitespace-only returns no hits.
        limit: Maximum hits to return.
        year_from: Earliest publication year (inclusive), or None. When a bound
            is set, papers with no known year are excluded — a user filtering by
            date doesn't want undatable hits.
        year_to: Latest publication year (inclusive), or None.

    Returns:
        Hit dicts with keys ``id, arxiv_id, title, authors, year,
        citation_count, url, has_graph`` — ``has_graph`` is True when a *fresh*
        snapshot exists for the paper as a seed, i.e. exploring it won't touch
        the S2 API. (No field filter here — these are cached S2 nodes, matched
        purely on text.)

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

    for _key, snapshot, created in cache.scan("graph:"):
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
    return [
        {
            "id": node["id"],
            "arxiv_id": node.get("arxiv_id"),
            "title": node.get("title"),
            "authors": node.get("authors"),
            "year": node.get("year"),
            "citation_count": node.get("citation_count"),
            "url": node.get("url"),
            "has_graph": bool(
                fresh_seeds & {ident for ident in (node["id"], node.get("arxiv_id")) if ident}
            ),
        }
        for node in hits
    ]
