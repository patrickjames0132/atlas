"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
The router's words: its system prompts, the phrasings it never has to see, and
the agent id it borrows.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

import re

from ..summarizer.config import AGENT_ID

__all__ = ["AGENT_ID", "OBVIOUS_LECTURE", "RESOLVE_SYSTEM_PROMPT", "SYSTEM_PROMPT"]

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
        )
        (?P<tail>.*)$""",
    re.IGNORECASE | re.VERBOSE | re.DOTALL,
)
"""Messages that open by naming a lecture: the reader said the word.

The `tail` group — everything after the phrase — decides whether the match
counts, via ``DEICTIC_TAIL`` below. Naming a lecture settles the *target*,
but since v7.23.0 a message also picks the lecture's **scope**, and a tail
with content in it ("…on the references", "…on the Bekenstein paper") is
exactly the part a regex cannot read. So the fast path claims only the
messages whose tail says nothing about *which* papers.

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

DEICTIC_TAIL = re.compile(
    r"""^(?:\s+(?:(?:on|about|of|for|over|covering)\s+)?
          (?:the\s+)?
          (?:(?:history|story|evolution|timeline|development|origins?)\s+(?:of|behind)\s+(?:the\s+)?)?
          (?:
              (?:all\s+(?:of\s+)?)?(?:these|this|those|them|it|everything)
            | (?:these|those|the\s+(?:selected|visible|scoped|filtered))\s+(?:papers?|ones?|nodes?|works?)
            | the\s+(?:graph|screen|canvas|view|selection|papers|nodes)
            | what(?:'s|\s+is)\s+(?:on\s+(?:the\s+|my\s+)?screen|selected|visible)
            | what\s+i\s+(?:have|see|selected|picked)(?:\s+on\s+(?:the\s+|my\s+)?screen)?
            | how\s+(?:we\s+got\s+here|this\s+(?:field|area)\s+(?:evolved|developed|came\s+about|got\s+here))
          )
          (?:\s+(?:over\s+time|so\s+far))?
        )?
        \s*[.!?]*\s*$""",
    re.IGNORECASE | re.VERBOSE,
)
"""What may follow a named lecture for the fast path to keep it: nothing, or a
phrase that points at the screen — "these", "this", "the selected papers",
"what I have on screen", "how we got here". Every alternative names *no*
particular paper, so the scope is certainly what is on screen and the routing
is certainly a lecture; there is nothing left for a model to decide.

A tail that says anything else — "the references", "this paper: BERT", "the
attention papers", "transformers" — is a scope, and the model reads it. That
includes tails a keyword pattern *could* read ("the references"), because a
pattern that gets "the references" right and "the papers that reference the
seed" wrong is the guessing fast path the module docstring above rules out."""

SYSTEM_PROMPT = (
    "You route one message from a reader of a citation-graph explorer to one "
    "of two assistants, and you decide nothing else.\n\n"
    "The reader is looking at a graph of papers built around one SEED paper: "
    "the seed's references (the papers it cites), its citations (the papers "
    "that cite it), and any they have expanded from there. Some subset is "
    "scoped (selected, or narrowed with filters). Their message goes to "
    "either:\n"
    "- the LECTURER, which delivers a multi-beat taught lecture over a set of "
    "papers. This is for 'teach me this', 'lecture me on these', 'give me an "
    "overview of what I'm looking at', 'what's the story of this field' — a "
    "request to be TAUGHT a body of work.\n"
    "- the RESEARCHER, which answers a question, reading and searching papers "
    "as needed. This is for anything with an answer: 'what is X', 'how does Y "
    "work', 'which of these used Z', 'who wrote this', 'compare A and B', and "
    "every follow-up to something already said.\n\n"
    "Return three fields:\n"
    "- target: 'lecture' or 'answer'.\n"
    "- framing: for a lecture, 'history' ONLY when they asked for the story, "
    "the development, the timeline, or how the field got here; 'summary' "
    "otherwise — when they asked what this work IS or what it covers, and "
    "whenever they did not say. Naming a relation ('the citations') or "
    "several papers is not asking for a history. On 'answer', return "
    "'summary' — it is unused, not a judgement.\n"
    "- scope: WHICH papers the message is about — for a lecture and a question "
    "alike, since both are answered over a set of papers — read only from what "
    "the message says:\n"
    "  * 'screen' when the message does not say — 'these', 'this', 'what I "
    "have here', a topic word, or nothing at all. The papers the reader has "
    "on screen are the default, and by far the common case.\n"
    "  * 'references' when they ask for the seed's references, the works it "
    "cites, its bibliography, the papers it builds on.\n"
    "  * 'citations' when they ask for the papers citing the seed, its "
    "citers, the work that built on it, what came after it.\n"
    "  * 'seed' when they ask for the seed paper alone — 'the seed', 'this "
    "paper', 'the main paper', 'the paper I opened'.\n"
    "  * 'named' when the message identifies one or more SPECIFIC papers — by "
    "title, by nickname, by author, by author and year: 'this paper: "
    "Attention is all you need', 'the Bekenstein paper', 'BERT and GPT-2', "
    "'Hawking 1975'. A field or topic is NOT a named paper: 'lecture me on "
    "transformers' is 'screen'.\n"
    "  A question reads the same way: 'what do the references say about "
    "entropy?' is 'references', 'who wrote the seed?' is 'seed', 'which of "
    "these used dropout?' is 'screen'. When in doubt, 'screen' — it keeps the "
    "context the reader already set up.\n"
    "- year_from and year_to: when the message limits a lecture to a period "
    "— 'between 2016 and 2017' (2016, 2017), 'the 2010s' (2010, 2019), 'since "
    "2020' (2020, null), 'before 2000' (null, 1999), 'the last five years' "
    "(count back from today's date, given after the message). A period "
    "combines with the scope: 'the references from the 2010s' is scope "
    "'references' with both years. Null when no period was given; a year "
    "mentioned as part of a paper's name ('Hawking 1975') is NOT a period. "
    "Read for a question exactly as for a lecture.\n\n"
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

RESOLVE_SYSTEM_PROMPT = (
    "A reader of a citation-graph explorer has asked for a lecture on one or "
    "more specific papers, naming them in their message. You are given that "
    "message and a numbered list of every paper on their graph — each as "
    "[n] title (first author, year). Return one field:\n"
    "- indices: the numbers of the listed papers the reader named, in the "
    "order they named them.\n\n"
    "Readers name papers loosely — a nickname ('the BERT paper'), a fragment "
    "of the title, an author ('the Bekenstein paper'), an author and year "
    "('Hawking 1975'), an acronym — so match on meaning, not on exact words. "
    "But be strict about WHICH papers: return only papers the message "
    "actually points at. If a name matches nothing on the list, leave it "
    "out; if nothing on the list is what they meant, return an empty list. "
    "A field or topic is not a paper: 'lecture me on transformers' names no "
    "paper even if the list holds the paper that introduced them, so return "
    "an empty list rather than the paper about the topic. Never pad the list "
    "with papers that merely seem related — the reader will get a lecture on "
    "exactly what you return, and a paper they did not ask for is worse than "
    "one you could not find."
)
"""The name resolver's prompt — the second, rarer call. It runs only after
the classifier has said the scope is 'named', so the graph's paper list
crosses the wire (and is billed) only for the messages that name a paper,
never on the every-message classify."""
