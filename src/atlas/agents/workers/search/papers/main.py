"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
The paper scout: the worker that owns the academic-paper source.

It replaces the researcher's old one-shot ``search_papers`` tool rather than
sitting beside it — two paths to one source is the bug, not the feature. What
it adds is the judgment that tool could not have: **reformulation and recency
bounding.** A single query against a lexical, citation-weighted search answers
"what's new in quantum computing" with landmarks from a decade ago; the scout
sees that come back, sets a year floor, and asks again.

Since v7.4.0 it has **two channels rather than one**, which is the same
judgment applied to the other failure mode. ``search`` matches words;
``more_like`` matches meaning, hopping from a paper the scout has already
found (SPECTER2 recommendations under S2, ``related_works`` under OpenAlex).
The second exists because the first one's weakness is written into this
module's own prompt — a paper matches only words that literally appear in its
title or abstract — and re-phrasing the query is a workaround for not having
the other channel. It cannot start a run: with nothing found there is nothing
to be *like*, so it is always a second move.

It never assigns an index and never writes prose for the reader. It returns
the raw provider nodes it found plus a short summary of the search itself,
and the researcher — which owns the numbered list — decides what those
papers become. See ``workers/README.md``.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field

from pydantic import BaseModel, ConfigDict
from pydantic_ai import Agent, RunContext, Tool

from .....integrations import openalex
from .....integrations import semantic_scholar as s2
from .....services.graph import Provider
from .....services.search import cached_nodes
from .... import factory, prompts, traversal
from .config import AGENT_ID, BUDGETS, SKILLS, SYSTEM_PROMPT

log = logging.getLogger(__name__)

# Either provider's client can fail a search; both come back to the model as
# steerable text, never raised — the researcher's rule, applied one tier down.
_SEARCH_ERRORS = (s2.S2Error, openalex.OpenAlexError)


@dataclass
class ScoutDeps:
    """One scouting run's state: what it may spend, and what it has found.

    ``known_ids`` arrives from the caller and is *its* world — every paper
    already on the graph or already discovered this turn. Deduping against it
    here means the scout's own view of "what I found" is only what is
    genuinely new, so its summary can't claim to have turned up a paper the
    reader is already looking at.
    """

    provider: Provider
    known_ids: set[str]
    searches_left: int
    limit: int
    #: The caller's filters, applied to EVERY search this run makes. They live
    #: here rather than in the prompt on purpose: a filter the model is merely
    #: *told about* is a filter it can forget, while one read out of the deps
    #: inside the tool is one no amount of non-determinism can route around.
    #: The model never sees these values and has no argument that overrides
    #: them — the same way ``provider`` and ``known_ids`` already bind it.
    #: All None/empty (the default) means a genuinely unrestricted search:
    #: the scout runs exactly as it did before filters existed.
    year_from: int | None = None
    year_to: int | None = None
    #: Field-of-study values in the ACTIVE provider's vocabulary (S2 names /
    #: OpenAlex numeric ids — see ``traversal.search``). Empty for no filter.
    fields: list[str] = field(default_factory=list)
    #: Raw provider node dicts, in discovery order. Deliberately not typed
    #: nodes and deliberately un-numbered: turning these into numbered graph
    #: nodes is the researcher's job.
    found: list[dict] = field(default_factory=list)
    #: Every lookup actually made, in the reader's words, for the trace they
    #: see. Not all of them are queries: a semantic hop has no query string, so
    #: it records what it did instead ("similar to: <title>"), named for the
    #: provider's own notion of the relation — see ``_HOP_LABEL``.
    queries: list[str] = field(default_factory=list)
    #: Called TWICE per lookup for a caller streaming progress: once with
    #: ``(label, None)`` the moment it is issued, and again with
    #: ``(label, new_nodes)`` when it lands.
    #:
    #: Announcing at issue is half the point — a chip that appears on
    #: completion reports what already happened, while one that appears on
    #: issue says what is happening now, and a scout run is several seconds of
    #: otherwise-blank screen. Handing back the **papers** rather than just a
    #: count is the other half: a scout finds them a batch at a time, so a
    #: caller can grow its list lookup by lookup instead of sitting empty
    #: until the whole run ends. (The count comes free — it's the length.)
    on_lookup: Callable[[str, list[dict] | None], None] | None = None


