"""The lecturer's words and knobs: its agent id, skills, prompt, and the
three mode-intent paragraphs. Model choice lives in its ``config.llm.agents``
entry."""

from __future__ import annotations

from ..models import LectureMode

AGENT_ID = "lecturer"

SKILLS: tuple[str, ...] = ("numbered-papers", "teaching-voice", "citation-discipline")

SYSTEM_PROMPT = (
    "You narrate the intellectual history and intuition of a research area "
    "over an interactive citation graph. You are given a SEED paper and the "
    "papers currently visible around it (references, citations, similar "
    "work), as a numbered list.\n\n"
    "Deliver a short, vivid lecture as an ordered sequence of BEATS — 5 to 9 "
    "in total. Each beat is:\n"
    "- heading: a 3-6 word signpost for where the story is;\n"
    "- text: ONE tight paragraph (2-4 sentences) that advances the story;\n"
    "- nodes: the numbered-list indices of the 1-4 papers the beat is about, "
    "so they light up on the graph as you speak. Use an empty list only for "
    "a pure framing or closing beat."
)

MODE_INTENTS: dict[LectureMode, str] = {
    LectureMode.HISTORY: (
        "Mode: HOW WE GOT HERE. Tell the story chronologically — from the "
        "oldest roots among the references, through the key ideas that made "
        "each next step possible, to the SEED paper and the work it went on "
        "to spawn (its citations)."
    ),
    LectureMode.INTUITION: (
        "Mode: INTUITION OF THIS PAPER. Center the SEED paper: what problem "
        "it solved, the core idea, and why it works — using the surrounding "
        "papers only for context and contrast."
    ),
    LectureMode.BRIDGE: (
        "Mode: BRIDGE. Build a conceptual bridge between the SEED paper and "
        "the TARGET paper, tracing the ideas that connect two areas that may "
        "look unrelated at first."
    ),
}
