"""The query analyst: expansion flows through from the model's structured
output, and every failure mode degrades to a passthrough."""

from __future__ import annotations

from pydantic_ai.models.function import FunctionModel
from pydantic_ai.models.test import TestModel

from arxiv_digest.agents import query_analyst


def test_expansion_comes_from_the_structured_output():
    model = TestModel(custom_output_args={"expanded_query": "DQN deep Q-network"})
    with query_analyst.agent.override(model=model):
        assert query_analyst.expand_query("DQN") == "DQN deep Q-network"


def test_blank_query_short_circuits_before_the_model():
    def explode(messages, info):
        raise AssertionError("the model must not be engaged for a blank query")

    with query_analyst.agent.override(model=FunctionModel(explode)):
        assert query_analyst.expand_query("") == ""
        assert query_analyst.expand_query("   ") == ""


def test_model_failure_degrades_to_passthrough():
    def boom(messages, info):
        raise RuntimeError("api down")

    with query_analyst.agent.override(model=FunctionModel(boom)):
        assert query_analyst.expand_query("DQN") == "DQN"


def test_blocked_live_call_degrades_to_passthrough():
    # No override: conftest's ALLOW_MODEL_REQUESTS=False makes the run raise
    # before any network — and expand_query eats even that.
    assert query_analyst.expand_query("DQN") == "DQN"


def test_blank_expansion_falls_back_to_the_original():
    model = TestModel(custom_output_args={"expanded_query": "   "})
    with query_analyst.agent.override(model=model):
        assert query_analyst.expand_query("DQN") == "DQN"


def test_query_is_stripped_before_expansion():
    seen = {}

    def record(messages, info):
        seen["prompt"] = messages[0].parts[-1].content
        raise RuntimeError("stop after recording")  # passthrough returns the strip

    with query_analyst.agent.override(model=FunctionModel(record)):
        assert query_analyst.expand_query("  DQN  ") == "DQN"
    assert seen["prompt"] == "DQN"
