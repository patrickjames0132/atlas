"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
Two one-shot micro-agents that write a short piece of text on demand, and
share one agent id (and so one configured model — the crew's cheapest).

* **Paper TL;DRs** — one plain-language sentence from a paper's title +
  abstract, for papers whose provider ships none (every OpenAlex paper; the
  S2 papers S2 never summarized).
* **Exploration titles** — a short noun phrase naming a conversation, so an
  automatically-saved exploration arrives in the rail with a name a reader
  can find again instead of "Untitled exploration".

* ``main``   — both ``Agent``s, their ``Summary``/``ConversationTitle``
  output models, and the two None-on-failure entry points ``summarize`` and
  ``title_for_conversation``.
* ``config`` — the agent id, both system prompts, and the (empty) skill list.

Both entry points are re-exported here — callers use
``summarizer.summarize(...)`` / ``summarizer.title_for_conversation(...)``
without reaching into submodules.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

from .main import (
    ConversationTitle,
    Summary,
    agent,
    summarize,
    title_agent,
    title_for_conversation,
)

__all__ = [
    "ConversationTitle",
    "Summary",
    "agent",
    "summarize",
    "title_agent",
    "title_for_conversation",
]
