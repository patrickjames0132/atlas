"""The summarizer's words and knobs: its agent id, system prompt, and skills.
Model choice and tunables live in its ``config.llm.agents`` entry.
"""

from __future__ import annotations

AGENT_ID = "summarizer"

SKILLS: tuple[str, ...] = ()
"""No shared skills — a one-shot micro-agent with a complete prompt of its
own (skills carry teaching-behavior rules; this agent doesn't teach)."""

SYSTEM_PROMPT = (
    "You write TL;DRs for academic papers. Given a paper's title and "
    "abstract, return one field:\n"
    "- tldr: a single plain-language sentence (two at most, ~25 words) "
    "stating what the paper does and what it found — the register of "
    "Semantic Scholar's TLDRs. Lead with the contribution, not the topic: "
    "'Introduces X, showing Y' beats 'This paper is about X'.\n\n"
    "Summarize only what the abstract actually claims — no outside "
    "knowledge, no evaluation, no lead-ins like 'This paper' or 'TL;DR:'."
)
