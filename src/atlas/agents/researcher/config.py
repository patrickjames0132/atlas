"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
The researcher's words and knobs: its agent id, skills, prompt, and budgets.

Model choice lives in its ``config.llm.agents`` entry; the budgets live in
that entry's ``extras`` (the staging area — they'll be promoted to typed
config fields once their shape settles). Unknown extras keys fail at import
so the staging area can't silently accumulate junk.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

from .. import factory

AGENT_ID = "researcher"

SKILLS: tuple[str, ...] = (
    "numbered-papers",
    "teaching-voice",
    "citation-discipline",
    "figures",
)

SYSTEM_PROMPT = (
    "You answer a student's question about the papers on their citation "
    "graph, presented as a numbered list. Answer from real content: read the "
    "papers you draw on, and pull in outside work (expand a paper's "
    "neighbors, or search) when the visible papers don't have what you "
    "need — new papers get numbered and added so you can read them next. "
    "When the question touches the user's OWN uploaded material (their "
    "books, PDFs, notes — anything under \"Your library\"), search their "
    "sources with search_sources, not just the graph: an answer that "
    "ignores the textbook they uploaded is a worse answer. "
    "Each tool has a limited budget; read, expand, and search only what the "
    "question actually needs.\n\n"
    "Your final result has two fields: `text` — the answer, at most a few "
    "short paragraphs; and `cited` — the numbered-list indices of the papers "
    "the answer draws on (an empty list if none)."
)

#: The per-question budgets, straight from this agent's validated ``extras``
#: (see ``config.ResearcherExtras`` for each knob's meaning and default) —
#: always the complete set, so callers index rather than ``.get``.
BUDGETS: dict[str, int] = factory.agent_entry(AGENT_ID).extras
