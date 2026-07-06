"""The lecturer: typed beats stream out with indices mapped to node ids,
junk beats/indices are dropped, and each mode shapes the prompt."""

from __future__ import annotations

import pytest
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.models.test import TestModel

from arxiv_digest.agents import events, lecturer
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


def test_bridge_mode_names_the_target():
    seen: dict = {}
    target = make_node("node04", "Attention Is All You Need", year=2017)
    with lecturer.agent.override(model=record_model(seen)):
        with pytest.raises(RuntimeError):
            list(lecturer.lecture(SEED, NODES, mode="bridge", target=target))
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
