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

from atlas.agents import events
from atlas.agents.orchestrators import lecturer
from atlas.agents.orchestrators.lecturer import main as lecturer_main
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
    # The numbered list is the mode-scoped, CHRONOLOGICAL one the lecturer
    # builds itself (`_story_nodes`, since v7.0.0 — see test_scoping.py), so
    # [1] is the oldest paper and the 2015 seed sits at [3].
    assert out == [
        events.Beat(heading="The roots", text="It began with TD.", node_ids=["seed01", "node02"]),
        events.Beat(heading="The leap", text="Then Atari fell.", node_ids=["node03"]),
        events.Beat(heading="Closing", text="And so on.", node_ids=[]),
    ]


def test_a_beat_lights_up_every_paper_it_cites_not_just_its_structured_picks():
    """The prompt asks for 1-4 papers in `nodes` — the beat's focus — but a beat
    over a broad scope routinely cites a dozen more inline. Those were silently
    unlit: a reader clicked a beat naming sixteen papers and watched three of
    them glow, with the footer saying "3 papers". `node_ids` is now the union,
    the model's own picks first (the emphasis) then anything else cited, in
    first-mention order."""
    model = beats_model(
        [{"heading": "Roots", "text": "Building on [3], later [2] followed.", "nodes": [3]}]
    )
    with lecturer.agent.override(model=model):
        out = list(lecturer.lecture(SEED, NODES))
    assert out[0].node_ids == ["seed01", "node02"]  # [3] picked, [2] cited
    # graph_refs still carries the marker map, for clickable citations.
    assert out[0].graph_refs == {"3": "seed01", "2": "node02"}


def test_a_cited_paper_is_not_listed_twice_when_the_model_also_picked_it():
    model = beats_model([{"heading": "Roots", "text": "Per [2].", "nodes": [2, 2]}])
    with lecturer.agent.override(model=model):
        out = list(lecturer.lecture(SEED, NODES))
    assert out[0].node_ids == ["node02"]


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


def test_the_ordinary_lecture_prompt_defaults_to_a_summary():
    seen: dict = {}
    with lecturer.agent.override(model=record_model(seen)):
        with pytest.raises(RuntimeError):
            list(lecturer.lecture(SEED, NODES))
    prompt = seen["request"].parts[-1].content
    assert prompt.startswith("Summarize the papers on your numbered list")
    assert "SEED paper: Playing Atari with Deep RL" in prompt
    assert "TARGET paper" not in prompt
    assert "[2] (1992, 100 citations; reference) Q-learning" in prompt
    # The skills ride along as instructions (house rule: instructions=).
    assert "# Numbered papers" in seen["request"].instructions


def test_a_history_framed_prompt_bands_by_era_and_states_the_span(monkeypatch):
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
            list(lecturer.lecture(ARXIV_SEED, nodes, framing="history"))
    prompt = seen["request"].parts[-1].content
    assert "banded by era" in prompt
    assert "--- 1990" in prompt  # the first era header
    assert "The numbered list spans 1990–2015" in prompt


def test_a_bridge_lecture_names_the_target():
    seen: dict = {}
    target = make_node("node04", "Attention Is All You Need", year=2017)
    with lecturer.agent.override(model=record_model(seen)):
        with pytest.raises(RuntimeError):
            list(lecturer.lecture(SEED, NODES, target=target))
    prompt = seen["request"].parts[-1].content
    assert prompt.startswith("Build a conceptual bridge")
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


def test_a_solo_scope_reads_the_seed_and_lists_figures_and_passages(monkeypatch):
    passages = [{"source_title": "Sutton & Barto", "page": 131, "text": "Q-learning is..."}]
    seen_ground = _ground(monkeypatch, passages=passages)
    seen: dict = {}
    with lecturer.agent.override(model=record_model(seen)):
        with pytest.raises(RuntimeError):
            list(lecturer.lecture(ARXIV_SEED, [ARXIV_SEED]))
    prompt = seen["request"].parts[-1].content
    assert prompt.startswith("Teach the SUBJECT paper itself")
    # The seed's full text — read and taught in chapters, math kept as LaTeX.
    assert "Full text of the SUBJECT paper" in prompt
    assert "$\\mathcal{L}(\\theta)$" in prompt
    # The seed's own figures, numbered for the beat's `figure` field...
    assert "Figures of the SUBJECT paper" in prompt
    assert "1. The DQN architecture" in prompt and "2. Training curves" in prompt
    # ...and the library passages, attributed.
    assert "[Sutton & Barto, p.131] Q-learning is..." in prompt
    # Grounding queried the right things: the seed's arXiv id (figures + full
    # text) and title (library).
    assert seen_ground["arxiv_id"] == "1312.5602"
    assert seen_ground["fulltext_arxiv_id"] == "1312.5602"
    assert seen_ground["query"] == "Playing Atari with Deep RL"