class PaperFindings(BaseModel):
    """The scout's structured result: what the search itself established.

    Only a summary, because everything else the caller needs — the papers —
    comes back through the deps. Asking the model to *also* list them would
    invite it to describe papers it never saw and to invent numbering, both
    of which the caller then has to disbelieve.
    """

    model_config = ConfigDict(extra="forbid")

    #: One or two sentences on what was found and what wasn't. A negative
    #: result is a real finding ("nothing indexed after 2021"), and the
    #: researcher needs it to answer honestly rather than silently.
    summary: str


#: What the semantic hop is called *in the reader's trace*, per provider —
#: because the two aren't the same thing and shouldn't claim to be. Under S2 it
#: is SPECTER2 embedding neighbours, which is what "similar" means there; under
#: OpenAlex it is ``related_works``, concept and citation overlap. Borrowing
#: each provider's own word keeps the chip honest about how strong the claim
#: behind it is. The tool the model calls stays one ``more_like`` — the model
#: chooses the move, the provider decides what the move means.
_HOP_LABEL: dict[Provider, str] = {"s2": "similar to", "openalex": "related to"}


def _announce(deps: ScoutDeps, label: str) -> None:
    """Record a lookup and tell any listener it just started.

    Args:
        deps: The run's state — ``queries`` grows here.
        label: The lookup in reader-facing words ("deep q-network",
            "title: Playing Atari", "similar to: <title>").
    """
    deps.queries.append(label)
    if deps.on_lookup:
        deps.on_lookup(label, None)


def _report(deps: ScoutDeps, label: str, since: int) -> None:
    """Tell any listener how a lookup turned out, and hand it the papers.

    Pairs with :func:`_announce` — the caller replaces the pending chip with
    this one rather than showing both, and appends the papers to whatever it
    is already showing.

    Args:
        deps: The run's state.
        label: The same label the lookup was announced under.
        since: How long ``deps.found`` was *before* this lookup ran; the
            papers it added are everything after that point. Passing the mark
            rather than the list keeps the one truth in ``found`` — the
            caller can't be handed papers the scout didn't actually keep.
    """
    if deps.on_lookup:
        deps.on_lookup(label, deps.found[since:])


def _floor(bound: int | None, other: int | None) -> int | None:
    """Combine two "earliest year" bounds into the narrower one.

    Args:
        bound: The caller's floor, or None for none.
        other: The scout's own floor for this call, or None for none.

    Returns:
        The later of the two (whichever is set) — so the scout can tighten a
        window but never widen out of the caller's.
    """
    return max((year for year in (bound, other) if year is not None), default=None)


def _ceiling(bound: int | None, other: int | None) -> int | None:
    """Combine two "latest year" bounds into the narrower one — :func:`_floor`'s twin.

    Args:
        bound: The caller's ceiling, or None for none.
        other: The scout's own ceiling for this call, or None for none.

    Returns:
        The earlier of the two (whichever is set).
    """
    return min((year for year in (bound, other) if year is not None), default=None)


def _cached_hits(deps: ScoutDeps, query: str, year_from: int | None, year_to: int | None) -> list[dict]:
    """Papers matching ``query`` in graph snapshots already on disk.

    Free (no provider call, no network) and, when the provider is rate-limiting
    us, the only thing that answers at all — which is why it runs *inside*
    ``search`` rather than as a tool of its own. A tool is the model's to skip;
    this isn't.

    **Skipped entirely when a field filter is active.** The snapshot cache
    stores no fields of study, so it cannot honor one, and returning hits that
    quietly ignore a filter the reader set would break the promise the filter
    makes. Losing the cache is the cheaper half of that trade.

    Args:
        deps: The run's state — its provider and field filter are read.
        query: The search text, matched against cached titles + authors.
        year_from: Earliest publication year already narrowed for this call.
        year_to: Latest publication year already narrowed for this call.

    Returns:
        Cached papers in the traversal ``[{"node": ...}]`` shape. Empty when a
        field filter is active, when nothing matches, or when the cache read
        fails — a cache miss must never be able to fail a search.
    """
    if deps.fields:
        return []
    try:
        nodes = cached_nodes(query, deps.limit, year_from, year_to, deps.provider)
    except Exception as exc:  # a cache read must not be able to break a search
        log.warning("paper scout cache lookup failed for %r: %s", query, exc)
        return []
    # `has_graph` is the route's business (it badges a paper that opens with
    # no provider call); a scouted paper is just a paper.
    return [
        {"node": {key: value for key, value in node.items() if key != "has_graph"}}
        for node in nodes
    ]


