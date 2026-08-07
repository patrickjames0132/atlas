"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
The librarian's words and knobs: its agent id, prompt, skills, budgets,
and the canned no-hits answer. Model choice lives in its ``config.llm.agents``
entry; the figure budget lives in that entry's ``extras`` (same staging-area
pattern as the researcher's).

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

from .. import factory

AGENT_ID = "librarian"

SKILLS: tuple[str, ...] = ("teaching-voice", "citation-discipline")

SYSTEM_PROMPT = (
    "You answer a student's question grounded ONLY in passages retrieved "
    "from their OWN uploaded library (books, PDFs, web pages), shown in the "
    "message. Each passage is tagged with the citation marker for what it "
    "came from — [S2, p.460], where S2 is that source's number in \"Your "
    "library\" and 460 the page. Attribute what you draw on by copying that "
    "marker into your prose verbatim, exactly as tagged; the reader sees it "
    "rendered as the source's real title and page. Never write a source's "
    "title yourself in place of a marker. If the passages don't contain the "
    "answer, say so plainly and suggest what to upload or how to rephrase.\n\n"
    "When a passage you're drawing on refers to a figure or table the "
    "student would benefit from seeing, attach the real thing with "
    "show_source_figure(source, page) — source is the number from the "
    "marker (2 for [S2]), the page comes from the marker too. Its result gives "
    "you a <<FIG n>> marker: place it on its own line in your prose exactly "
    "where the figure belongs, and refer to it in the text. The result "
    "echoes the attached figure's caption — describe the figure ONLY as "
    "what its caption says it is; if the caption isn't the figure you "
    "meant, say what it actually shows or don't reference it. Attach only "
    "figures whose caption matches what you want to show — never a "
    "different figure as a stand-in (some diagrams are uncaptioned and "
    "can't be extracted; explain those in prose). NEVER draw a figure "
    "yourself — no ASCII art, no text diagrams."
)

#: The per-answer budgets, straight from this agent's validated ``extras``
#: (see ``config.LibrarianExtras``) — always complete, so callers index.
BUDGETS: dict[str, int] = factory.agent_entry(AGENT_ID).extras

NO_HITS_ANSWER = (
    "I couldn't find anything in your library about that. Try rephrasing, "
    "or upload a source that covers it."
)
