"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
The lecturer: typed beats stream out with indices mapped to node ids,
junk beats/indices are dropped, each mode shapes the prompt, and lectures
are illustrated — intuition reads the seed's full text and pools its own
figures (+ library passages); history/evolution/frontier pool the story's
landmark papers' figures and era-band their numbered list.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

import pytest
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.models.test import TestModel

from atlas.agents import events, lecturer
from atlas.agents.lecturer import main as lecturer_main
from atlas.agents.models import LectureMode
from atlas.services.graph import Node


def make_node(node_id: str, title: str, **overrides) -> Node:
    fields = dict(
        id=node_id,
        arxiv_id=None,
        title=title,
        abstract=None,
        tldr=None,
        year=2015,
        month=None,
        pub_date=None,
        citation_count=100,
        authors=None,
        url=f"https://example.org/{node_id}",
        rels=["reference"],
        is_seed=False,
    )
    fields.update(overrides)
    return Node(**fields)


SEED = make_node("seed01", "Playing Atari with Deep RL", is_seed=True, rels=[])
NODES = [
    SEED,
    make_node("node02", "Q-learning", year=1992),
    make_node("node03", "TD Learning", year=1988),
]


def beats_model(beats: list[dict]) -> TestModel:
    # custom_output_args is the bare output value — TestModel itself wraps it
    # in the output tool's {"response": ...} envelope.
    return TestModel(custom_output_args=beats)


def test_beats_map_indices_to_node_ids():
    model = beats_model(
        [
            {"heading": "The roots", "text": "It began with TD.", "nodes": [3, 2]},
            {"heading": "The leap", "text": "Then Atari fell.", "nodes": [1]},
            {"heading": "Closing", "text": "And so on.", "nodes": []},
        ]
    )
    with lecturer.agent.override(model=model):
        out = list(lecturer.lecture(SEED, NODES))
    assert out == [
        events.Beat(heading="The roots", text="It began with TD.", node_ids=["node03", "node02"]),
        events.Beat(heading="The leap", text="Then Atari fell.", node_ids=["seed01"]),
        events.Beat(heading="Closing", text="And so on.", node_ids=[]),
    ]


def test_beats_resolve_inline_ref_markers_for_clickable_citations():
    # A beat's prose cites papers by [n]; those markers resolve to node ids
    # (against the same numbered list) so the frontend can make them clickable —
    # independent of the structured `nodes` highlight set.
    model = beats_model(
        [{"heading": "Roots", "text": "Building on [3], later [2] followed.", "nodes": [3]}]
    )
    with lecturer.agent.override(model=model):
        out = list(lecturer.lecture(SEED, NODES))
    assert out[0].node_ids == ["node03"]  # the structured highlight set
    assert out[0].refs == {"3": "node03", "2": "node02"}  # every inline [n] used


def test_blank_text_beats_are_dropped():
    model = beats_model(
        [
            {"heading": "Empty", "text": "   ", "nodes": [1]},
            {"heading": "Real", "text": "Substance.", "nodes": [1]},
        ]
    )
    with lecturer.agent.override(model=model):
        out = list(lecturer.lecture(SEED, NODES))
    assert [beat.heading for beat in out] == ["Real"]


def test_hallucinated_indices_are_ignored():
    model = beats_model([{"heading": "H", "text": "T.", "nodes": [2, 99, 0, -1]}])
    with lecturer.agent.override(model=model):
        out = list(lecturer.lecture(SEED, NODES))
    assert out[0].node_ids == ["node02"]


def record_model(seen: dict) -> FunctionModel:
    async def record(messages, info):
        seen["request"] = messages[-1]
        raise RuntimeError("stop after recording")
        yield  # unreachable — marks this as the async generator streaming needs

    return FunctionModel(stream_function=record)


def test_history_mode_prompt_by_default():
    seen: dict = {}
    with lecturer.agent.override(model=record_model(seen)):
        with pytest.raises(RuntimeError):
            list(lecturer.lecture(SEED, NODES))
    prompt = seen["request"].parts[-1].content
    assert prompt.startswith("Mode: HOW WE GOT HERE")
    assert "SEED paper: Playing Atari with Deep RL" in prompt
    assert "TARGET paper" not in prompt
    assert "[2] (1992, 100 citations; reference) Q-learning" in prompt
    # The skills ride along as instructions (house rule: instructions=).
    assert "# Numbered papers" in seen["request"].instructions


