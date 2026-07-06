"""The query analyst: a one-shot micro-agent that expands seed-search queries.

Semantic Scholar's search is lexical, so "DQN" misses the seminal papers that
never spell the acronym out in their title or abstract. The analyst rewrites
the query ("DQN" -> "DQN deep Q-network deep Q-learning") before it hits S2 —
called from ``services.search``'s ``_expand_query`` seam, not through the
orchestrator: it's infrastructure for search, not a teacher workflow.

The one hard rule here is **degrade to a passthrough on any failure**: search
can never break, slow down excepted, because the LLM hiccuped. ``expand_query``
catches everything and returns the query unchanged.
"""

from __future__ import annotations

import logging

from pydantic import BaseModel, ConfigDict
from pydantic_ai import Agent

from .. import factory
from .config import AGENT_ID, SYSTEM_PROMPT

log = logging.getLogger(__name__)


class Expansion(BaseModel):
    """The analyst's structured output: the expanded query, nothing else.

    A typed field instead of raw completion text, so prose the model might
    wrap around the query ("Here is the expanded...") can't leak into the
    search box.
    """

    model_config = ConfigDict(extra="forbid")

    expanded_query: str


agent: Agent[None, Expansion] = Agent(
    factory.build_model(AGENT_ID),
    output_type=Expansion,
    # instructions=, never system_prompt=: PydanticAI drops a system_prompt
    # whenever message_history is passed — house rule so no agent can lose
    # its persona on follow-up turns.
    instructions=SYSTEM_PROMPT,
)


def expand_query(query: str) -> str:
    """Expand a search query's acronyms and jargon for lexical search.

    Args:
        query: The raw seed-search query; surrounding whitespace is ignored.

    Returns:
        The expanded query — original terms kept, spelled-out forms appended.
        The (stripped) query comes back unchanged when it's blank, when the
        model returns nothing usable, or when the run fails for **any**
        reason (no key, network down, rate limit): expansion is an
        enhancement, and search must work without it.
    """
    query = (query or "").strip()
    if not query:
        return query
    try:
        result = agent.run_sync(query)
    except Exception:
        log.warning("query expansion failed — searching unexpanded", exc_info=True)
        return query
    expanded = result.output.expanded_query.strip()
    return expanded or query
