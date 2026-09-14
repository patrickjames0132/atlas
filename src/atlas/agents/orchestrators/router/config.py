"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
The router's words: its system prompt, the phrasings it never has to see, and
the agent id it borrows.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

import re

from ..summarizer.config import AGENT_ID

__all__ = ["AGENT_ID", "OBVIOUS_LECTURE", "SYSTEM_PROMPT"]

# `AGENT_ID` is imported rather than declared: the router runs on the
# summarizer's configured model, the same way the exploration titler and the
# paper-name resolver do. All four are one-shot micro-agents emitting a few
# tokens of structured output, and the house pattern (stated twice in
# `summarizer/config.py`) is that those share the crew's cheapest entry
# instead of each adding a row to Agent Settings. Importing the constant keeps
# that a checkable fact rather than a duplicated string — change it there and
# the router follows.

OBVIOUS_LECTURE = re.compile(
    r"""^\s*(?:
          (?:can\s+you\s+|could\s+you\s+|please\s+|now\s+)*
          (?:
              lecture\s+(?:me|us)\b
            | give\s+(?:me|us)\s+(?:a|the|your)\s+lecture\b
            | lecture\s*:
          )
        )""",
    re.IGNORECASE | re.VERBOSE,
)
"""Messages that need no model to classify: the reader said the word.

Deliberately **narrow**. Every phrasing here names a lecture outright, so the
match cannot be wrong and the call is pure waste; the tempting additions are
all ambiguous and belong to the model. "Summarize this" is the clearest
example — it means the papers on screen about half the time and *your last
answer* the other half, and only the conversation says which. Same for "walk
me through attention", which is as likely a question about the mechanism as a
request to be taught the papers about it.

So this is a latency shortcut, not the routing rule. Being small is the point:
a fast path that guesses is worse than no fast path, because the model it
skips would have been right."""

SYSTEM_PROMPT = (
    "You route one message from a reader of a citation-graph explorer to one "
    "of two assistants, and you decide nothing else.\n\n"
    "The reader is looking at a graph of papers, some subset of which they "
    "have scoped (selected, or narrowed with filters). Their message goes to "
    "either:\n"
    "- the LECTURER, which delivers a multi-beat taught lecture over the "
    "papers they have scoped. This is for 'teach me this', 'lecture me on "
    "these', 'give me an overview of what I'm looking at', 'what's the story "
    "of this field' — a request to be TAUGHT a body of work.\n"
    "- the RESEARCHER, which answers a question, reading and searching papers "
    "as needed. This is for anything with an answer: 'what is X', 'how does Y "
    "work', 'which of these used Z', 'who wrote this', 'compare A and B', and "
    "every follow-up to something already said.\n\n"
    "Return two fields:\n"
    "- target: 'lecture' or 'answer'.\n"
    "- framing: for a lecture, 'history' when they asked for the story, the "
    "development, the timeline, or how the field got here; 'summary' when they "
    "asked what this work IS or what it covers. On 'answer', return 'summary' "
    "— it is unused, not a judgement.\n\n"
    "**Answer is the default, and the asymmetry is deliberate.** A question "
    "misrouted to the lecturer costs the reader a minute of narration that "
    "never addresses what they asked; a lecture request misrouted to the "
    "researcher costs them a short answer and a second try. So choose "
    "'lecture' only when being taught is plainly what was asked for — a "
    "question that merely spans several papers is still a question. If the "
    "message is short and bare ('attention?', 'these two'), it is a question. "
    "Route the words in front of you; never try to be helpful about what the "
    "reader might have wanted instead."
)
