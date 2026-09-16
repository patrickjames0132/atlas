"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
The router: decide whether a typed message wants the lecturer or the
researcher, with what framing, and — for a lecture — over which papers.

Two stages, cheapest first. A message that *names* a lecture and points at
nothing in particular (``OBVIOUS_LECTURE`` + ``DEICTIC_TAIL``) is routed on
the spot, with no model involved; anything else goes to a one-shot
classifier. Every failure — no key, network down, rate limit, unparseable
output — lands on the researcher, because that is the cheaper mistake: a
misrouted question wastes a minute of narration, a misrouted lecture wastes
one short answer.

A third, rarer call resolves the papers a message *named* against the graph
(``resolve_papers``). It is separate from ``route`` so the graph's paper list
is only sent, and only billed, for the messages that name one.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict
from pydantic_ai import Agent

from ... import factory
from ..lecturer.config import Framing
from .config import AGENT_ID, DEICTIC_TAIL, OBVIOUS_LECTURE, RESOLVE_SYSTEM_PROMPT, SYSTEM_PROMPT

log = logging.getLogger(__name__)

#: Which assistant a message goes to.
Target = Literal["lecture", "answer"]

#: Which papers the message is about — a lecture's subject or a question's
#: grounding alike, as far as the message says. ``screen`` is "the message
#: doesn't say": the reader's own scope (their selection, else what passes
#: their filters), which is what every turn was about before a message could
#: name a set of its own.
Scope = Literal["screen", "references", "citations", "seed", "named"]


class MessageRoute(BaseModel):
    """Where one message goes, how to tell it if it is a lecture, and on what.

    There is no ``confident`` field, unlike its sibling ``PaperName``: a
    classifier picking between two agents expresses its own doubt by picking
    the safe one. ``target='answer'`` already *is* "not sure this is a
    lecture", so a third value would only give the caller two ways to spell
    the same decision.

    ``scope`` says which papers, never *which ids*: the classifier reads the
    message alone, and ``named`` is a promise that a second call
    (``resolve_papers``) can turn the message into ids given the graph. Read
    for an ``answer`` exactly as for a ``lecture`` (since v7.24.0): the
    researcher grounds in the scope the same way the lecturer narrates it.

    ``year_from`` / ``year_to`` are a period the message limited the lecture
    to ("between 2016 and 2017", "the 2010s", "the last five years"), applied
    on top of whichever scope it named; both None when it named none. Years
    rather than a sixth scope kind because a period *combines* with the
    others — "the references from the 2010s" is a relation and a window.
    """

    model_config = ConfigDict(extra="forbid")

    target: Target
    framing: Framing
    scope: Scope = "screen"
    year_from: int | None = None
    year_to: int | None = None


#: The fallback, and the shape of every failure: answer the question.
ANSWER = MessageRoute(target="answer", framing="summary", scope="screen")

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
        The route when the message plainly asks for a lecture over what is
        on screen, else None — which means "no opinion, ask the model", not
        "this is a question". A message that names a lecture *and* says
        which papers ("…on the references") is left to the model too: the
        scope is the half a pattern cannot read.
    """
    match = OBVIOUS_LECTURE.match(message or "")
    if match is None or not DEICTIC_TAIL.match(match.group("tail")):
        return None
    framing: Framing = "history" if _HISTORY_WORDS.search(message) else "summary"
    return MessageRoute(target="lecture", framing=framing, scope="screen")


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
    # The date rides along so a relative period ("the last five years",
    # "this decade") can be turned into years; appended after the cut so a
    # long message cannot push it out.
    prompt = f"{message[:_MAX_CHARS]}\n\n(Today's date: {date.today().isoformat()})"
    try:
        result = agent.run_sync(prompt, model=factory.model_for(AGENT_ID))
    except Exception:
        log.warning("message routing failed, answering instead", exc_info=True)
        return ANSWER
    return result.output


class RoutePaper(BaseModel):
    """One graph paper as the resolver sees it: enough to be recognised by.

    A deliberately thin cut of ``Node`` — a title, a first author and a year
    are what a reader names a paper *by*, and the abstract a full node
    carries would multiply the prompt without adding a way to match. Extra
    fields are ignored rather than refused, so a frontend can send whatever
    node shape it has.
    """

    model_config = ConfigDict(extra="ignore")

    id: str
    title: str
    year: int | None = None
    authors: str | None = None


class PaperPicks(BaseModel):
    """The resolver's output: positions in the numbered list it was shown."""

    model_config = ConfigDict(extra="forbid")

    indices: list[int]


resolve_agent: Agent[None, PaperPicks] = Agent(
    output_type=PaperPicks,
    instructions=[RESOLVE_SYSTEM_PROMPT],
)

_MAX_PAPERS = 500
"""How many graph papers the resolver is shown. A graph pool is capped well
below this by the build budget; the bound is here so a pathological payload
cannot turn one routing call into a very long prompt."""


def _paper_line(number: int, paper: RoutePaper) -> str:
    """One paper's line in the resolver's list: ``[n] title (author, year)``.

    Args:
        number: The paper's 1-based position.
        paper: The paper.

    Returns:
        The formatted line.
    """
    first_author = (paper.authors or "").split(",")[0].strip() or "unknown"
    year = paper.year if paper.year is not None else "n.d."
    return f"[{number}] {paper.title} ({first_author}, {year})"


def resolve_papers(message: str, papers: Sequence[RoutePaper]) -> list[str]:
    """Find which of the graph's papers a message named.

    Args:
        message: The reader's message, as typed.
        papers: Every paper on the graph, in any order.

    Returns:
        The ids of the papers named, in the order the model listed them, with
        out-of-range and repeated picks dropped. Empty when nothing matched —
        and empty on every failure too, for the same reason ``route`` never
        raises: the caller has one thing to check, and "nothing matched" is
        already a case it has to handle.
    """
    message = (message or "").strip()
    shown = list(papers[:_MAX_PAPERS])
    if not message or not shown:
        return []
    prompt = (
        f"Message: {message[:_MAX_CHARS]}\n\nPapers on the graph:\n"
        + "\n".join(_paper_line(number, paper) for number, paper in enumerate(shown, start=1))
    )
    try:
        result = resolve_agent.run_sync(prompt, model=factory.model_for(AGENT_ID))
    except Exception:
        log.warning("named-paper resolution failed, matching nothing", exc_info=True)
        return []
    ids: list[str] = []
    for index in result.output.indices:
        if 1 <= index <= len(shown) and shown[index - 1].id not in ids:
            ids.append(shown[index - 1].id)
    return ids
