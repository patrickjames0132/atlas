"""The query analyst: a one-shot micro-agent that analyzes seed-search queries.

Semantic Scholar's search is lexical, so "DQN" misses the seminal papers that
never spell the acronym out in their title or abstract. The analyst attacks
that gap from both ends: it **expands** the query ("DQN" -> "DQN deep
Q-network deep Q-learning") for the lexical search, and — when it's confident
the query refers to specific papers — **names their exact titles** from
parametric knowledge (the model internalized the same acronym→paper
associations Google resolves via link text), which ``services.search``
verifies against S2's title-match endpoint. Called from ``services.search``'s
analysis seam, not through the orchestrator: it's infrastructure for search,
not a teacher workflow.

The one hard rule here is **degrade to a passthrough on any failure**: search
can never break, slow down excepted, because the LLM hiccuped. ``analyze``
catches everything and returns the query unchanged with no titles.
"""

from __future__ import annotations

import logging

from pydantic import BaseModel, ConfigDict
from pydantic_ai import Agent

from .. import factory, prompts
from .config import AGENT_ID, SKILLS, SYSTEM_PROMPT

log = logging.getLogger(__name__)


class Expansion(BaseModel):
    """The analyst's structured output.

    Typed fields instead of raw completion text, so prose the model might
    wrap around the query ("Here is the expanded...") can't leak into the
    search box.

    Exact titles of the specific papers the query most likely refers to —
    confident recalls only, empty otherwise. Suggestions, not truth: the
    search service verifies each against S2's title match before showing
    anything, so an invented title costs one lookup, never a wrong result.
    """

    model_config = ConfigDict(extra="forbid")

    expanded_query: str
    known_titles: list[str]


agent: Agent[None, Expansion] = Agent(
    factory.build_model(AGENT_ID),
    output_type=Expansion,
    instructions=[SYSTEM_PROMPT, *(prompts.skill(name) for name in SKILLS)],
)


def analyze(query: str) -> Expansion:
    """Analyze a search query: expand its vocabulary, recall known papers.

    Args:
        query: The raw seed-search query; surrounding whitespace is ignored.

    Returns:
        An ``Expansion`` — the expanded query (original terms kept,
        spelled-out forms appended) plus the exact titles of confidently
        recalled papers. The (stripped) query comes back unchanged with no
        titles when it's blank, when the model returns nothing usable, or
        when the run fails for **any** reason (no key, network down, rate
        limit): analysis is an enhancement, and search must work without it.
    """
    query = (query or "").strip()
    passthrough = Expansion(expanded_query=query, known_titles=[])
    if not query:
        return passthrough
    try:
        result = agent.run_sync(query)
    except Exception:
        log.warning("query analysis failed — searching unexpanded", exc_info=True)
        return passthrough
    expanded = result.output.expanded_query.strip()
    titles = [title.strip() for title in result.output.known_titles if title.strip()]
    return Expansion(expanded_query=expanded or query, known_titles=titles)
