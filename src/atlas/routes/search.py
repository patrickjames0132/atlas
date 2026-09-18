"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
Seed-search routes: direct search (the paper scout run without the researcher
above it, under binding date/field filters) and the field vocabularies that
power the filter picker.

GET /api/search?q=&provider=&limit=&year_from=&year_to=&fields=
                                 -> direct search (SSE): the paper scout, alone
GET /api/taxonomy/<provider>     -> a provider's field vocabulary (s2 / openalex)

The instant cache search that used to sit here (``/api/local_search``) is gone
as of v7.6.0 — not because the cache stopped mattering, but because the scout
reads it directly inside its own search tool. One path to one source.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from queue import Empty, Queue
from typing import Iterator

from flask import Blueprint, jsonify, request
from flask.typing import ResponseReturnValue

from ..agents import streams, traversal
from ..agents.workers.search import papers
from ..integrations import openalex, semantic_scholar
from ..services import search as search_service
from ..services.graph import Provider, resolve_provider
from .sse import sse, sse_response

# Module logger, NOT current_app.logger: the SSE generator below runs during
# response iteration, after the app context is gone.
log = logging.getLogger(__name__)

bp = Blueprint("search", __name__)

#: Where a direct search's nickname resolve runs while the scout works. Its
#: own pool rather than the agent loop because :func:`paper_by_name` is
#: synchronous (a ``run_sync`` micro-agent plus a blocking provider call) and
#: must not sit on the loop the scout is streaming from. Small: one resolve per
#: search, and searches are something a reader does one at a time.
_RESOLVERS = ThreadPoolExecutor(max_workers=4, thread_name_prefix="atlas-name-resolve")

#: The trace chip a successful resolve leaves behind, in the same words the
#: `@`-mention dropdown uses for the phase. Only a hit gets a chip: most
#: queries are not a paper's name, and "nothing new" after every search would
#: be noise about a step the reader never asked for.
_RESOLVE_LABEL = "Working out which paper “{query}” is"

_PICKER_BRIEF = (
    "\n\n(What you find goes straight to a reader choosing ONE paper to open on "
    "a citation graph, so come back with a SPREAD of candidates rather than a "
    "single best answer. Even when one paper is obviously the one meant — an "
    "acronym you recognize, an exact title — lead with it and KEEP LOOKING for "
    "the work around it. Stopping at one is the failure mode here: a picker "
    "with a single row in it has made the reader's choice for them. Aim for "
    "roughly 8-15 papers unless the topic genuinely has fewer.)"
)
"""How direct search reframes the scout's stopping rule.

The scout's own prompt tells it to stop as soon as the papers in hand answer
the request, which is right when a researcher is waiting on them and wrong
when a *reader* is: the first thing direct search shipped with returned one
paper for "dqn" — correctly, and uselessly, because there was nothing to
choose between. Same worker, different consumer, so the brief rides on the
call rather than moving into the shared prompt."""


def _lookup_frames(label: str, papers: list[dict] | None) -> list[str]:
    """One lookup, as the frames it produces — announced, then answered.

    Announced (``papers is None``) it is a single pending chip. Answered, it is
    the finished chip *plus* the papers it turned up, so the reader's list
    grows lookup by lookup instead of appearing all at once when the whole run
    ends. That is the difference between watching a search work and watching a
    blank panel: a scout finds papers a batch at a time, and there is no
    reason to sit on them.

    Args:
        label: The lookup in reader-facing words.
        papers: The new papers it produced, or None for the announcement that
            it has only just started.

    Returns:
        The SSE frames, in order.
    """
    if papers is None:
        return [sse("trace", {"action": "search", "ok": True, "query": label, "pending": True})]
    # The count is the length — a chip without one renders "nothing new", which
    # made every lookup look like a miss back when it was omitted.
    frames = [sse("trace", {"action": "search", "ok": True, "query": label, "found": len(papers)})]
    if papers:
        frames.append(sse("papers", {"papers": papers}))
    return frames


