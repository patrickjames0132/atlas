"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
The dispatcher: intent routing (lectures are pure delegation — they never
expand the graph) and the Done/Error termination contract.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

from atlas.agents import events
from atlas.agents.models import Intent, LectureMode, PlayedBeat, PlayedLecture
from atlas.agents.orchestrator import main as orchestrator_main
from atlas.agents.orchestrator import run
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


SEED = make_node("seed01", "Seed", is_seed=True, rels=[], year=2015)
NODES = [
    SEED,
    make_node("ref01", "Reference", year=1992, rels=["reference"]),
    make_node("cite01", "Landmark citer", year=2023, rels=["citation"]),
    make_node("late01", "Latest", year=2025, rels=["latest"]),
    make_node("simil01", "Undated Similar", year=None, rels=["similar"]),
]


def test_librarian_intent_relays_and_appends_done(monkeypatch):
    def fake_answer(question, history=None, source_ids=None):
        yield events.RetrievalTrace(found=1, sources=["Deep Learning"])
        yield events.Token(text="From your book.")

    monkeypatch.setattr(orchestrator_main.librarian, "answer", fake_answer)
    out = list(run(Intent.LIBRARIAN, question="q"))
    assert [event.type for event in out] == ["trace", "token", "done"]


def test_research_intent_passes_everything_through(monkeypatch):
    seen: dict = {}

    def fake_answer(question, seed, nodes, history=None, source_ids=None,
                    lectures=None, provider="s2"):
        seen.update(question=question, seed=seed, nodes=nodes, history=history,
                    source_ids=source_ids, lectures=lectures, provider=provider)
        yield events.Token(text="ok")

    monkeypatch.setattr(orchestrator_main.researcher, "answer", fake_answer)
    turns = [{"role": "user", "content": "earlier"}]
    played = [PlayedLecture(title="How we got here",
                            beats=[PlayedBeat(heading="Roots", text="It began.")])]
    out = list(run(Intent.RESEARCH, question="why?", seed=SEED, nodes=NODES,
                   history=turns, source_ids=["s1"], lectures=played, provider="openalex"))
    assert seen == {"question": "why?", "seed": SEED, "nodes": NODES,
                    "history": turns, "source_ids": ["s1"], "lectures": played,
                    "provider": "openalex"}
    assert out[-1] == events.Done()


def test_lecture_scopes_the_visible_nodes_per_relation(monkeypatch):
    """A lecture never expands the graph — the lecturer only ever receives
    visible nodes — and each mode is pinned to ONE graph relation: history
    narrates the seed's references, evolution the landmark citers, frontier
    the Latest-Publications nodes. Loosely-similar work never enters a
    directional mode. The directional sets come back sorted oldest-first
    (with the seed slotted by its own year); intuition stays on the seed
    alone; bridge sees everything, unsorted."""
    seen: dict = {}

    def fake_lecture(seed, nodes, mode="history", target=None):
        seen["seed"], seen["nodes"], seen["mode"] = seed, nodes, mode
        yield events.Beat(heading="Roots", text="It began.", node_ids=["ref01"])

    monkeypatch.setattr(orchestrator_main.lecturer, "lecture", fake_lecture)
    expected = {
        LectureMode.HISTORY: ["ref01", "seed01"],  # 1992, then the 2015 seed
        LectureMode.EVOLUTION: ["seed01", "cite01"],  # 2015 seed, then 2023
        LectureMode.FRONTIER: ["seed01", "late01"],  # 2015 seed, then 2025
        LectureMode.INTUITION: ["seed01"],  # the seed alone
        LectureMode.BRIDGE: ["seed01", "ref01", "cite01", "late01", "simil01"],
    }
    for mode, node_ids in expected.items():
        out = list(run(Intent.LECTURE, seed=SEED, nodes=NODES, mode=mode))
        # Beats only — no trace/discovery frames ever precede a lecture.
        assert [event.type for event in out] == ["beat", "done"]
        assert seen["mode"] is mode
        assert [node.id for node in seen["nodes"]] == node_ids
    assert seen["seed"] is SEED


def test_directional_lecture_sorts_undated_nodes_last(monkeypatch):
    """A relation-scoped mode still includes an undated paper carrying its
    tag, sorted to the end (it can't be placed in the timeline)."""
    seen: dict = {}

    def fake_lecture(seed, nodes, mode="history", target=None):
        seen["nodes"] = nodes
        yield events.Beat(heading="H", text="T.", node_ids=[])

    monkeypatch.setattr(orchestrator_main.lecturer, "lecture", fake_lecture)
    nodes = [
        SEED,
        make_node("ref-old", "Old ref", year=1990, rels=["reference"]),
        make_node("ref-nd", "Undated ref", year=None, rels=["reference"]),
    ]
    list(run(Intent.LECTURE, seed=SEED, nodes=nodes, mode=LectureMode.HISTORY))
    # 1990, 2015 seed, then the undated reference last.
    assert [node.id for node in seen["nodes"]] == ["ref-old", "seed01", "ref-nd"]


def test_a_failing_workflow_ends_with_error_not_done(monkeypatch):
    def broken(question, history=None, source_ids=None):
        yield events.Token(text="starting...")
        raise RuntimeError("api down")

    monkeypatch.setattr(orchestrator_main.librarian, "answer", broken)
    out = list(run(Intent.LIBRARIAN, question="q"))
    assert [event.type for event in out] == ["token", "error"]
    assert "api down" in out[-1].message


def test_unknown_intent_and_missing_args_yield_error():
    assert [event.type for event in run("mystery")] == ["error"]  # type: ignore[arg-type]
    assert [event.type for event in run(Intent.LECTURE)] == ["error"]
    assert [event.type for event in run(Intent.RESEARCH, question="why?")] == ["error"]
    assert [event.type for event in run(Intent.LIBRARIAN)] == ["error"]
