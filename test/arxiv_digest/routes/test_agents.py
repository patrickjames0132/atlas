"""Agent routes: typed-input validation at the door, uniform event->SSE
serialization, history persistence rules, and the two separate chat stores."""

from __future__ import annotations

import json

import pytest

from arxiv_digest.agents import events
from arxiv_digest.config import config
from arxiv_digest.routes import agents as agents_routes

SEED = {
    "id": "seed01", "arxiv_id": "1312.5602", "title": "Playing Atari",
    "abstract": None, "tldr": None, "year": 2013, "month": None,
    "pub_date": None, "citation_count": 10000, "authors": None,
    "url": "https://example.org/seed01", "rels": ["seed"], "is_seed": True,
    # force-graph simulation baggage the route must tolerate:
    "x": 12.5, "vy": -0.3, "index": 0,
}
NODES = [SEED, {**SEED, "id": "node02", "title": "Q-learning", "is_seed": False}]


def frames(response) -> list[tuple[str, dict]]:
    parsed = []
    for chunk in response.data.decode().strip().split("\n\n"):
        event_line, data_line = chunk.split("\n")
        parsed.append(
            (event_line.removeprefix("event: "), json.loads(data_line.removeprefix("data: ")))
        )
    return parsed


@pytest.fixture(autouse=True)
def _fresh_stores():
    agents_routes._QA_SESSIONS.clear()
    agents_routes._SOURCES_SESSIONS.clear()
    yield


def test_lecture_types_the_payload_and_relays_by_event_type(client, monkeypatch):
    seen = {}

    def fake_run(intent, **kwargs):
        seen["intent"], seen["kwargs"] = intent, kwargs
        yield events.BackfillTrace(hop=1, found=0, oldest=None)
        yield events.Beat(heading="Roots", text="It began.", node_ids=["node02"])
        yield events.Done()

    monkeypatch.setattr(agents_routes.orchestrator, "run", fake_run)
    response = client.post("/api/lecture", json={"seed": SEED, "nodes": NODES, "mode": "intuition"})
    assert frames(response) == [
        ("trace", {"action": "backfill", "hop": 1, "found": 0, "oldest": None, "error": False}),
        ("beat", {"heading": "Roots", "text": "It began.", "node_ids": ["node02"]}),
        ("done", {}),
    ]
    assert seen["intent"] == "lecture" and seen["kwargs"]["mode"] == "intuition"
    # The route delivered typed Nodes, sim baggage stripped, annotations kept.
    typed_seed = seen["kwargs"]["seed"]
    assert typed_seed.id == "seed01" and typed_seed.is_seed is True
    assert not hasattr(typed_seed, "x")


def test_lecture_input_validation(client):
    assert client.post("/api/lecture", json={"seed": SEED, "nodes": []}).status_code == 400
    assert (
        client.post("/api/lecture", json={"seed": SEED, "nodes": NODES, "mode": "opera"}).status_code
        == 400
    )
    broken = {**SEED}
    del broken["url"]  # a required core field
    assert (
        client.post("/api/lecture", json={"seed": SEED, "nodes": [broken]}).status_code == 400
    )


def test_ask_streams_persists_and_strips_figure_markers(client, monkeypatch):
    seen = {}

    def fake_run(intent, **kwargs):
        seen["intent"], seen["kwargs"] = intent, kwargs
        yield events.Token(text="As the figure shows.\n<<FIG 1>>\nSo it works.")
        yield events.Cited(node_ids=["seed01"])
        yield events.Done()

    monkeypatch.setattr(agents_routes.orchestrator, "run", fake_run)
    body = {"question": "why?", "session_id": "sess1", "seed": SEED, "nodes": NODES,
            "source_ids": ["s1", 42, ""]}
    response = client.post("/api/ask", json=body)
    assert [name for name, _ in frames(response)] == ["token", "cited", "done"]
    assert seen["intent"] == "research"
    assert seen["kwargs"]["source_ids"] == ["s1"]  # non-strings dropped
    assert seen["kwargs"]["history"] == []
    # Persisted turn: marker stripped, both roles recorded.
    convo = agents_routes._QA_SESSIONS["sess1"]
    assert convo[0] == {"role": "user", "content": "why?"}
    assert "<<FIG" not in convo[1]["content"]
    assert "So it works." in convo[1]["content"]

    # The follow-up sees the stored history.
    client.post("/api/ask", json=body)
    assert seen["kwargs"]["history"] == convo[:2]


def test_failed_answers_do_not_poison_history(client, monkeypatch):
    def fake_run(intent, **kwargs):
        yield events.Token(text="starting...")
        yield events.Error(message="Semantic Scholar is unavailable — try again.")

    monkeypatch.setattr(agents_routes.orchestrator, "run", fake_run)
    response = client.post(
        "/api/ask", json={"question": "why?", "session_id": "sess1", "seed": SEED, "nodes": NODES}
    )
    assert frames(response)[-1] == (
        "error", {"message": "Semantic Scholar is unavailable — try again."}
    )
    assert agents_routes._QA_SESSIONS == {}  # nothing persisted


def test_history_window_is_trimmed(client, monkeypatch):
    monkeypatch.setattr(config.server, "history_turns", 1)

    def fake_run(intent, **kwargs):
        yield events.Token(text="answer")
        yield events.Done()

    monkeypatch.setattr(agents_routes.orchestrator, "run", fake_run)
    for question in ("first?", "second?"):
        # .data consumes the stream — persistence happens during iteration.
        client.post("/api/ask_sources", json={"question": question, "session_id": "lib1"}).data
    convo = agents_routes._SOURCES_SESSIONS["lib1"]
    assert len(convo) == 2  # one pair kept
    assert convo[0]["content"] == "second?"


def test_the_two_chats_use_separate_stores(client, monkeypatch):
    def fake_run(intent, **kwargs):
        yield events.Token(text="ok")
        yield events.Done()

    monkeypatch.setattr(agents_routes.orchestrator, "run", fake_run)
    client.post("/api/ask", json={"question": "graph q", "session_id": "same-id",
                                  "seed": SEED, "nodes": NODES}).data
    client.post("/api/ask_sources", json={"question": "library q", "session_id": "same-id"}).data
    assert agents_routes._QA_SESSIONS["same-id"][0]["content"] == "graph q"
    assert agents_routes._SOURCES_SESSIONS["same-id"][0]["content"] == "library q"


def test_ask_sources_has_no_availability_gate(client, monkeypatch):
    def fake_run(intent, **kwargs):
        yield events.RetrievalTrace(found=0, sources=[])
        yield events.Token(text="I couldn't find anything in your library about that.")
        yield events.Done()

    monkeypatch.setattr(agents_routes.orchestrator, "run", fake_run)
    response = client.post("/api/ask_sources", json={"question": "anything"})
    assert response.status_code == 200  # no embedder probe, no 400 refusal
    assert frames(response)[0][0] == "trace"

    assert client.post("/api/ask_sources", json={}).status_code == 400  # question required