def _opt_year(name: str) -> int | None:
    """Parse an optional year query arg.

    Args:
        name: The query-arg name (``year_from`` / ``year_to``).

    Returns:
        The year as an int, or None when absent/blank/non-numeric — filters
        are strictly optional, so garbage degrades to "no filter" rather
        than erroring.
    """
    raw = (request.args.get(name) or "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _opt_fields(provider: Provider) -> list[str] | None:
    """Parse and validate the optional ``fields`` query arg for a provider.

    The field-filter values are provider-specific: S2 fields are their own
    names, OpenAlex fields are numeric ids (``topics.field.id``). Each is
    validated against that provider's vocabulary; unknown values are silently
    dropped (they can only come from a stale/forged client — e.g. S2 field names
    left over after switching to OpenAlex).

    Args:
        provider: ``s2`` or ``openalex`` — which vocabulary to validate against.

    Returns:
        The surviving field values, or None when none survive.
    """
    raw = (request.args.get("fields") or "").strip()
    if not raw:
        return None
    fields = search_service.valid_fields(provider, [part.strip() for part in raw.split(",")])
    return fields or None


@bp.get("/api/search")
def api_search() -> ResponseReturnValue:
    """Direct search: the paper scout, run on its own to find a seed paper.

    This is the same worker the researcher sends out (``workers/search/papers``)
    with the orchestration layer skipped — one Haiku agent that writes its own
    queries, looks at what came back, and searches again, rather than the older
    one-shot expand-then-search. Skipping the researcher is the point: a reader
    who knows what paper they want should not pay for an agent that writes
    prose about it.

    **The filters bind.** ``year_from`` / ``year_to`` / ``fields`` are handed to
    the scout as deps, not as prompt text, so every lookup it makes is already
    restricted to them and no wording it chooses can widen them (see
    ``ScoutDeps``). It may narrow further inside that window.

    Query args:
        q: Keywords, a title, an author, or a description of what's wanted.
            Blank returns an empty result rather than an error. (A pasted
            arXiv id/URL never reaches here — the frontend routes it straight
            to the graph, which is exact and needs no model.)
        provider: ``s2`` or ``openalex`` — which backend to search (matches the
            graph provider; defaults to ``config.providers.default_provider``).
        limit: Maximum papers per lookup (default 12, clamped to 1–50).
        year_from: Earliest publication year (inclusive; optional).
        year_to: Latest publication year (inclusive; optional).
        fields: Comma-separated field-of-study values in the provider's own
            vocabulary (optional; a paper matches when it carries any of them).

    **Streamed, not a plain response.** A scout run is several seconds, and a
    blocking GET meant the transcript sat blank for all of them — the reader
    couldn't tell a slow search from a dead one. It streams the same way the
    researcher does: a ``trace`` frame per lookup as the scout issues it, so
    the chips appear while the work happens.

    **The nickname resolve runs here too.** The `@`-mention dropdown learned
    (``api_mentions``) that ``dqn`` reaches *Playing Atari with Deep
    Reinforcement Learning* only through world knowledge — no text search
    gets there — and the scout, a text-searching agent, has exactly the same
    blind spot: asked for ``dqn`` it came back leading with a 2020 paper
    *titled* "Deep Q-Networks" and called it canonical. So the same
    day-cached resolve (``naming.paper_by_name``) runs **alongside** the scout
    in its own thread, costing no wall-clock, and the confirmed paper is
    prepended to the scout's list under the same gate the dropdown uses: only
    when no found title already *is* the query. Sending a bare ``@dqn`` from
    the dropdown thus lands on the same paper the dropdown would have offered
    — and usually from the cache the dropdown's own lookup just filled.

    Returns:
        An SSE stream: one optional ``cached`` frame up front (papers already
        in the local snapshot cache — an instant provisional list, superseded
        by the result; omitted when a field filter is active, which the cache
        cannot honor), ``trace`` frames (``{action, ok, query}`` — ``pending``
        as each lookup starts, then again with ``found``), then one ``result``
        frame carrying
        ``{q, count, papers, summary, queries}`` — ``papers`` are node dicts
        (the same shape as graph nodes) and ``summary`` is the scout's own
        account including what it *couldn't* find — then ``done``. Saves
        nothing. A provider outage is NOT an ``error`` frame: the scout
        degrades internally and reports it in the summary, so only a genuine
        break ends the stream with ``error``.
    """
    query = (request.args.get("q") or "").strip()
    provider = resolve_provider(request.args.get("provider"))
    try:
        limit = max(1, min(int(request.args.get("limit", "12")), 50))
    except ValueError:
        limit = 12
    # Every request arg is read HERE, outside the generator: an SSE body runs
    # during response iteration, after the request context is gone.
    year_from, year_to = _opt_year("year_from"), _opt_year("year_to")
    fields = _opt_fields(provider)

    def frames() -> Iterator[str]:
        """Yield the search's SSE frames: lookups live, then the result.

        Yields:
            ``trace`` frames as the scout issues each lookup, one ``result``
            frame, then ``done`` (or ``error`` if the run itself broke).
        """
        if not query:
            yield sse("result", {"q": query, "count": 0, "papers": [], "summary": "", "queries": []})
            yield sse("done", {})
            return
        # The scout runs on the shared agent loop while this generator drains
        # its lookups from the side — hence a thread-safe queue and a
        # non-blocking submit rather than `streams.run`.
        # (label, papers) — papers is None for the issued/pending announcement
        # and the lookup's new papers when it lands.
        lookups: Queue[tuple[str, list[dict] | None]] = Queue()
        # Started before the scout so it overlaps all of the scout's run: the
        # resolve is one model call and one provider lookup, the scout is
        # several of each, so this finishes first in practice and costs the
        # reader nothing. Collected below, once the scout's chips are done.
        resolving = _RESOLVERS.submit(search_service.paper_by_name, query, provider)
        future = streams.submit(
            papers.scout(
                query + _PICKER_BRIEF,
                provider,
                # Deliberately empty: the scout dedupes against its caller's
                # world, which is right for the researcher and wrong here. You
                # are picking a paper to explore, and hiding one because it
                # already happens to be on the canvas is exactly backwards.
                known_ids=set(),
                year_from=year_from,
                year_to=year_to,
                fields=fields,
                limit=limit,
                on_lookup=lambda label, papers: lookups.put((label, papers)),
            )
        )
        # The cache answers in milliseconds, so it lands as a provisional list
        # while the scout is still on its first provider call — the instant
        # tier the old racing local search used to give, rebuilt on the stream
        # instead of on a second endpoint. Skipped when a field filter is set,
        # for the same reason the scout skips it: snapshots carry no fields of
        # study, and an instant list that quietly ignored the filter would
        # break the promise the filter makes.
        if not fields:
            try:
                instant = search_service.display_hits(
                    search_service.cached_nodes(query, limit, year_from, year_to, provider)
                )
            except Exception:
                log.exception("cache pre-pass failed for %r", query)
                instant = []
            if instant:
                yield sse("cached", {"papers": instant})

        try:
            while True:
                try:
                    # A short poll rather than a blocking get: the run can
                    # finish without another lookup ever arriving, and nothing
                    # pushes a sentinel from the agent side.
                    yield from _lookup_frames(*lookups.get(timeout=0.1))
                except Empty:
                    if future.done():
                        break
            # Anything queued between the last drain and the run finishing.
            while not lookups.empty():
                yield from _lookup_frames(*lookups.get_nowait())
            result = future.result()
        except Exception as exc:
            # Only a genuine break reaches here — the scout swallows provider
            # failures and reports them in its summary.
            log.exception("direct search failed for %r", query)
            yield sse("error", {"message": f"Search failed: {exc}"})
            yield sse("done", {})
            return
        found = list(result.found)
        try:
            named = resolving.result()
        except Exception:
            # `paper_by_name` already swallows its own failures; this guards
            # the pool itself. A miss here is a miss, never a broken search.
            log.warning("direct search: name resolve failed for %r", query, exc_info=True)
            named = None
        # Prepended, not re-ranked in, and only when nothing the scout found
        # is already titled what was typed — the dropdown's rule exactly (see
        # `naming.has_exact_title_match` for why "contains" would be wrong).
        if named and not search_service.has_exact_title_match(found, query):
            found = search_service.merge_mentions([named], found, len(found) + 1)
            yield from _lookup_frames(_RESOLVE_LABEL.format(query=query), [named])
        yield sse(
            "result",
            {
                "q": query,
                "count": len(found),
                "papers": found,
                "summary": result.summary,
                "queries": result.queries,
            },
        )
        yield sse("done", {})

    return sse_response(frames())


#: Shortest `@`-mention query worth a lookup. One or two characters match
#: almost everything, so the list would be noise and the live search would be
#: spent on it.
_MENTION_MIN_CHARS = 3

#: How many suggestions a mention dropdown shows.
_MENTION_LIMIT = 8

#: Each provider in reader-facing words, for the mention stream's step labels.
#: Named here rather than reused from the frontend's `PROVIDER_LABEL` because a
#: step label is prose the server writes; the two happening to agree is a
#: coincidence worth keeping, not a coupling worth building.
_PROVIDER_NAMES: dict[str, str] = {"s2": "Semantic Scholar", "openalex": "OpenAlex"}


@bp.get("/api/mentions")
def api_mentions() -> ResponseReturnValue:
    """`@`-mention suggestions: papers matching a partial title, for the composer.

    A **plain, cheap lookup**, not an agent — the deliberate opposite of
    ``/api/search`` next door. It runs on every few keystrokes, so it must not
    write prose or pick its own queries.

    **Two sources, and ``source`` decides whether to wait for the slow one.**

    1. :func:`search_service.local_search` — the reader's cached graph
       snapshots. Free, instant, offline, and usually holds the paper they are
       reaching for, because they have seen it.
    2. ``traversal.search`` — a real provider search, **day-cached** with a
       normalized query key, which is what makes typing into this affordable:
       the same prefix typed twice is one request. It is also the only reason a
       paper the reader has never opened is mentionable at all.

    ``source=local`` returns only the first, as a **plain JSON response**, and
    that is the point of splitting them: the composer fires it with no debounce
    at all and paints suggestions while the reader is still typing. Serving
    both from one blocking call — as this did when it shipped — meant the free
    half bought nothing, because the response still waited on the provider.

    The **full pass streams** (see :func:`_mention_stream`), because it has
    three phases of visibly different cost and the reader deserves to know
    which one they are waiting on.

    Query args:
        q: The partial title typed after ``@``. Shorter than
            ``_MENTION_MIN_CHARS`` returns no candidates.
        provider: ``s2`` or ``openalex`` (defaults to the configured provider).
        source: ``local`` for the cache-only answer (no provider call, no
            wait, plain JSON); anything else, including absent, for the
            streamed full list.

    Returns:
        For ``source=local``, ``{"papers": [...], "partial": true}`` — rows
        carrying what a suggestion shows (title, authors, venue, year) plus the
        ids the composer needs. ``partial`` tells the composer this list is
        provisional, so a cache miss isn't read as "no such paper". Otherwise
        an SSE stream of ``step`` frames and one ``result`` frame.
    """
    query = (request.args.get("q") or "").strip()
    provider: Provider = resolve_provider(request.args.get("provider"))
    local_only = request.args.get("source") == "local"

    if local_only:
        if len(query) < _MENTION_MIN_CHARS:
            return jsonify({"papers": [], "partial": False})
        # Cache only: whatever is on hand, in local_search's own ranking, with
        # no provider call to wait on.
        local = search_service.local_search(query, limit=_MENTION_LIMIT, provider=provider)
        trimmed = search_service.mention_hits(local[:_MENTION_LIMIT])
        return jsonify({"papers": trimmed, "partial": True})

    return sse_response(_mention_stream(query, provider))


def _mention_stream(query: str, provider: Provider) -> Iterator[str]:
    """The full `@`-mention pass, as the frames it produces.

    Streamed rather than returned because its three phases cost visibly
    different amounts and the reader is watching a dropdown while they run: the
    cache scan is instant, the provider search is a network round trip, and the
    nickname resolve is a model call plus a verification. A single blocking
    response could only say "Searching…" for all three, which is the same
    complaint that got the trace chips added to ``/api/search``.

    Each ``step`` frame carries the label in reader-facing words, and each one
    **supersedes the last** — a phase history would be noise for a lookup that
    finishes in a second or two, and the dropdown renders one live line.

    Args:
        query: The partial title typed after ``@``.
        provider: The active backend.

    Yields:
        ``step`` frames as each phase starts, then one ``result`` frame
        carrying ``{papers}``. Errors are not a frame type here: every phase
        degrades to fewer papers rather than failing, so the stream always ends
        with a result.
    """
    if len(query) < _MENTION_MIN_CHARS:
        yield sse("result", {"papers": []})
        return

    yield sse("step", {"label": "Looking in your library"})
    local = search_service.local_search(query, limit=_MENTION_LIMIT, provider=provider)

    yield sse("step", {"label": f"Searching {_PROVIDER_NAMES[provider]}"})
    try:
        live = [hit["node"] for hit in traversal.search(query, _MENTION_LIMIT, provider=provider)]
    except Exception:
        log.warning("mention lookup: live search failed for %r", query, exc_info=True)
        live = []

    # Cached hits are passed first so a relevance tie resolves to the paper
    # already on hand, then the whole set is ranked on how well it answers
    # what was typed.
    merged = search_service.merge_mentions(local, live, _MENTION_LIMIT)
    ranked = search_service.rank_mentions(merged, query)

    # The only place a model touches this path: a nickname whose paper shares
    # no word with it. Skipped when a candidate's title already IS what was
    # typed — the one case world knowledge cannot improve on. Deliberately not
    # gated on a *contains* test: typing "dqn" returns a page of DQN-titled
    # papers while the paper actually called DQN is absent, so "text matching
    # found something" is not the same as "found the right thing"
    # (see `naming.has_exact_title_match`).
    if not search_service.has_exact_title_match(ranked, query):
        # Announced before it runs, not after: this is the slowest phase, and
        # a step that appears on completion reports what already happened.
        yield sse("step", {"label": f"Working out which paper “{query}” is"})
        named = search_service.paper_by_name(query, provider)
        if named:
            # Prepended, not re-ranked in: this is an identity match on what
            # the reader typed, which outranks any word overlap.
            ranked = search_service.merge_mentions([named], ranked, _MENTION_LIMIT)

    yield sse("result", {"papers": search_service.mention_hits(ranked)})


@bp.get("/api/taxonomy/<provider>")
def api_taxonomy(provider: str) -> ResponseReturnValue:
    """A search provider's field vocabulary, for the seed-search filter picker.

    Both graph providers return the **same** shape — ``{"fields": [{id, name}]}``
    — so the frontend picker is provider-agnostic: it shows ``name`` and sends
    ``id`` as the filter value. For S2 the id *is* the field name (S2 filters on
    the name itself); for OpenAlex the id is the numeric field id
    (``topics.field.id``) and the name its label.

    Args:
        provider: ``s2`` (the ~20 fields of study) or ``openalex`` (the 26
            top-level fields).

    Returns:
        ``{"fields": [{"id": ..., "name": ...}]}``; ``{error}`` with HTTP 404
        for an unknown provider.
    """
    if provider == "s2":
        return jsonify(
            {"fields": [{"id": name, "name": name} for name in semantic_scholar.vocab.fields()]}
        )
    if provider == "openalex":
        return jsonify({"fields": openalex.vocab.fields()})
    return jsonify({"error": f"unknown taxonomy provider {provider!r}"}), 404
