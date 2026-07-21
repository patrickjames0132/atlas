"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
Seed discovery: a live relevance search across Semantic Scholar, plus an
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

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

import time

from ...agents import query_analyst
from ...config import config
from ...integrations import arxiv, openalex
from ...integrations import semantic_scholar as s2
from ...storage import cache
from ..graph import Provider


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


def _verified_titles_openalex(titles: list[str]) -> list[dict]:
    """Resolve analyst-suggested titles against OpenAlex — the OpenAlex twin of
    :func:`_verified_titles`.

    Each title is resolved with ``openalex.resolve_work`` (title search,
    most-cited first), so a confidently-recalled paper leads the OpenAlex results
    the same way it does the S2 ones. Failures skip the title, never the search.

    Args:
        titles: Exact-title suggestions, most relevant first.

    Returns:
        The matched papers' normalized node dicts, deduped, in suggestion order.
    """
    verified: list[dict] = []
    seen: set[str] = set()
    for title in titles:
        try:
            work = openalex.resolve_work(arxiv_id=None, title=title)
        except openalex.OpenAlexError:
            continue
        node = openalex.node(work) if work else None
        if node and node["id"] not in seen:
            seen.add(node["id"])
            verified.append(node)
    return verified


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


def _s2_live(
    query: str,
    limit: int,
    year_from: int | None,
    year_to: int | None,
    fields_of_study: list[str] | None,
    analyst: bool,
) -> list[dict]:
    """The Semantic Scholar live-search body: analyst expansion + verified
    titles + lexical search, merged.

    Args:
        query: The raw user query (already non-blank, non-pasted-id).
        limit: Maximum papers to return.
        year_from: Earliest publication year (inclusive), or None.
        year_to: Latest publication year (inclusive), or None.
        fields_of_study: S2 fields of study to restrict to (any-of), or None.
        analyst: Run the query analyst. False skips the LLM round-trip
            entirely — no expansion, no recalled titles — and searches the
            words as typed.

    Returns:
        Relevance-ranked node dicts, verified title matches leading.

    Raises:
        s2.S2Error: When the Semantic Scholar request fails after retries.
    """
    analysis = _analyze(query) if analyst else None
    # Confidently recalled papers, verified via S2 title match, lead the
    # results — like the id path, an exact resolution outranks lexical hits
    # and bypasses the filters (it's the paper the query *means*).
    verified = _verified_titles(analysis.known_titles) if analysis else []
    hits = s2.search_papers(
        analysis.expanded_query if analysis else query,
        limit=limit,
        year_from=year_from,
        year_to=year_to,
        fields_of_study=fields_of_study,
    )
    # search_papers returns the traversal shape (``[{"node": ...}]``); unwrap to
    # bare node dicts so live and local search return the same thing.
    verified_ids = {node["id"] for node in verified}
    lexical = [hit["node"] for hit in hits if hit["node"]["id"] not in verified_ids]
    return (verified + lexical)[:limit]


def _openalex_live(
    query: str,
    limit: int,
    year_from: int | None,
    year_to: int | None,
    fields: list[str] | None,
    analyst: bool,
) -> list[dict]:
    """The OpenAlex live-search body — the twin of :func:`_s2_live`.

    Same shape (analyst expansion + verified titles lead + lexical search), but
    resolved through OpenAlex, with the field filter expressed in OpenAlex's own
    field ids (``openalex.vocab``) rather than S2's field names.

    Args:
        query: The raw user query (already non-blank, non-pasted-id).
        limit: Maximum papers to return.
        year_from: Earliest publication year (inclusive), or None.
        year_to: Latest publication year (inclusive), or None.
        fields: OpenAlex field ids to restrict to (any-of), or None.
        analyst: Run the query analyst. False skips the LLM round-trip
            entirely — no expansion, no recalled titles — and searches the
            words as typed.

    Returns:
        Relevance-ranked node dicts, verified title matches leading.

    Raises:
        openalex.OpenAlexError: When an OpenAlex request fails after retries.
    """
    analysis = _analyze(query) if analyst else None
    verified = _verified_titles_openalex(analysis.known_titles) if analysis else []
    hits = openalex.search_papers(
        analysis.expanded_query if analysis else query,
        limit=limit,
        year_from=year_from,
        year_to=year_to,
        fields=fields,
    )
    # openalex.search_papers already returns bare node dicts (unlike S2's
    # ``[{"node": ...}]``), so no unwrap is needed.
    verified_ids = {node["id"] for node in verified}
    lexical = [hit for hit in hits if hit["id"] not in verified_ids]
    return (verified + lexical)[:limit]


