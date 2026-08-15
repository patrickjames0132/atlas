"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
The paper scout: the worker that owns the academic-paper source.

It replaces the researcher's old one-shot ``search_papers`` tool rather than
sitting beside it — two paths to one source is the bug, not the feature. What
it adds is the judgment that tool could not have: **reformulation and recency
bounding.** A single query against a lexical, citation-weighted search answers
"what's new in quantum computing" with landmarks from a decade ago; the scout
sees that come back, sets a year floor, and asks again.

It never assigns an index and never writes prose for the reader. It returns
the raw provider nodes it found plus a short summary of the search itself,
and the researcher — which owns the numbered list — decides what those
papers become. See ``workers/README.md``.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from pydantic import BaseModel, ConfigDict
from pydantic_ai import Agent, RunContext, Tool

from ....integrations import openalex
from ....integrations import semantic_scholar as s2
from ....services.graph import Provider
from ... import factory, prompts, traversal
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
    #: Raw provider node dicts, in discovery order. Deliberately not typed
    #: nodes and deliberately un-numbered: turning these into numbered graph
    #: nodes is the researcher's job.
    found: list[dict] = field(default_factory=list)
    #: Every query actually issued, for the trace the reader sees.
    queries: list[str] = field(default_factory=list)


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
    deps.queries.append(query)

    try:
        hits = traversal.search(query, deps.limit, year_from, year_to, deps.provider)
    except _SEARCH_ERRORS as exc:
        log.warning("paper scout search failed for %r: %s", query, exc)
        return f'Couldn\'t search "{query}": {exc}'

    lines = []
    for hit in hits:
        node = hit["node"]
        if node["id"] in deps.known_ids:
            continue
        deps.known_ids.add(node["id"])
        deps.found.append(node)
        lines.append(f"({node.get('year') or 'n.d.'}) {node['title']}")
    if not lines:
        return f'"{query}" returned nothing new.'
    return f'"{query}" — {len(lines)} paper(s):\n' + "\n".join(lines)


# sequential=True for the same reason the researcher's tools use it: the deps
# this mutates (the budget, the found list) are shared across the run's calls.
agent: Agent[ScoutDeps, PaperFindings] = Agent(
    factory.build_model(AGENT_ID),
    deps_type=ScoutDeps,
    output_type=PaperFindings,
    instructions=[SYSTEM_PROMPT, *(prompts.skill(name) for name in SKILLS)],
    tools=[Tool(search, sequential=True)],
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


async def scout(need: str, provider: Provider, known_ids: set[str]) -> ScoutResult:
    """Find papers answering a stated need, reformulating until they fit.

    Args:
        need: What the caller is looking for, in its own words ("recent work
            on quantum error correction, last two years"). Not a query — the
            scout writes those.
        provider: The academic backend to search (``s2`` / ``openalex``).
        known_ids: Paper ids the caller already has; anything matching is
            dropped rather than reported as a find.

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
        limit=int(BUDGETS["search_limit"]),
    )
    try:
        result = await agent.run(need, deps=deps)
    except Exception as exc:
        log.warning("paper scout failed for %r: %s", need, exc, exc_info=True)
        return ScoutResult(found=deps.found, summary=f"Paper search failed: {exc}", queries=deps.queries)
    return ScoutResult(found=deps.found, summary=result.output.summary.strip(), queries=deps.queries)