def test_directional_prompt_bands_by_era_and_states_the_span(monkeypatch):
    """History/evolution/frontier render the numbered list banded by era and
    spell out the concrete year span — the full-span guardrail's prompt half.
    The orchestrator hands nodes oldest-first, so headers read top-to-bottom."""
    monkeypatch.setattr(
        lecturer_main.figures_mod, "get_figures", lambda arxiv_id: {"figures": []}
    )
    nodes = [
        make_node("old", "Old roots", year=1990, rels=["reference"]),
        make_node("mid", "Middle work", year=2004, rels=["reference"]),
        ARXIV_SEED,  # 2015
    ]
    seen: dict = {}
    with lecturer.agent.override(model=record_model(seen)):
        with pytest.raises(RuntimeError):
            list(lecturer.lecture(ARXIV_SEED, nodes, mode=LectureMode.HISTORY))
    prompt = seen["request"].parts[-1].content
    assert "banded by era" in prompt
    assert "--- 1990" in prompt  # the first era header
    assert "The numbered list spans 1990–2015" in prompt


def test_bridge_mode_names_the_target():
    seen: dict = {}
    target = make_node("node04", "Attention Is All You Need", year=2017)
    with lecturer.agent.override(model=record_model(seen)):
        with pytest.raises(RuntimeError):
            list(lecturer.lecture(SEED, NODES, mode=LectureMode.BRIDGE, target=target))
    prompt = seen["request"].parts[-1].content
    assert prompt.startswith("Mode: BRIDGE")
    assert "TARGET paper: Attention Is All You Need" in prompt


def test_model_failure_propagates_to_the_caller():
    async def boom(messages, info):
        raise RuntimeError("api down")
        yield  # unreachable — marks this as the async generator streaming needs

    with lecturer.agent.override(model=FunctionModel(stream_function=boom)):
        with pytest.raises(RuntimeError, match="api down"):
            list(lecturer.lecture(SEED, NODES))


# --- Intuition mode: grounded in the seed itself ------------------------------

ARXIV_SEED = make_node(
    "seed01", "Playing Atari with Deep RL", is_seed=True, rels=[], arxiv_id="1312.5602"
)
FIGS = [
    {"image": "https://ar5iv.org/fig1.png", "caption": "The DQN architecture"},
    {"image": "https://ar5iv.org/fig2.png", "caption": "Training curves"},
]
FULLTEXT = "We minimize the loss $\\mathcal{L}(\\theta)$ over Atari frames."


def _ground(monkeypatch, figures=FIGS, passages=(), fulltext=FULLTEXT):
    """Fake the intuition grounding fetches (no ar5iv, no library DB)."""
    seen: dict = {}

    def fake_figures(arxiv_id):
        seen["arxiv_id"] = arxiv_id
        return {"figures": list(figures)}

    def fake_search(query, top_k=None, source_ids=None):
        seen["query"] = query
        return list(passages)

    def fake_fulltext(arxiv_id, refresh=False):
        seen["fulltext_arxiv_id"] = arxiv_id
        return {"available": bool(fulltext), "text": fulltext}

    monkeypatch.setattr(lecturer_main.figures_mod, "get_figures", fake_figures)
    monkeypatch.setattr(lecturer_main.retrieval, "search", fake_search)
    monkeypatch.setattr(lecturer_main.fulltext_mod, "get_fulltext", fake_fulltext)
    return seen