def live_search(
    query: str,
    limit: int = 25,
    year_from: int | None = None,
    year_to: int | None = None,
    fields_of_study: list[str] | None = None,
    provider: Provider = "s2",
    analyst: bool = True,
) -> list[dict]:
    """Relevance-search the selected provider to find a seed paper.

    Args:
        query: Free-text search terms (keywords, a title, an author).
        limit: Maximum papers to return.
        year_from: Earliest publication year (inclusive), or None.
        year_to: Latest publication year (inclusive), or None.
        fields_of_study: Field filter values to restrict to (any-of), or None.
            **Provider-specific:** S2 field names on the S2 path
            (``semantic_scholar.vocab``), OpenAlex field ids on the OpenAlex path
            (``openalex.vocab``). The route validates against the right vocabulary.
        provider: Which backend to search (``s2`` / ``openalex``) — matches the
            graph provider so a hit explores under the backend that found it.
        analyst: Run the query analyst before the lexical search (the default).
            False skips the LLM entirely — no expansion, no recalled titles,
            no spend — and searches the words as typed. Irrelevant for a
            pasted id/URL, which never touches the analyst anyway.

    Returns:
        Relevance-ranked node dicts (the shared node shape — the same a graph
        neighbor has). Empty list for a blank query. A pasted arXiv id/URL
        returns exactly that paper (or nothing when the provider can't resolve
        it). Results are cached for a day (keyed by provider), so a repeated
        search answers instantly — no analyst call, no live request.

    Raises:
        s2.S2Error: When a Semantic Scholar request fails (the ``s2`` path).
        openalex.OpenAlexError: When an OpenAlex request fails (the ``openalex``
            path).
    """
    query = (query or "").strip()
    if not query:
        return []
    # A pasted arXiv id/URL is a statement of intent, not a query: skip
    # expansion and filters and land on that exact paper, resolved through the
    # active provider. An id the provider doesn't know returns nothing.
    pasted_id = arxiv.extract_id(query)
    if pasted_id:
        if provider == "openalex":
            node = openalex.get_paper(pasted_id)
            return [node] if node else []
        paper = s2.get_paper(f"ARXIV:{pasted_id}")
        return [paper] if paper else []

    # Whole-result cache, keyed by provider (an S2 search and an OpenAlex search
    # for the same query are different searches). The key also carries the
    # filters and the analyst flag (raw and expanded searches return different
    # results); the analyst's view is frozen for the TTL, fine for a day.
    fields_key = ",".join(fields_of_study) if fields_of_study else ""
    analyst_key = "llm" if analyst else "raw"
    cache_key = (
        f"livesearch:{provider}:{query.lower()}:{limit}:"
        f"{year_from or ''}:{year_to or ''}:{fields_key}:{analyst_key}"
    )
    cached = cache.get(cache_key, config.graph.cache_ttl)
    if cached is not None:
        return cached

    if provider == "openalex":
        results = _openalex_live(query, limit, year_from, year_to, fields_of_study, analyst)
    else:
        results = _s2_live(query, limit, year_from, year_to, fields_of_study, analyst)
    cache.set(cache_key, results)
    return results


def local_search(
    query: str,
    limit: int = 10,
    year_from: int | None = None,
    year_to: int | None = None,
    provider: Provider = "s2",
) -> list[dict]:
    """Search papers already sitting in the local graph-snapshot cache, scoped to
    one provider.

    Matches every whitespace token of ``query`` against a paper's title +
    authors (case-insensitive substring). Stale snapshots still count — a
    paper's title doesn't expire. Results are deduped across snapshots (keeping
    whichever record carries more detail) and ranked: whole-phrase title matches
    first, then papers explored directly as seeds, then by citation count.

    **Scoped to ``provider``:** since snapshots are cached per provider
    (``graph:<provider>:<seed>``), only the selected backend's snapshots are
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
        Hit dicts with keys ``id, arxiv_id, title, authors, year,
        citation_count, url, has_graph`` — ``has_graph`` is True when a *fresh*
        snapshot exists for the paper as a seed under this provider, i.e.
        exploring it won't touch the provider's API. (No field filter here —
        these are cached nodes, matched purely on text.)

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

    for _key, snapshot, created in cache.scan(f"graph:{provider}:"):
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