def _keep(deps: ScoutDeps, hits: list[dict]) -> list[str]:
    """Take the genuinely-new papers out of a hop or search, and list them back.

    **On the numbers.** These are the scout's own, and they never leave it: they
    are how the model says "more like *that* one" to ``more_like``, which needs
    a handle on a paper and can't be given ids (a model handed ids starts
    inventing them). They are emphatically NOT the ``[n]`` the reader sees —
    that numbering is the researcher's, assigned when it accepts these papers,
    and the two must never be confused. What keeps them apart is that a scout
    number indexes ``deps.found`` (only what THIS run turned up) while ``[n]``
    indexes the whole numbered list, and nothing carries a scout number across
    the boundary: ``ScoutResult`` hands back raw node dicts, and the prompt
    forbids naming a number in the summary.

    Args:
        deps: The run's state — its ``known_ids`` and ``found`` grow here.
        hits: Provider entries, ``[{"node": {...}}, ...]``.

    Returns:
        One display line per newly-kept paper, numbered by its position in
        ``found``. Empty when everything was a duplicate.
    """
    lines = []
    for hit in hits:
        node = hit["node"]
        if node["id"] in deps.known_ids:
            continue
        deps.known_ids.add(node["id"])
        deps.found.append(node)
        # len(found) is this paper's position, since it was just appended.
        lines.append(f"{len(deps.found)}. ({node.get('year') or 'n.d.'}) {node['title']}")
    return lines


def search(
    ctx: RunContext[ScoutDeps],
    query: str,
    year_from: int | None = None,
    year_to: int | None = None,
) -> str:
    """Search the paper database. Returns what matched, so you can judge it and
    search again with better words or a year floor if it missed.

    Args:
        ctx: The run context carrying the scout's deps (framework-injected).
        query: Free-text query — keywords or a topic, not an id.
        year_from: Earliest publication year (inclusive). Omit for no floor.
        year_to: Latest publication year (inclusive). Omit for no ceiling.

    Returns:
        The matching papers as title + year lines, or a budget/validity note.
    """
    deps = ctx.deps
    query = query.strip()
    if not query:
        return "Invalid search (empty query)."
    if deps.searches_left <= 0:
        return "Search budget spent — summarize what you have and stop."
    deps.searches_left -= 1
    _announce(deps, query)

    # The caller's window wins where the two disagree: the model may tighten
    # inside it (its prompt tells it to, for recency) but cannot widen out of
    # it. With no caller filter set, its own bounds pass through untouched —
    # an unfiltered run searches exactly as freely as it always did.
    year_from = _floor(deps.year_from, year_from)
    year_to = _ceiling(deps.year_to, year_to)

    kept_before = len(deps.found)
    cached = _cached_hits(deps, query, year_from, year_to)
    try:
        hits = traversal.search(query, deps.limit, year_from, year_to, deps.provider, deps.fields)
    except _SEARCH_ERRORS as exc:
        # Cache-only mode: the provider is down or rate-limiting, but papers we
        # have seen before still answer. Degrading to them beats reporting a
        # dead end the reader can see isn't one.
        log.warning("paper scout search failed for %r: %s", query, exc)
        if not cached:
            _report(deps, query, kept_before)
            return f'Couldn\'t search "{query}": {exc}'
        lines = _keep(deps, cached)
        _report(deps, query, kept_before)
        if not lines:
            return f'Couldn\'t search "{query}" ({exc}) and found nothing new already cached.'
        return (
            f'"{query}" — the paper database is unavailable ({exc}); '
            f"{len(lines)} paper(s) from previously loaded graphs:\n" + "\n".join(lines)
        )

    # Live hits lead; anything the cache knew that the search missed follows.
    lines = _keep(deps, hits + cached)
    _report(deps, query, kept_before)
    if not lines:
        return f'"{query}" returned nothing new.'
    return f'"{query}" — {len(lines)} paper(s):\n' + "\n".join(lines)


