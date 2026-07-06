"""The query analyst: expansion and title recall flow through from the
model's structured output, and every failure mode degrades to a passthrough."""

from __future__ import annotations

from pydantic_ai.models.function import FunctionModel
from pydantic_ai.models.test import TestModel

from arxiv_digest.agents import query_analyst

PASSTHROUGH = query_analyst.Expansion(expanded_query="DQN", known_titles=[])


def analyst_model(expanded: str, titles: list[str]) -> TestModel:
    return TestModel(
        custom_output_args={"expanded_query": expanded, "known_titles": titles}
    )


def test_expansion_and_titles_come_from_the_structured_output():
    model = analyst_model("DQN deep Q-network", ["Playing Atari with Deep RL", "  "])
    with query_analyst.agent.override(model=model):
        analysis = query_analyst.analyze("DQN")
    assert analysis.expanded_query == "DQN deep Q-network"
    assert analysis.known_titles == ["Playing Atari with Deep RL"]  # blanks dropped


def test_blank_query_short_circuits_before_the_model():
    def explode(messages, info):
        raise AssertionError("the model must not be engaged for a blank query")

    with query_analyst.agent.override(model=FunctionModel(explode)):
        assert query_analyst.analyze("").expanded_query == ""
        assert query_analyst.analyze("   ").known_titles == []


def test_model_failure_degrades_to_passthrough():
    def boom(messages, info):
        raise RuntimeError("api down")

    with query_analyst.agent.override(model=FunctionModel(boom)):
        assert query_analyst.analyze("DQN") == PASSTHROUGH


def test_blocked_live_call_degrades_to_passthrough():
    # No override: conftest's ALLOW_MODEL_REQUESTS=False makes the run raise
    # before any network — and analyze eats even that.
    assert query_analyst.analyze("DQN") == PASSTHROUGH


def test_blank_expansion_falls_back_to_the_original():
    model = analyst_model("   ", [])
    with query_analyst.agent.override(model=model):
        assert query_analyst.analyze("DQN") == PASSTHROUGH


def test_query_is_stripped_before_analysis():
    seen = {}

    def record(messages, info):
        seen["prompt"] = messages[0].parts[-1].content
        raise RuntimeError("stop after recording")  # passthrough returns the strip

    with query_analyst.agent.override(model=FunctionModel(record)):
        assert query_analyst.analyze("  DQN  ") == PASSTHROUGH
    assert seen["prompt"] == "DQN"
