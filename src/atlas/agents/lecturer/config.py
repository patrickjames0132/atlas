"""The lecturer's words and knobs: its agent id, skills, prompt, the
mode-intent paragraphs, the frontier recency window, and the beat-count
bounds. Model choice lives in its ``config.llm.agents`` entry; the knobs
live in that entry's ``extras`` (the staging area — promoted to typed
config fields once their shape settles). Unknown extras keys fail at
import so the staging area can't silently accumulate junk.
"""

from __future__ import annotations

from .. import factory
from ..models import LectureMode

AGENT_ID = "lecturer"

SKILLS: tuple[str, ...] = ("numbered-papers", "teaching-voice", "citation-discipline")

EXTRA_DEFAULTS: dict[str, int] = {
    # THE CURRENT FRONTIER's recency window, in months. Wide (~5 years) on
    # purpose: since the OpenAlex hybrid (v4.0.0) the graph's light-green
    # "Latest Publications" nodes span the newest years plus the
    # `graph.latest_band_years` per-year bands below them, so the old
    # 12-month lecture window narrated almost none of what the user sees.
    "frontier_window_months": 60,
    # How many beats a lecture asks for. The bound lives in the prompt (there
    # is no hard output cap): it's also what keeps lecture length in check —
    # raising max_beats materially lengthens (and slows) every lecture.
    "min_beats": 5,
    "max_beats": 9,
}

_extras = factory.agent_entry(AGENT_ID).extras
_unknown = set(_extras) - set(EXTRA_DEFAULTS)
if _unknown:
    raise ValueError(
        f"unknown lecturer extras {sorted(_unknown)!r} in config.llm.agents — "
        f"known knobs: {sorted(EXTRA_DEFAULTS)}"
    )

FRONTIER_WINDOW_MONTHS: int = int(
    _extras.get("frontier_window_months", EXTRA_DEFAULTS["frontier_window_months"])
)
if FRONTIER_WINDOW_MONTHS <= 0:
    raise ValueError(
        f"lecturer extras frontier_window_months must be positive, "
        f"got {FRONTIER_WINDOW_MONTHS}"
    )

MIN_BEATS: int = int(_extras.get("min_beats", EXTRA_DEFAULTS["min_beats"]))
MAX_BEATS: int = int(_extras.get("max_beats", EXTRA_DEFAULTS["max_beats"]))
if not 1 <= MIN_BEATS <= MAX_BEATS:
    raise ValueError(
        f"lecturer extras need 1 <= min_beats <= max_beats, "
        f"got min_beats={MIN_BEATS}, max_beats={MAX_BEATS}"
    )


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
    "- text: ONE tight paragraph (2-4 sentences) that advances the story;\n"
    "- nodes: the numbered-list indices of the 1-4 papers the beat is about, "
    "so they light up on the graph as you speak. Use an empty list only for "
    "a pure framing or closing beat."
)

MODE_INTENTS: dict[LectureMode, str] = {
    LectureMode.HISTORY: (
        "Mode: HOW WE GOT HERE. Tell the story chronologically — from the "
        "oldest roots among the references, through the key ideas that made "
        "each next step possible — and END AT the SEED paper: the seed is "
        "the destination and the final beat. Never discuss work that came "
        "after the seed (that story belongs to WHAT'S EVOLVED SINCE). When "
        "figures from the story's papers are listed, attach the most "
        "illuminating one to the beat about that paper (set the beat's "
        "`figure` to its number) and weave what it shows into the narration."
    ),
    LectureMode.INTUITION: (
        "Mode: INTUITION OF THIS PAPER. Stay tightly on the SEED paper "
        "itself — do NOT retell the field's history or tour the surrounding "
        "graph (those are other modes' jobs). Walk through the paper's own "
        "components: the problem it tackles, the core idea, how the method "
        "actually works (architecture / algorithm / training), what the "
        "results showed, and WHY the idea works. A surrounding paper may be "
        "named only in passing, for contrast. When the SEED's figures are "
        "listed, attach the most illuminating one to the beat it belongs to "
        "(set the beat's `figure` to its number) and weave what the figure "
        "shows into that beat's narration. When library passages are "
        "provided, draw on them for extra context and attribute them inline."
    ),
    LectureMode.EVOLUTION: (
        "Mode: WHAT'S EVOLVED SINCE. Start at the SEED paper and move FORWARD "
        "in time through the work that built on it — the follow-ups, newer "
        "architectures, and refinements its citations represent — showing how "
        "each step advanced the idea, and ending at the current frontier / "
        "state of the art. The reverse of HOW WE GOT HERE: tell the future, "
        "not the past. When figures from the story's papers are listed, "
        "attach the most illuminating one to the beat about that paper (set "
        "the beat's `figure` to its number) and weave what it shows into the "
        "narration."
    ),
    LectureMode.FRONTIER: (
        "Mode: THE CURRENT FRONTIER. Survey the NEWEST work around the seed — "
        f"only the papers of the last {_window_phrase(FRONTIER_WINDOW_MONTHS)} "
        "or so, both recent citations and "
        "recent similar work — to show what is active RIGHT NOW. This is NOT "
        "the whole arc since the seed (that is WHAT'S EVOLVED SINCE); stay at "
        "the leading edge. Group the recent papers into a few coherent current "
        "threads (open problems, hot directions, the latest advances) rather "
        "than a flat list, and say where the frontier seems to be heading. "
        "When figures from the story's papers are listed, attach the most "
        "illuminating one to the beat about that paper (set the beat's "
        "`figure` to its number) and weave what it shows into the narration."
    ),
    LectureMode.BRIDGE: (
        "Mode: BRIDGE. Build a conceptual bridge between the SEED paper and "
        "the TARGET paper, tracing the ideas that connect two areas that may "
        "look unrelated at first."
    ),
}