def match_title(ctx: RunContext[ScoutDeps], title: str) -> str:
    """Look up ONE paper by its exact title. Use it when you can name the paper
    you're after — an acronym or nickname you recognize ("DQN", "the ResNet
    paper") almost always has a specific paper behind it whose title never
    contains that word, which is precisely the paper a word search cannot find.
    Give the real title as you remember it. Costs the same as a search, so
    spend it on papers you're confident exist, not on guesses.

    Args:
        ctx: The run context carrying the scout's deps (framework-injected).
        title: The paper's title, as exactly as you can recall it.

    Returns:
        The matched paper as a numbered title + year line, or a note saying
        nothing matched (which means the title was wrong — move on and search).
    """
    deps = ctx.deps
    title = title.strip()
    if not title:
        return "Invalid title lookup (empty title)."
    # A title match resolves one named paper and can't express a field-of-study
    # restriction, so while one is set this move is off rather than a way
    # around it — the same rule the cache lookup follows, for the same reason.
    if deps.fields:
        return "Title lookup is unavailable while a field filter is set — use search instead."
    if deps.searches_left <= 0:
        return "Search budget spent — summarize what you have and stop."
    deps.searches_left -= 1
    kept_before = len(deps.found)
    _announce(deps, f"title: {title}")

    try:
        if deps.provider == "openalex":
            work = openalex.resolve_work(arxiv_id=None, title=title)
            node = openalex.node(work) if work else None
        else:
            node = s2.match_title(title)
    except _SEARCH_ERRORS as exc:
        log.warning("paper scout title match failed for %r: %s", title, exc)
        _report(deps, f"title: {title}", kept_before)
        return f'Couldn\'t look up "{title}": {exc}'

    if not node:
        _report(deps, f"title: {title}", kept_before)
        return f'No paper matches the title "{title}".'
    # The caller's year window binds here too. Today's seed search let a
    # recalled title outrank the filters on the reading that an exact
    # resolution is "the paper the query means" — but once the window is a
    # promise the reader made rather than a hint, a match outside it is a
    # broken promise, not a smart override.
    year = node.get("year")
    outside = (deps.year_from is not None and (year is None or year < deps.year_from)) or (
        deps.year_to is not None and (year is None or year > deps.year_to)
    )
    if outside:
        _report(deps, f"title: {title}", kept_before)
        return f'"{node["title"]}" ({year or "n.d."}) falls outside the requested years.'

    lines = _keep(deps, [{"node": node}])
    _report(deps, f"title: {title}", kept_before)
    if not lines:
        return f'"{node["title"]}" was already found above.'
    return "Matched:\n" + "\n".join(lines)


def more_like(ctx: RunContext[ScoutDeps], result: int) -> str:
    """Find papers semantically similar to one you have ALREADY found — the
    other way to search, and the one that doesn't care what words a paper uses.
    Reach for it when a result is clearly on-target and you suspect the
    vocabulary is hiding its neighbours from the query, or when the request is
    "papers like X" in the first place. It costs the same as a search.

    Args:
        ctx: The run context carrying the scout's deps (framework-injected).
        result: Which paper to match, by its number in the lists above.

    Returns:
        The similar papers as numbered title + year lines, or a
        budget/validity note.
    """
    deps = ctx.deps
    if not 1 <= result <= len(deps.found):
        return f"No result {result} — use the numbers from the lists above."
    if deps.searches_left <= 0:
        return "Search budget spent — summarize what you have and stop."
    deps.searches_left -= 1
    origin = deps.found[result - 1]
    label = _HOP_LABEL[deps.provider]
    # Recorded in reader-facing words, not as a query, because there isn't one:
    # this shares the researcher's search trace rather than getting one of its
    # own. Which paper found a paper is the agent's business, not the reader's
    # (Patrick's call, 2026-08-15) — but "what is it doing right now" is, and
    # a chip reading `more like "…"` answers that honestly.
    # No inner quotes: the reader's trace chip wraps this in curly quotes of
    # its own, and `“similar to "X"”` reads like a typo.
    hop_label = f"{_HOP_LABEL[deps.provider]}: {origin['title']}"
    kept_before = len(deps.found)
    _announce(deps, hop_label)

    try:
        hits = traversal.neighbors(origin["id"], "similar", deps.limit, deps.provider)
    except _SEARCH_ERRORS as exc:
        log.warning("paper scout similar-hop failed for %r: %s", origin["id"], exc)
        _report(deps, hop_label, kept_before)
        return f'Couldn\'t find papers {label} "{origin["title"]}": {exc}'

    lines = _keep(deps, hits)
    _report(deps, hop_label, kept_before)
    if not lines:
        return f'Nothing new {label} "{origin["title"]}".'
    return f'{label.capitalize()} "{origin["title"]}" — {len(lines)} paper(s):\n' + "\n".join(lines)