def test_intuition_prompt_reads_the_seed_and_lists_figures_and_passages(monkeypatch):
    passages = [{"source_title": "Sutton & Barto", "page": 131, "text": "Q-learning is..."}]
    seen_ground = _ground(monkeypatch, passages=passages)
    seen: dict = {}
    with lecturer.agent.override(model=record_model(seen)):
        with pytest.raises(RuntimeError):
            list(lecturer.lecture(ARXIV_SEED, NODES, mode=LectureMode.INTUITION))
    prompt = seen["request"].parts[-1].content
    assert prompt.startswith("Mode: INTUITION OF THIS PAPER")
    # The seed's full text — read and taught in chapters, math kept as LaTeX.
    assert "Full text of the SEED paper" in prompt
    assert "$\\mathcal{L}(\\theta)$" in prompt
    # The seed's own figures, numbered for the beat's `figure` field...
    assert "Figures of the SEED paper" in prompt
    assert "1. The DQN architecture" in prompt and "2. Training curves" in prompt
    # ...and the library passages, attributed.
    assert "[Sutton & Barto, p.131] Q-learning is..." in prompt
    # Grounding queried the right things: the seed's arXiv id (figures + full
    # text) and title (library).
    assert seen_ground["arxiv_id"] == "1312.5602"
    assert seen_ground["fulltext_arxiv_id"] == "1312.5602"
    assert seen_ground["query"] == "Playing Atari with Deep RL"


def test_intuition_beats_carry_the_attached_seed_figure(monkeypatch):
    _ground(monkeypatch)
    model = beats_model(
        [
            {"heading": "The idea", "text": "One net.", "nodes": [1], "figure": 1},
            {"heading": "Junk", "text": "Bad number.", "nodes": [], "figure": 99},
            {"heading": "Plain", "text": "No figure.", "nodes": []},
        ]
    )
    with lecturer.agent.override(model=model):
        out = list(lecturer.lecture(ARXIV_SEED, NODES, mode=LectureMode.INTUITION))
    assert out[0].figure == events.BeatFigure(
        image="/api/figure_proxy?src=https%3A%2F%2Far5iv.org%2Ffig1.png",
        caption="The DQN architecture",
        number=1,
    )
    # A hallucinated number and an omitted one both mean "no figure".
    assert out[1].figure is None and out[2].figure is None


def test_story_modes_pool_the_landmark_papers_figures(monkeypatch):
    calls: list[str] = []

    def fake_figures(arxiv_id):
        calls.append(arxiv_id)
        return {"figures": [
            {"image": f"https://ar5iv.org/{arxiv_id}/f{number}.png",
             "caption": f"{arxiv_id} fig {number}"}
            for number in range(1, 6)  # five figures — the per-paper cap keeps 3
        ]}

    monkeypatch.setattr(lecturer_main.figures_mod, "get_figures", fake_figures)
    monkeypatch.setattr(
        lecturer_main.retrieval, "search",
        lambda query, top_k=None, source_ids=None: pytest.fail(
            "the library must not be searched outside intuition mode"
        ),
    )
    ancestors = [
        make_node(f"anc{number}", f"Ancestor {number}", year=1990 + number,
                  arxiv_id=f"90{number}.0000{number}", citation_count=number * 100)
        for number in range(1, 7)  # six arXiv ancestors — the pool keeps the top 4
    ]
    # A mega-cited journal paper with no arXiv render contributes nothing.
    plain = make_node("noarxiv", "Journal Paper", year=1995, citation_count=10**6)
    seen: dict = {}
    with lecturer.agent.override(model=record_model(seen)):
        with pytest.raises(RuntimeError):
            list(lecturer.lecture(ARXIV_SEED, [ARXIV_SEED, plain, *ancestors]))  # history
    prompt = seen["request"].parts[-1].content
    assert "Figures from the story's papers" in prompt
    # The seed leads, then the 4 most-cited arXiv papers.
    assert calls == ["1312.5602", "906.00006", "905.00005", "904.00004", "903.00003"]
    # Entries carry their source paper, 3 figures per paper (5 x 3 = 15).
    assert "[Ancestor 6] 906.00006 fig 1" in prompt
    assert prompt.count("[Ancestor 6]") == 3
    assert "\n15. " in prompt and "\n16. " not in prompt


