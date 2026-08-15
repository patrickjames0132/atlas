"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
The web scout: the worker that owns the open web as a source.

**This is a grounded source, not recall.** The distinction matters enough to
write down, because a future reader will find v6.8.0 cutting the
"general-assistant" ambition and reasonably wonder whether this reopens it. It
does not. What was cut there was the model answering from its own weights,
with a soft prompt rule behind it and no way to measure the result. A web page
is as real, as citable and as retrievable as a paper or a page of the reader's
own book — it *extends* the grounding boundary rather than abandoning it, and
every claim still comes back with somewhere to check it.

Both membership criteria are met unambiguously (see ``workers/README.md``):
it needs judgment — phrasing the query, deciding when it has enough — and it
needs context isolation, because raw pages are long and low-signal and would
crowd out the researcher's own context.

The search itself is Anthropic's native ``WebSearchTool``, so the retrieval
runs provider-side and ``max_uses`` enforces the budget for us.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

import logging

from pydantic import BaseModel, ConfigDict
from pydantic_ai import Agent
from pydantic_ai.capabilities import WebSearch

from .... import factory, prompts
from .config import AGENT_ID, BUDGETS, SKILLS, SYSTEM_PROMPT

log = logging.getLogger(__name__)


class WebSource(BaseModel):
    """One page the scout actually retrieved, and what it contributes.

    ``url`` is the whole point: it is what makes a web claim checkable, and
    the researcher cites it inline so the reader can follow it. A source
    without one is dropped rather than shown — an uncheckable claim dressed
    as a citation is worse than no citation.
    """

    model_config = ConfigDict(extra="forbid")

    title: str
    url: str
    #: One line on what THIS page adds — not a summary of the topic.
    note: str


class WebFindings(BaseModel):
    """The scout's structured result: what the web established, and where."""

    model_config = ConfigDict(extra="forbid")

    #: Two or three sentences, dates stated plainly, gaps named.
    summary: str
    sources: list[WebSource]


agent: Agent[None, WebFindings] = Agent(
    factory.build_model(AGENT_ID),
    output_type=WebFindings,
    instructions=[SYSTEM_PROMPT, *(prompts.skill(name) for name in SKILLS)],
    # `capabilities=`, not `tools=`: the search runs provider-side and never
    # reaches this process, so PydanticAI attaches it as a capability of the
    # model rather than as a function it can call. It must be the
    # `capabilities.WebSearch` wrapper and NOT a bare
    # `native_tools.WebSearchTool` — a bare one is accepted by the
    # constructor and then silently dropped, leaving an agent that is
    # prompted to search the web and has no way to (caught by mypy, then
    # confirmed against the resolved native-tool list).
    capabilities=[WebSearch(max_uses=int(BUDGETS["max_uses"]))],
)


async def scout(need: str) -> WebFindings:
    """Search the web for a stated need and report what it established.

    Args:
        need: What the caller is looking for, in its own words. Not a query —
            the scout writes those.

    Returns:
        A ``WebFindings``. Sources missing a URL are dropped. On any failure
        it comes back empty with the reason as its summary: a broken web
        search must cost the answer its web grounding, never the answer.
    """
    try:
        result = await agent.run(need)
    except Exception as exc:
        log.warning("web scout failed for %r: %s", need, exc, exc_info=True)
        return WebFindings(summary=f"Web search failed: {exc}", sources=[])
    findings = result.output
    return WebFindings(
        summary=findings.summary.strip(),
        sources=[source for source in findings.sources if source.url.strip()],
    )
