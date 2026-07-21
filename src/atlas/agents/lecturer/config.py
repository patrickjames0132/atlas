"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
The lecturer's words and knobs: its agent id, skills, prompt, the
mode-intent paragraphs, the frontier recency window, and the beat-count
bounds. Model choice lives in its ``config.llm.agents`` entry; the knobs
live in that entry's ``extras``, validated at load against
``config.LecturerExtras`` — so the values read here are already complete,
in range, and ordered (min_beats <= max_beats). This module reads them; it
no longer range-checks them.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

from .. import factory
from ..models import LectureMode

AGENT_ID = "lecturer"

SKILLS: tuple[str, ...] = ("numbered-papers", "teaching-voice", "citation-discipline")

_extras = factory.agent_entry(AGENT_ID).extras

FRONTIER_WINDOW_MONTHS: int = _extras["frontier_window_months"]
MIN_BEATS: int = _extras["min_beats"]
MAX_BEATS: int = _extras["max_beats"]


def _window_phrase(months: int) -> str:
    """The frontier window as prompt-ready English ("year", "5 years",
    "18 months") — the FRONTIER mode intent must describe the same window
    the orchestrator's ``_story_nodes`` actually scopes the papers to.

    Args:
        months: The window length in months.

    Returns:
        A human phrase for "the last <phrase> or so".
    """
    if months % 12 == 0:
        years = months // 12
        return "year" if years == 1 else f"{years} years"
    return f"{months} months"

# The beat-count bound as prompt-ready English — "5 to 9", or "exactly 7"
# when the config pins both ends to the same value.
_BEAT_RANGE = (
    f"exactly {MIN_BEATS}" if MIN_BEATS == MAX_BEATS else f"{MIN_BEATS} to {MAX_BEATS}"
)

SYSTEM_PROMPT = (
    "You narrate the intellectual history, intuition, and evolution of a "
    "research area over an interactive citation graph. You are given a SEED "
    "paper and the papers currently visible around it (references, citations, "
    "similar work), as a numbered list.\n\n"
    "Deliver a short, vivid lecture as an ordered sequence of BEATS — "
    f"{_BEAT_RANGE} in total. Each beat is:\n"
    "- heading: a 3-6 word signpost for where the story is;\n"
    "- text: ONE tight paragraph (2-4 sentences) that advances the story — an "
    "intuition CHAPTER may run a little longer (up to ~6) to carry its math;\n"
    "- nodes: the numbered-list indices of the 1-4 papers the beat is about, "
    "so they light up on the graph as you speak. Use an empty list only for "
    "a pure framing or closing beat."
)

# Appended to every chronological (multi-paper) mode: the full-span guardrail
# in words. The prompt separately states the concrete YEAR1–YEAR2 range and
# bands the numbered list by era; this is the behavioural instruction that
# stops the lecture clustering on the oldest, most-cited papers.
_SPAN_NUDGE = (
    " Span the WHOLE range: the numbered list runs oldest to newest and is "
    "banded by era — your beats must reach both ends, giving early, middle, and "
    "recent work its own beat. Bigger, more-cited papers deserve room, but never "
    "let the story stall in the earliest years and skip the rest."
)

MODE_INTENTS: dict[LectureMode, str] = {
    LectureMode.HISTORY: (
        "Mode: HOW WE GOT HERE. Tell the story of the SEED's REFERENCES — the "
        "papers it stands on. Go chronologically: from the oldest roots, "
        "through the key ideas that made each next step possible, and END AT "
        "the SEED paper, the destination and final beat. Every non-seed paper "
        "on your list is a reference the seed cites; don't reach for anything "
        "else. When figures from the story's papers are listed, attach the most "
        "illuminating one to the beat about that paper (set the beat's `figure` "
        "to its number) and weave what it shows into the narration." + _SPAN_NUDGE
    ),
    LectureMode.INTUITION: (
        "Mode: INTUITION OF THIS PAPER. Teach the SEED paper itself, and ONLY "
        "the seed — do NOT devote a beat to any other paper (there are none on "
        "your list; this is not a tour of the field). Read the provided full "
        "text and walk through the paper as a sequence of detailed CHAPTERS, "
        "one component per beat: the problem it tackles, the core idea, how the "
        "method actually works (architecture / algorithm / training), the key "
        "math or derivation, what the results showed, and WHY the idea works. "
        "Be concrete and technical — name the actual equations, quantities, and "
        "numbers from the text, and render any math inline in LaTeX (e.g. "
        "`$\\mathcal{L} = \\dots$`) so it typesets. When the SEED's figures are "
        "listed, attach the most illuminating one to the chapter it belongs to "
        "(set the beat's `figure` to its number) and read what the figure "
        "shows into that chapter. When library passages are provided, draw on "
        "them for extra context and attribute them inline."
    ),
    LectureMode.EVOLUTION: (
        "Mode: SUMMARIZE THE LANDMARK PAPERS SINCE. Every non-seed paper on "
        "your list is a LANDMARK paper that CITES the seed — the influential "
        "work that built on it. Start at the SEED and move FORWARD in time "
        "through those landmarks — the follow-ups, newer architectures, and "
        "refinements — showing how each advanced the idea, and ending at the "
        "newest landmark on your list. The reverse of HOW WE GOT HERE: tell "
        "the future, not the past, and stay on the landmark citers (not the "
        "seed's references or loosely-similar work). The CURRENT FRONTIER is "
        "a separate lecture: don't survey what's active right now or forecast "
        "where the field is heading — close on the newest landmark's "
        "contribution and stop there. When figures from the story's "
        "papers are listed, attach the most illuminating one to the beat about "
        "that paper (set the beat's `figure` to its number) and weave what it "
        "shows into the narration." + _SPAN_NUDGE
    ),
    LectureMode.FRONTIER: (
        "Mode: THE CURRENT FRONTIER. Survey ONLY the graph's Latest "
        "Publications — the newest papers around the seed (roughly the last "
        f"{_window_phrase(FRONTIER_WINDOW_MONTHS)} of per-year bands) — to show "
        "what is active RIGHT NOW. Every paper on your list is one of those "
        "recent works; don't reach back to older landmarks or references. Group "
        "them into a few coherent current threads (open problems, hot "
        "directions, the latest advances) — one thread per beat, not a flat "
        "list. Move forward in time as you go: order the threads from the "
        "earlier-emerging recent directions toward the very newest, and close "
        "by saying where the frontier seems to be heading. When figures from "
        "the story's papers are listed, attach the most illuminating one to the "
        "beat about that paper (set the beat's `figure` to its number) and "
        "weave what it shows into the narration." + _SPAN_NUDGE
    ),
    LectureMode.BRIDGE: (
        "Mode: BRIDGE. Build a conceptual bridge between the SEED paper and "
        "the TARGET paper, tracing the ideas that connect two areas that may "
        "look unrelated at first."
    ),
}