def test_a_solo_lecture_beats_carry_the_attached_seed_figure(monkeypatch):
    _ground(monkeypatch)
    model = beats_model(
        [
            {"heading": "The idea", "text": "One net.", "nodes": [1], "figure": 1},
            {"heading": "Junk", "text": "Bad number.", "nodes": [], "figure": 99},
            {"heading": "Plain", "text": "No figure.", "nodes": []},
        ]
    )
    with lecturer.agent.override(model=model):
        out = list(lecturer.lecture(ARXIV_SEED, [ARXIV_SEED]))
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
            "the library must not be searched outside a solo lecture"
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
    assert "Figures from the papers" in prompt
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
            "the library must not be searched outside a solo lecture"
        ),
    )
    seen: dict = {}
    target = make_node("node04", "Attention Is All You Need", year=2017)
    with lecturer.agent.override(model=record_model(seen)):
        with pytest.raises(RuntimeError):
            list(lecturer.lecture(ARXIV_SEED, NODES, target=target))
    prompt = seen["request"].parts[-1].content
    assert "Figures" not in prompt and "library" not in prompt


def test_solo_grounding_failures_never_block_the_lecture(monkeypatch):
    def explode(*args, **kwargs):
        raise RuntimeError("ar5iv down")

    monkeypatch.setattr(lecturer_main.figures_mod, "get_figures", explode)
    monkeypatch.setattr(lecturer_main.retrieval, "search", explode)
    monkeypatch.setattr(lecturer_main.fulltext_mod, "get_fulltext", explode)
    model = beats_model([{"heading": "H", "text": "Still lectures.", "nodes": [1]}])
    with lecturer.agent.override(model=model):
        out = list(lecturer.lecture(ARXIV_SEED, [ARXIV_SEED]))
    assert [beat.text for beat in out] == ["Still lectures."]
    assert out[0].figure is None


def test_the_two_framings_differ_on_ordering_not_on_which_papers():
    """Framing is the reader's one remaining choice about a lecture, and it must
    be about *how* to tell the scoped papers — both intents take their subject
    from the same numbered list. Summary orders by idea and says so; history
    orders by time and carries the full-span guardrail."""
    from atlas.agents.orchestrators.lecturer.config import HISTORY_INTENT, SUMMARY_INTENT

    for intent in (SUMMARY_INTENT, HISTORY_INTENT):
        assert "papers on your numbered list" in intent  # the scope is the subject
    assert "key themes" in SUMMARY_INTENT
    assert "Do NOT tell this as a chronological story" in SUMMARY_INTENT
    assert "reach both ends" not in SUMMARY_INTENT  # no span guardrail without a timeline
    assert "chronologically" in HISTORY_INTENT
    assert "reach both ends" in HISTORY_INTENT  # the _SPAN_NUDGE is appended


def test_the_system_prompt_forbids_narrating_the_graph_itself():
    """The beat that prompted this: "Notice the gap in the timeline: after [1],
    the graph jumps straight to 2023-2026..." — a beat about the *view* rather
    than the papers. The reader chose what is in front of the model, so gaps in
    it are their own doing and need no explaining back to them."""
    from atlas.agents.orchestrators.lecturer.config import SYSTEM_PROMPT

    assert "Narrate the papers, never the graph" in SYSTEM_PROMPT
    assert "gaps or jumps in its years" in SYSTEM_PROMPT


def test_a_history_framed_scope_is_era_banded_whatever_the_relations_are():
    """The chronological scaffolding — era-banded list plus a concrete span
    line — keyed off the *mode* until v7.17.0, and keys off the reader's
    framing now. A mixed bag of references and citers gets it just as a
    single-relation set did."""
    monkeypatch_free_nodes = [
        SEED,  # no arXiv id → no figure fetch
        make_node("cite-a", "Recent A", year=2021, rels=["citation"]),
        make_node("ref-b", "Old B", year=1998, rels=["reference"]),
    ]
    seen: dict = {}
    with lecturer.agent.override(model=record_model(seen)):
        with pytest.raises(RuntimeError):
            list(lecturer.lecture(SEED, monkeypatch_free_nodes, framing="history"))
    prompt = seen["request"].parts[-1].content
    assert prompt.startswith("Tell the story of the papers")
    assert "banded by era" in prompt
    assert "The numbered list spans 1998–2021" in prompt


def test_a_summary_framed_scope_is_never_era_banded():
    """The other half of the timeline-beat fix. Handing a summary an era-banded
    list and a "reach both ends of 1998-2021" line is what invited beats about
    the timeline; a summary orders its beats by idea, so it gets the plain
    numbered list and no span line."""
    nodes = [
        SEED,
        make_node("cite-a", "Recent A", year=2021, rels=["citation"]),
        make_node("ref-b", "Old B", year=1998, rels=["reference"]),
    ]
    seen: dict = {}
    with lecturer.agent.override(model=record_model(seen)):
        with pytest.raises(RuntimeError):
            list(lecturer.lecture(SEED, nodes))
    prompt = seen["request"].parts[-1].content
    assert "banded by era" not in prompt
    assert "The numbered list spans" not in prompt


def test_a_solo_scope_is_not_era_banded():
    """One paper has no timeline to band, so the solo lecture gets the plain
    numbered list — the same shape the retired INTUITION mode had."""
    seen: dict = {}
    with lecturer.agent.override(model=record_model(seen)):
        with pytest.raises(RuntimeError):
            list(lecturer.lecture(SEED, [SEED]))
    prompt = seen["request"].parts[-1].content
    assert prompt.startswith("Teach the SUBJECT paper itself")
    assert "banded by era" not in prompt
