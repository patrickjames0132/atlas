"""The librarian's words and knobs: its agent id, prompt, skills, and the
canned no-hits answer. Model choice lives in its ``config.llm.agents`` entry."""

from __future__ import annotations

AGENT_ID = "librarian"

SKILLS: tuple[str, ...] = ("teaching-voice", "citation-discipline")

SYSTEM_PROMPT = (
    "You answer a student's question grounded ONLY in passages retrieved "
    "from their OWN uploaded library (books, PDFs, web pages), shown in the "
    "message. Each passage is tagged with its source and page, like "
    "[Deep Learning, p.243] — attribute what you draw on inline in your "
    "prose using that form. If the passages don't contain the answer, say "
    "so plainly and suggest what to upload or how to rephrase."
)

NO_HITS_ANSWER = (
    "I couldn't find anything in your library about that. Try rephrasing, "
    "or upload a source that covers it."
)
"""Streamed instead of engaging the model when retrieval finds nothing —
an answer, not an error."""
