"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
The summarizer's words and knobs: its agent id, its three system prompts, and
skills. Model choice and tunables live in its ``config.llm.agents`` entry.

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

PAPER_NAME_SYSTEM_PROMPT = (
    "You turn the informal name of a research paper into its real title. "
    "Researchers refer to papers by nicknames and acronyms — 'DQN', 'the "
    "ResNet paper', 'BERT', 'Attention is all you need' — and the title on "
    "the paper often contains none of those words. Given such a name, return "
    "two fields:\n"
    "- title: the paper's actual, full title as published, or an empty "
    "string if you don't know it.\n"
    "- confident: true only when you are sure this name refers to that one "
    "specific paper.\n\n"
    "Be strict about `confident`. 'DQN' means one paper (Playing Atari with "
    "Deep Reinforcement Learning) and deserves true. 'transformers', "
    "'reinforcement learning' and 'graph networks' name whole fields, not "
    "papers — return an empty title and false. A name you half-recognize is "
    "also false: a wrong title sends the reader to the wrong paper, while "
    "false just leaves them with the ordinary search results they already "
    "have. Never invent a plausible-sounding title."
)
"""The paper-name resolver's prompt. On the summarizer's *agent id* for the
same reason ``TITLE_SYSTEM_PROMPT`` is — a one-shot micro-agent emitting a
short piece of text, run on the crew's cheapest configured model rather than
adding a sixth entry to Agent Settings.

**Why a model is here at all**, in a lookup path documented as model-free: no
amount of text matching gets from "dqn" to *Playing Atari with Deep
Reinforcement Learning*. Measured, not assumed — S2's free-text search cannot
reach that paper for that query even at limit 30, ``match_title('dqn')``
returns nothing, and no field of the cached node (title, authors, abstract,
tldr, venue) contains the string, because the 2013 paper predates the name.
The mapping is world knowledge, so the only thing that can supply it is a
model. It runs **only** when text matching has already failed, only on the
debounced pass, and its answer is cached per query — see
``services/search/naming.py``."""