# sequential=True for the same reason the researcher's tools use it: the deps
# these mutate (the budget, the found list, and the numbering that indexes into
# it) are shared across the run's calls.
#
# No model at construction: it is passed per run by `factory.model_for`, so a
# blank config can't stop the app booting and a settings edit needs no restart.
agent: Agent[ScoutDeps, PaperFindings] = Agent(
    deps_type=ScoutDeps,
    output_type=PaperFindings,
    instructions=[SYSTEM_PROMPT, *(prompts.skill(name) for name in SKILLS)],
    tools=[
        Tool(search, sequential=True),
        Tool(match_title, sequential=True),
        Tool(more_like, sequential=True),
    ],
)


@dataclass
class ScoutResult:
    """What one scouting run hands back to its caller."""

    #: Raw provider node dicts, new to the caller's world, in discovery order.
    #: Un-numbered on purpose — see ``workers/README.md``.
    found: list[dict]
    #: The scout's own account of the search, including what it *didn't* find.
    summary: str
    #: Every query it issued, for the reader-facing trace.
    queries: list[str]


def _filter_briefing(deps: ScoutDeps) -> str:
    """State the active filters to the model, as fact rather than instruction.

    This is emphatically **not** how the filters are enforced — that happens in
    the tools, out of the model's reach. It exists so the scout's *summary*
    isn't wrong: a run whose year floor silently cut the results would
    otherwise report "nothing indexed after 2021" as a finding about the
    literature, when it was a finding about the reader's own filter. Telling it
    which instrument it's holding costs one sentence and buys an honest
    negative result.

    Args:
        deps: The run's state — its filters are read.

    Returns:
        A line describing the active filters, or "" when none are set.
    """
    active = []
    if deps.year_from is not None or deps.year_to is not None:
        active.append(f"published {deps.year_from or 'any'}–{deps.year_to or 'any'}")
    if deps.fields:
        active.append(f"in these fields: {', '.join(deps.fields)}")
    if not active:
        return ""
    return (
        "\n\n(The reader has restricted this search to papers "
        + " and ".join(active)
        + ". Every lookup you make is already limited to that — you don't need to "
        "ask for it, and you cannot search outside it. If results come back thin, "
        "say the restriction is why rather than reporting the field is empty.)"
    )


async def scout(
    need: str,
    provider: Provider,
    known_ids: set[str],
    *,
    year_from: int | None = None,
    year_to: int | None = None,
    fields: list[str] | None = None,
    limit: int | None = None,
    on_lookup: Callable[[str, list[dict] | None], None] | None = None,
) -> ScoutResult:
    """Find papers answering a stated need, reformulating until they fit.

    Args:
        need: What the caller is looking for, in its own words ("recent work
            on quantum error correction, last two years"). Not a query — the
            scout writes those.
        provider: The academic backend to search (``s2`` / ``openalex``).
        known_ids: Paper ids the caller already has; anything matching is
            dropped rather than reported as a find.
        year_from: Earliest publication year every lookup is restricted to, or
            None for no floor. Binding — see ``ScoutDeps``.
        year_to: Latest publication year every lookup is restricted to, or None.
        fields: Field-of-study values in ``provider``'s own vocabulary that
            every search is restricted to, or None for no restriction.
        limit: Hits per lookup. Defaults to the configured ``search_limit``;
            a caller showing the papers to a reader directly wants more than
            one feeding them to another agent does.
        on_lookup: Called ``(label, None)`` as each lookup is issued and
            ``(label, new_papers)`` when it lands, for a caller streaming
            progress. None (the default) simply records them.

    Returns:
        A ``ScoutResult``. On any failure it comes back empty with the reason
        as its summary — a scouting run that breaks must cost the answer its
        papers, never the answer itself.
    """
    deps = ScoutDeps(
        provider=provider,
        # Copied, not aliased: the scout dedupes into this as it goes, and the
        # caller's set must not gain ids for papers it has not yet accepted.
        known_ids=set(known_ids),
        searches_left=int(BUDGETS["searches"]),
        limit=limit if limit is not None else int(BUDGETS["search_limit"]),
        year_from=year_from,
        year_to=year_to,
        fields=list(fields or []),
        on_lookup=on_lookup,
    )
    try:
        result = await agent.run(
            need + _filter_briefing(deps), deps=deps, model=factory.model_for(AGENT_ID)
        )
    except Exception as exc:
        log.warning("paper scout failed for %r: %s", need, exc, exc_info=True)
        return ScoutResult(found=deps.found, summary=f"Paper search failed: {exc}", queries=deps.queries)
    return ScoutResult(found=deps.found, summary=result.output.summary.strip(), queries=deps.queries)
