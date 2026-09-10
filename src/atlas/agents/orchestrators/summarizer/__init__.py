"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
Three one-shot micro-agents that write a short piece of text on demand, and
share one agent id (and so one configured model — the crew's cheapest).

* **Paper TL;DRs** — one plain-language sentence from a paper's title +
  abstract, for papers whose provider ships none (every OpenAlex paper; the
  S2 papers S2 never summarized).
* **Exploration titles** — a short noun phrase naming a conversation, so an
  automatically-saved exploration arrives in the rail with a name a reader
  can find again instead of "Untitled exploration".
* **Paper names** — an acronym or nickname ("DQN") turned into the real
  title, for the composer's `@` lookup. The one model call in an otherwise
  model-free path, because the mapping is world knowledge: no field of the
  DQN paper contains the string "DQN".

* ``main``   — the three ``Agent``s, their
  ``Summary``/``ConversationTitle``/``PaperName`` output models, and the
  three None-on-failure entry points.
* ``config`` — the agent id, the three system prompts, and the (empty) skill
  list.

All three entry points are re-exported here — callers use
``summarizer.summarize(...)`` and friends without reaching into submodules.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

from .main import (
    ConversationTitle,
    PaperName,
    Summary,
    agent,
    paper_name_agent,
    summarize,
    title_agent,
    title_for_conversation,
    title_for_paper_name,
)

__all__ = [
    "ConversationTitle",
    "PaperName",
    "Summary",
    "agent",
    "paper_name_agent",
    "summarize",
    "title_agent",
    "title_for_conversation",
    "title_for_paper_name",
]
