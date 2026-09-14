"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
The router: decide whether a typed message wants the lecturer or the
researcher, and with what framing.

Two stages, cheapest first. A message that *names* a lecture
(``OBVIOUS_LECTURE``) is routed on the spot, with no model involved; anything
else goes to a one-shot classifier. Every failure — no key, network down, rate
limit, unparseable output — lands on the researcher, because that is the
cheaper mistake: a misrouted question wastes a minute of narration, a
misrouted lecture wastes one short answer.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

import logging
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict
from pydantic_ai import Agent

from ... import factory
from ..lecturer.config import Framing
from .config import AGENT_ID, OBVIOUS_LECTURE, SYSTEM_PROMPT

log = logging.getLogger(__name__)

#: Which assistant a message goes to.
Target = Literal["lecture", "answer"]


class MessageRoute(BaseModel):
    """Where one message goes, and how to tell it if it is a lecture.

    There is no ``confident`` field, unlike its sibling ``PaperName``: a
    classifier picking between two agents expresses its own doubt by picking
    the safe one. ``target='answer'`` already *is* "not sure this is a
    lecture", so a third value would only give the caller two ways to spell
    the same decision.
    """

    model_config = ConfigDict(extra="forbid")

    target: Target
    framing: Framing


#: The fallback, and the shape of every failure: answer the question.
ANSWER = MessageRoute(target="answer", framing="summary")

_HISTORY_WORDS = re.compile(
    r"\b(histor|story|stories|timeline|chronolog|evolv|evolution|"
    r"development|origins?|how\s+we\s+got|how\s+it\s+(?:began|started)|"
    r"over\s+time|came\s+about)", re.IGNORECASE
)
"""Framing for a message the fast path already claimed. It has said the word
"lecture", so the only question left is which of the two framings — and that
one *is* keyword-shaped, unlike the routing decision above it. No match means
summary, which is the button's default for the same reason: a chronological
arc is a strong claim to make about a set the reader assembled by hand."""

# No model at construction: passed per run by `factory.model_for`, so a blank
# config can't stop the app booting and a settings edit needs no restart.
agent: Agent[None, MessageRoute] = Agent(
    output_type=MessageRoute,
    instructions=[SYSTEM_PROMPT],
)

_MAX_CHARS = 600
"""How much of the message the router reads. Routing is decided by how a
message opens and what it asks for; a long message's tail is detail about a
subject, and billing for it cannot change a two-way pick."""


def obvious_route(message: str) -> MessageRoute | None:
    """Route a message that names a lecture outright, without a model call.

    Args:
        message: The reader's message, as typed.

    Returns:
        The route when the message plainly asks for a lecture, else None —
        which means "no opinion, ask the model", not "this is a question".
    """
    if not OBVIOUS_LECTURE.search(message or ""):
        return None
    framing: Framing = "history" if _HISTORY_WORDS.search(message) else "summary"
    return MessageRoute(target="lecture", framing=framing)


def route(message: str) -> MessageRoute:
    """Decide which assistant answers a typed message.

    Args:
        message: The reader's message, as typed. Blank routes to the
            researcher, which is what an empty question deserves.

    Returns:
        The route. Never raises and never returns None: an unroutable message
        is an answered one, so the caller has exactly one code path to write.
    """
    message = (message or "").strip()
    if not message:
        return ANSWER
    obvious = obvious_route(message)
    if obvious is not None:
        return obvious
    try:
        result = agent.run_sync(message[:_MAX_CHARS], model=factory.model_for(AGENT_ID))
    except Exception:
        log.warning("message routing failed, answering instead", exc_info=True)
        return ANSWER
    return result.output
