"""The dispatcher: intent routing, backfill enrichment feeding the lecturer,
and the Done/Error termination contract."""

from __future__ import annotations

from arxiv_digest.agents import events
from arxiv_digest.agents.models import Intent, LectureMode
from arxiv_digest.agents.orchestrator import main as orchestrator_main
from arxiv_digest.agents.orchestrator import run
from arxiv_digest.services.graph import Node


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


SEED = make_node("seed01", "Seed", is_seed=True, rels=[])
NODES = [SEED, make_node("node02", "Other", year=1992)]
ANCESTOR = events.DiscoveredNode(
    id="anc01", arxiv_id=None, title="Bellman 1957", abstract=None, tldr=None,
    year=1957, month=None, pub_date=None, citation_count=50000, authors=None,
    url="https://example.org/anc01", rels=["reference"], is_seed=False,
)


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


def test_history_lecture_backfills_then_narrates_the_enriched_set(monkeypatch):
    def fake_backfill(seed, nodes):
        yield events.BackfillTrace(hop=1, found=1, oldest=1957)
        yield events.Discovery(nodes=[ANCESTOR], edges=[])

    seen: dict = {}

    def fake_lecture(seed, nodes, mode="history", target=None):
        seen["nodes"], seen["mode"] = nodes, mode
        yield events.Beat(heading="Roots", text="It began.", node_ids=["anc01"])

    monkeypatch.setattr(orchestrator_main.backfill, "history_backfill", fake_backfill)
    monkeypatch.setattr(orchestrator_main.lecturer, "lecture", fake_lecture)
    out = list(run(Intent.LECTURE, seed=SEED, nodes=NODES))
    assert [event.type for event in out] == ["trace", "discovery", "beat", "done"]
    # The lecturer narrates the backfill-enriched node set.
    assert [node.id for node in seen["nodes"]] == ["seed01", "node02", "anc01"]


def test_non_history_modes_skip_the_backfill(monkeypatch):
    def explode(seed, nodes):
        raise AssertionError("backfill must not run outside history mode")

    monkeypatch.setattr(orchestrator_main.backfill, "history_backfill", explode)
    monkeypatch.setattr(
        orchestrator_main.lecturer, "lecture",
        lambda seed, nodes, mode="history", target=None: iter(
            [events.Beat(heading="H", text="T.", node_ids=[])]
        ),
    )
    out = list(run(Intent.LECTURE, seed=SEED, nodes=NODES, mode=LectureMode.INTUITION))
    assert [event.type for event in out] == ["beat", "done"]


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
