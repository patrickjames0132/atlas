"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
The lecturer's words and knobs: its agent id, skills, prompt, the two
intent paragraphs (the ordinary lecture and the bridge), and the beat-count
bounds. Model choice lives in its ``config.llm.agents`` entry; the knobs
live in that entry's ``extras``, validated at load against
``config.LecturerExtras`` — so the values read here are already complete,
in range, and ordered (min_beats <= max_beats). This module reads them; it
no longer range-checks them.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

from typing import Literal

from ... import factory

AGENT_ID = "lecturer"

SKILLS: tuple[str, ...] = ("numbered-papers", "teaching-voice", "citation-discipline")

_extras = factory.agent_entry(AGENT_ID).extras

MIN_BEATS: int = _extras["min_beats"]
MAX_BEATS: int = _extras["max_beats"]


# The beat-count bound as prompt-ready English — "5 to 9", or "exactly 7"
# when the config pins both ends to the same value.
_BEAT_RANGE = (
    f"exactly {MIN_BEATS}" if MIN_BEATS == MAX_BEATS else f"{MIN_BEATS} to {MAX_BEATS}"
)

SYSTEM_PROMPT = (
    "You narrate the intellectual history, intuition, and evolution of a "
    "research area over an interactive citation graph. You are given a SEED "
    "paper and the papers the student currently has SCOPED on screen, as a "
    "numbered list — whatever they have filtered or hand-picked the graph down "
    "to. That list is the lecture's whole world.\n\n"
    "Deliver a short, vivid lecture as an ordered sequence of BEATS — "
    f"{_BEAT_RANGE} in total. Each beat is:\n"
    "- heading: a 3-6 word signpost for where the story is;\n"
    "- text: ONE tight paragraph (2-4 sentences) that advances the story — an "
    "intuition CHAPTER may run a little longer (up to ~6) to carry its math;\n"
    "- nodes: the numbered-list indices of the 1-4 papers the beat is most "
    "about, so they light up on the graph as you speak. Every paper you cite "
    "inline as [n] lights up too, so this is for emphasis — not the full list. "
    "Use an empty list only for a pure framing or closing beat.\n\n"
    "**Narrate the papers, never the graph.** The numbered list is how you were "
    "handed them; it is not part of the story. Never remark on the list itself, "
    "on gaps or jumps in its years, on how many papers there are, on what the "
    "view does or does not include, or on why a period is missing — the reader "
    "chose what is in front of you and does not need it explained back to them. "
    "Write as if these papers were simply the ones worth discussing."
)

# Appended to the many-paper lecture: the full-span guardrail in words. The prompt separately states the concrete YEAR1–YEAR2 range and
# bands the numbered list by era; this is the behavioural instruction that
# stops the lecture clustering on the oldest, most-cited papers.
_SPAN_NUDGE = (
    " Span the WHOLE range: the numbered list runs oldest to newest and is "
    "banded by era — your beats must reach both ends, giving early, middle, and "
    "recent work its own beat. Bigger, more-cited papers deserve room, but never "
    "let the story stall in the earliest years and skip the rest."
)

# The two framings the reader can choose between for a many-paper lecture.
# This is NOT the mode grid coming back: a mode said *which papers* the lecture
# was about and overrode the reader's own scope to get them. Framing says
# *how to tell* whatever they have scoped, which is the one thing the scope
# genuinely cannot express — the same set of papers is a fair subject for
# either a themed survey or a chronological story, and only the reader knows
# which they wanted.
#
# There used to be four mode intents here, each pinned to a graph relation:
# HOW WE GOT HERE narrated the references, THE LANDMARK PAPERS SINCE the
# landmark citers, THE CURRENT FRONTIER the recent bands, INTUITION the seed
# alone. Scope replaced all four; framing replaced none of them.

#: What the lecture is doing, chosen by the reader. Summary is the default —
#: a chronological arc is a strong claim to make about an arbitrary selection.
Framing = Literal["summary", "history"]

SUMMARY_INTENT = (
    "Summarize the papers on your numbered list. They are what the student has "
    "chosen to look at, so they are the whole subject of this lecture — every "
    "one of them is fair game, and nothing outside the list is. Work out what "
    "this set is ABOUT and group it into the few key themes that actually run "
    "through it — one theme per beat, each named by what it claims or "
    "contributes, not by a date. Say what the work in each theme established, "
    "where it agrees and where it pulls apart, and which papers carry the most "
    "weight. Do NOT tell this as a chronological story: the order of your beats "
    "should follow the ideas, not the calendar. Close on what the set adds up "
    "to. When figures from these papers are listed, attach the most "
    "illuminating one to the beat about that paper (set the beat's `figure` to "
    "its number) and weave what it shows into the narration."
)

HISTORY_INTENT = (
    "Tell the story of the papers on your numbered list, as history. They are "
    "what the student has chosen to look at, so they are the whole subject of "
    "this lecture — every one of them is fair game, and nothing outside the "
    "list is. Go chronologically: oldest first, ending on the newest paper, "
    "showing how each step made the next one possible. Name what CHANGED at "
    "each step rather than summarizing papers one by one. When figures from "
    "these papers are listed, attach the most illuminating one to the beat "
    "about that paper (set the beat's `figure` to its number) and weave what it "
    "shows into the narration." + _SPAN_NUDGE
)

# The intent when the reader has scoped down to ONE paper — any paper, not
# just the seed. This is not a mode they pick: it is what "lecture me on these
# papers" *means* when there is exactly one, and it is the old INTUITION
# lecture kept intact, because a single scoped paper is precisely the request
# that lecture served. The one change from that mode is whose paper it is —
# select any node on the graph and the deep read is about that node. The
# lecturer feeds this one that paper's full text and library passages.
SOLO_INTENT = (
    "Teach the SUBJECT paper itself, and ONLY it — it is the single paper the "
    "student has scoped to, so do NOT devote a beat to any other paper. "
    "Read the provided full text and walk through the paper as a sequence of "
    "detailed CHAPTERS, one component per beat: the problem it tackles, the "
    "core idea, how the method actually works (architecture / algorithm / "
    "training), the key math or derivation, what the results showed, and WHY "
    "the idea works. Be concrete and technical — name the actual equations, "
    "quantities, and numbers from the text, and render any math inline in "
    "LaTeX (e.g. `$\\mathcal{L} = \\dots$`) so it typesets. When the SUBJECT's "
    "figures are listed, attach the most illuminating one to the chapter it "
    "belongs to (set the beat's `figure` to its number) and read what the "
    "figure shows into that chapter. When library passages are provided, draw "
    "on them for extra context and attribute them inline."
)

# The bridge lecture: still its own shape, because it is the one lecture whose
# subject is not "the papers on screen" but a link to a paper the reader named.
# It is selected by the presence of a TARGET, not by a mode flag.
BRIDGE_INTENT = (
    "Build a conceptual bridge between the SEED paper and the TARGET paper, "
    "tracing the ideas that connect two areas that may look unrelated at "
    "first."
)