def test_story_beat_figures_carry_the_source_paper(monkeypatch):
    monkeypatch.setattr(
        lecturer_main.figures_mod, "get_figures",
        lambda arxiv_id: {"figures": [{"image": "https://ar5iv.org/f1.png", "caption": "Arch"}]},
    )
    model = beats_model([{"heading": "H", "text": "T.", "nodes": [1], "figure": 1}])
    with lecturer.agent.override(model=model):
        out = list(lecturer.lecture(ARXIV_SEED, NODES))  # history; pool = the seed's figure
    assert out[0].figure == events.BeatFigure(
        image="/api/figure_proxy?src=https%3A%2F%2Far5iv.org%2Ff1.png",
        caption="Arch",
        number=1,
        title="Playing Atari with Deep RL",
    )


def test_bridge_mode_fetches_no_grounding(monkeypatch):
    monkeypatch.setattr(
        lecturer_main.figures_mod, "get_figures",
        lambda arxiv_id: pytest.fail("bridge lectures show no figures"),
    )
    monkeypatch.setattr(
        lecturer_main.retrieval, "search",
        lambda query, top_k=None, source_ids=None: pytest.fail(
            "the library must not be searched outside intuition mode"
        ),
    )
    seen: dict = {}
    target = make_node("node04", "Attention Is All You Need", year=2017)
    with lecturer.agent.override(model=record_model(seen)):
        with pytest.raises(RuntimeError):
            list(lecturer.lecture(ARXIV_SEED, NODES, mode=LectureMode.BRIDGE, target=target))
    prompt = seen["request"].parts[-1].content
    assert "Figures" not in prompt and "library" not in prompt


def test_intuition_grounding_failures_never_block_the_lecture(monkeypatch):
    def explode(*args, **kwargs):
        raise RuntimeError("ar5iv down")

    monkeypatch.setattr(lecturer_main.figures_mod, "get_figures", explode)
    monkeypatch.setattr(lecturer_main.retrieval, "search", explode)
    monkeypatch.setattr(lecturer_main.fulltext_mod, "get_fulltext", explode)
    model = beats_model([{"heading": "H", "text": "Still lectures.", "nodes": [1]}])
    with lecturer.agent.override(model=model):
        out = list(lecturer.lecture(ARXIV_SEED, NODES, mode=LectureMode.INTUITION))
    assert [beat.text for beat in out] == ["Still lectures."]
    assert out[0].figure is None


def test_frontier_intent_is_thematic_and_forward():
    """The frontier lecture is a THEMATIC survey (grouped into current threads),
    but still oriented forward in time, and — like the other many-paper modes —
    carries the full-span guardrail."""
    from atlas.agents.lecturer.config import MODE_INTENTS

    frontier = MODE_INTENTS[LectureMode.FRONTIER]
    assert "threads" in frontier  # thematic
    assert "Move forward in time" in frontier  # oriented forward
    assert "reach both ends" in frontier  # the _SPAN_NUDGE is appended


def test_frontier_prompt_is_era_banded_like_the_other_arcs(monkeypatch):
    """FRONTIER shares the chronological scaffolding — its numbered list is
    era-banded with a concrete span line — so the thematic survey still reads
    forward in time."""
    monkeypatch.setattr(
        lecturer_main.figures_mod, "get_figures", lambda arxiv_id: {"figures": []}
    )
    nodes = [
        SEED,  # no arXiv id → no figure fetch
        make_node("late-a", "Recent A", year=2021, rels=["latest"]),
        make_node("late-b", "Recent B", year=2025, rels=["latest"]),
    ]
    seen: dict = {}
    with lecturer.agent.override(model=record_model(seen)):
        with pytest.raises(RuntimeError):
            list(lecturer.lecture(SEED, nodes, mode=LectureMode.FRONTIER))
    prompt = seen["request"].parts[-1].content
    assert prompt.startswith("Mode: THE CURRENT FRONTIER")
    assert "banded by era" in prompt
    assert "The numbered list spans" in prompt


def test_every_lecture_mode_has_an_intent():
    """The prompt does ``MODE_INTENTS[mode]`` with no fallback, so a mode
    missing its intent paragraph is a KeyError at lecture time. Guard it: every
    LectureMode must have an entry (catches a new mode added without a prompt)."""
    from atlas.agents.lecturer.config import MODE_INTENTS

    assert set(MODE_INTENTS) == set(LectureMode)
