"""The librarian's words and knobs: its agent id, prompt, skills, budgets,
and the canned no-hits answer. Model choice lives in its ``config.llm.agents``
entry; the figure budget lives in that entry's ``extras`` (same staging-area
pattern as the researcher's).
"""

from __future__ import annotations

from .. import factory

AGENT_ID = "librarian"

SKILLS: tuple[str, ...] = ("teaching-voice", "citation-discipline")

SYSTEM_PROMPT = (
    "You answer a student's question grounded ONLY in passages retrieved "
    "from their OWN uploaded library (books, PDFs, web pages), shown in the "
    "message. Each passage is tagged with its source and page, like "
    "[Deep Learning, p.243] — attribute what you draw on inline in your "
    "prose using that form. If the passages don't contain the answer, say "
    "so plainly and suggest what to upload or how to rephrase.\n\n"
    "When a passage you're drawing on refers to a figure or table the "
    "student would benefit from seeing, attach the real thing with "
    "show_source_figure(source_id, page) — the source ids are listed with "
    "the passages, the page comes from the passage's tag. Its result gives "
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

BUDGET_DEFAULTS: dict[str, int] = {
    "figures": 2,  # show_source_figure calls per answer
}

_extras = factory.agent_entry(AGENT_ID).extras
_unknown = set(_extras) - set(BUDGET_DEFAULTS)
if _unknown:
    raise ValueError(
        f"unknown librarian extras {sorted(_unknown)!r} in config.llm.agents — "
        f"known budget knobs: {sorted(BUDGET_DEFAULTS)}"
    )

BUDGETS: dict[str, int] = {
    **BUDGET_DEFAULTS,
    **{name: int(value) for name, value in _extras.items()},
}

NO_HITS_ANSWER = (
    "I couldn't find anything in your library about that. Try rephrasing, "
    "or upload a source that covers it."
)
