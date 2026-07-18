"""The summarizer: a one-shot micro-agent that writes a TL;DR from an abstract.

Semantic Scholar ships its own model-written TLDRs; OpenAlex has no
equivalent, and even S2 lacks one for plenty of papers — so the detail
panel's TL;DR view generates one on demand. **On demand is the contract**:
the agent runs only when the user actually toggles a selected paper to
TL;DR (never during graph builds or panel hydration), and the route layer
caches the result per paper forever, so each paper bills at most once —
see ``routes/graph.py::api_paper_tldr``.

Like the query analyst, failure degrades instead of raising: ``summarize``
returns None on any error (no key, network down, rate limit), and the route
turns that into an honest HTTP error — the abstract is still right there.
"""

from __future__ import annotations

import logging

from pydantic import BaseModel, ConfigDict
from pydantic_ai import Agent

from .. import factory, prompts
from .config import AGENT_ID, SKILLS, SYSTEM_PROMPT

log = logging.getLogger(__name__)


class Summary(BaseModel):
    """The summarizer's structured output.

    A typed field instead of raw completion text, so prose the model might
    wrap around the summary ("Here is a TL;DR...") can't leak into the
    panel.
    """

    model_config = ConfigDict(extra="forbid")

    tldr: str


agent: Agent[None, Summary] = Agent(
    factory.build_model(AGENT_ID),
    output_type=Summary,
    instructions=[SYSTEM_PROMPT, *(prompts.skill(name) for name in SKILLS)],
)


def summarize(title: str, abstract: str) -> str | None:
    """Write a one-sentence TL;DR for a paper from its title and abstract.

    Args:
        title: The paper's title (may be blank — the abstract carries the
            content; the title just anchors it).
        abstract: The paper's abstract. Blank means there is nothing to
            summarize.

    Returns:
        The TL;DR sentence, or None when the abstract is blank, the model
        returns nothing usable, or the run fails for **any** reason (no key,
        network down, rate limit) — the caller surfaces that as an error
        while the abstract remains available.
    """
    abstract = (abstract or "").strip()
    if not abstract:
        return None
    prompt = f"Title: {(title or '').strip() or '(untitled)'}\n\nAbstract: {abstract}"
    try:
        result = agent.run_sync(prompt)
    except Exception:
        log.warning("TL;DR generation failed", exc_info=True)
        return None
    tldr = result.output.tldr.strip()
    return tldr or None
