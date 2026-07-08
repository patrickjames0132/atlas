"""The dispatcher: intent routing (lectures are pure delegation — they never
expand the graph) and the Done/Error termination contract."""

from __future__ import annotations

from atlas.agents import events
from atlas.agents.models import Intent, LectureMode
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
    make_node("node02", "Ancestor", year=1992),
    make_node("desc01", "Descendant", year=2023, rels=["citation"]),
    make_node("nodate", "Undated Similar", year=None, rels=["similar"]),
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

    def fake_answer(question, seed, nodes, history=None, source_ids=None):
        seen.update(question=question, seed=seed, nodes=nodes,
                    history=history, source_ids=source_ids)
        yield events.Token(text="ok")

    monkeypatch.setattr(orchestrator_main.researcher, "answer", fake_answer)
    turns = [{"role": "user", "content": "earlier"}]
    out = list(run(Intent.RESEARCH, question="why?", seed=SEED, nodes=NODES,
                   history=turns, source_ids=["s1"]))
    assert seen == {"question": "why?", "seed": SEED, "nodes": NODES,
                    "history": turns, "source_ids": ["s1"]}
    assert out[-1] == events.Done()


def test_lecture_scopes_the_visible_nodes_per_mode(monkeypatch):
    """A lecture never expands the graph — the lecturer only ever receives
    visible nodes — and the directional modes are clamped to their side of
    the seed: history ends AT the seed (no descendants), evolution starts
    from it (no ancestors). Undated papers can't be placed in a
    chronological story, so the clamped modes drop them; intuition sees
    everything."""
    seen: dict = {}

    def fake_lecture(seed, nodes, mode="history", target=None):
        seen["seed"], seen["nodes"], seen["mode"] = seed, nodes, mode
        yield events.Beat(heading="Roots", text="It began.", node_ids=["node02"])

    monkeypatch.setattr(orchestrator_main.lecturer, "lecture", fake_lecture)
    expected = {
        LectureMode.HISTORY: ["seed01", "node02"],
        LectureMode.EVOLUTION: ["seed01", "desc01"],
        LectureMode.INTUITION: ["seed01", "node02", "desc01", "nodate"],
    }
    for mode, node_ids in expected.items():
        out = list(run(Intent.LECTURE, seed=SEED, nodes=NODES, mode=mode))
        # Beats only — no trace/discovery frames ever precede a lecture.
        assert [event.type for event in out] == ["beat", "done"]
        assert seen["mode"] is mode
        assert [node.id for node in seen["nodes"]] == node_ids
    assert seen["seed"] is SEED


def test_lecture_with_an_undated_seed_skips_the_clamp(monkeypatch):
    """No seed year -> nothing to clamp against; the directional modes fall
    back to the full visible set rather than dropping everything."""
    seen: dict = {}

    def fake_lecture(seed, nodes, mode="history", target=None):
        seen["nodes"] = nodes
        yield events.Beat(heading="H", text="T.", node_ids=[])

    monkeypatch.setattr(orchestrator_main.lecturer, "lecture", fake_lecture)
    undated_seed = make_node("seed01", "Seed", is_seed=True, rels=[], year=None)
    nodes = [undated_seed, *NODES[1:]]
    list(run(Intent.LECTURE, seed=undated_seed, nodes=nodes, mode=LectureMode.HISTORY))
    assert [node.id for node in seen["nodes"]] == ["seed01", "node02", "desc01", "nodate"]


def test_frontier_lecture_scopes_to_recent_nodes(monkeypatch):
    """THE CURRENT FRONTIER keeps the seed plus only papers from the last ~12
    months — any relation (recent citations AND recent similar) — by absolute
    recency, not relative to the seed's (old) year."""
    import datetime

    recent = (datetime.date.today() - datetime.timedelta(days=30)).isoformat()
    old = (datetime.date.today() - datetime.timedelta(days=1500)).isoformat()
    seed = make_node("seed01", "Seed", is_seed=True, rels=[], year=2015)
    nodes = [
        seed,
        make_node("fresh-cite", "Fresh citation", pub_date=recent, year=2026, rels=["latest"]),
        make_node("fresh-sim", "Fresh similar", pub_date=recent, year=2026, rels=["similar"]),
        make_node("old-cite", "Old citation", pub_date=old, year=2022, rels=["citation"]),
    ]
    seen: dict = {}

    def fake_lecture(seed, nodes, mode="history", target=None):
        seen["nodes"] = nodes
        yield events.Beat(heading="H", text="T.", node_ids=[])

    monkeypatch.setattr(orchestrator_main.lecturer, "lecture", fake_lecture)
    list(run(Intent.LECTURE, seed=seed, nodes=nodes, mode=LectureMode.FRONTIER))
    # Seed + both recent papers (citation and similar); the old citation drops.
    assert [node.id for node in seen["nodes"]] == ["seed01", "fresh-cite", "fresh-sim"]


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
