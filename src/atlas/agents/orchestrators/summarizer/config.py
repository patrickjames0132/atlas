"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
The summarizer's words and knobs: its agent id, system prompt, and skills.
Model choice and tunables live in its ``config.llm.agents`` entry.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

AGENT_ID = "summarizer"

SKILLS: tuple[str, ...] = ()
"""No shared skills — a one-shot micro-agent with a complete prompt of its
own (skills carry teaching-behavior rules; this agent doesn't teach)."""

TITLE_SYSTEM_PROMPT = (
    "You name a research conversation, the way a person would name a note "
    "they meant to find again. Given the opening turns of a chat between a "
    "reader and a research assistant, return one field:\n"
    "- title: a short noun phrase naming what the conversation is ABOUT — "
    "three to six words, no trailing period, capitalized like a headline.\n\n"
    "Name the subject, not the activity: 'Attention vs. convolution' beats "
    "'A discussion about attention'. Never open with 'Chat about', "
    "'Conversation on', 'Exploring' or 'Understanding'. If the reader asked "
    "about one specific paper, its short name is a good title. Use only what "
    "the turns actually say — no outside knowledge, and no guessing at where "
    "the conversation might go next."
)
"""The titler's prompt. Shares the summarizer's *agent id* (and so its
configured model) rather than adding a sixth agent to Agent Settings: both
are one-shot micro-agents writing a short piece of text, and the summarizer
is already documented as the crew's cheapest, safest-to-downgrade member."""

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
