"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
The summarizer: a one-shot micro-agent that writes a TL;DR from an abstract.

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

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

import logging

from pydantic import BaseModel, ConfigDict
from pydantic_ai import Agent

from ... import factory, prompts
from .config import AGENT_ID, SKILLS, SYSTEM_PROMPT, TITLE_SYSTEM_PROMPT

log = logging.getLogger(__name__)


class Summary(BaseModel):
    """The summarizer's structured output.

    A typed field instead of raw completion text, so prose the model might
    wrap around the summary ("Here is a TL;DR...") can't leak into the
    panel.
    """

    model_config = ConfigDict(extra="forbid")

    tldr: str


# No model at construction: it is passed per run by `factory.model_for`, so a
# blank config can't stop the app booting and a settings edit needs no restart.
agent: Agent[None, Summary] = Agent(
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
        result = agent.run_sync(prompt, model=factory.model_for(AGENT_ID))
    except Exception:
        log.warning("TL;DR generation failed", exc_info=True)
        return None
    tldr = result.output.tldr.strip()
    return tldr or None


class ConversationTitle(BaseModel):
    """The titler's structured output.

    A typed field for the same reason ``Summary`` has one: a name goes
    straight into a list row, so prose the model might wrap around it
    ("Here's a title:") must not be able to leak in.
    """

    model_config = ConfigDict(extra="forbid")

    title: str


# A second one-shot agent on the summarizer's id, so it runs on whatever
# model the summarizer is configured with (see `TITLE_SYSTEM_PROMPT`).
title_agent: Agent[None, ConversationTitle] = Agent(
    output_type=ConversationTitle,
    instructions=[TITLE_SYSTEM_PROMPT],
)

_TITLE_MAX_CHARS = 1200
"""How much of the conversation the titler reads. A name comes from what the
conversation opened with — later turns wander, and a long transcript would
bill for tokens that cannot improve a six-word phrase."""


def title_for_conversation(turns: list[str]) -> str | None:
    """Name an exploration after the conversation held in it.

    Runs **once per exploration**, when it first has enough content to be
    worth naming, and never again — the caller stores the result, and the
    reader can rename it in place afterwards. That is what keeps automatic
    saving from billing a model call on every keystroke.

    Args:
        turns: The conversation's opening turns, oldest first, already
            flattened to plain text by the caller. An empty list (or one
            holding only blanks) means there is nothing to name yet.

    Returns:
        The title, or None when there is nothing to name, the model returns
        nothing usable, or the run fails for **any** reason (no key, network
        down, rate limit). None is a normal outcome, not an error: the caller
        falls back to naming the exploration after its own first message,
        which costs nothing and is always available.
    """
    joined = "\n\n".join(turn.strip() for turn in turns if turn and turn.strip())
    if not joined:
        return None
    try:
        result = title_agent.run_sync(
            joined[:_TITLE_MAX_CHARS], model=factory.model_for(AGENT_ID)
        )
    except Exception:
        log.warning("exploration title generation failed", exc_info=True)
        return None
    title = result.output.title.strip().strip('"').rstrip(".")
    return title or None
