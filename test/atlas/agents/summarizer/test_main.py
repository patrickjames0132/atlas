"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
The summarizer: the TL;DR flows through from the model's structured
output, the prompt carries the title and abstract, and every failure mode
degrades to None (the route turns that into a visible error).

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

from pydantic_ai.models.function import FunctionModel
from pydantic_ai.models.test import TestModel

from atlas.agents import summarizer

ABSTRACT = "We present a deep reinforcement learning approach to playing Atari games."


def test_tldr_comes_from_the_structured_output():
    model = TestModel(custom_output_args={"tldr": "  Introduces DQN, which learns Atari from pixels.  "})
    with summarizer.agent.override(model=model):
        tldr = summarizer.summarize("Playing Atari with Deep RL", ABSTRACT)
    assert tldr == "Introduces DQN, which learns Atari from pixels."  # stripped


def test_blank_abstract_short_circuits_before_the_model():
    def explode(messages, info):
        raise AssertionError("the model must not be engaged for a blank abstract")

    with summarizer.agent.override(model=FunctionModel(explode)):
        assert summarizer.summarize("A Title", "") is None
        assert summarizer.summarize("A Title", "   ") is None


def test_model_failure_degrades_to_none():
    def boom(messages, info):
        raise RuntimeError("api down")

    with summarizer.agent.override(model=FunctionModel(boom)):
        assert summarizer.summarize("A Title", ABSTRACT) is None


def test_blocked_live_call_degrades_to_none():
    # No override: conftest's ALLOW_MODEL_REQUESTS=False makes the run raise
    # before any network — and summarize eats even that.
    assert summarizer.summarize("A Title", ABSTRACT) is None


def test_blank_output_degrades_to_none():
    model = TestModel(custom_output_args={"tldr": "   "})
    with summarizer.agent.override(model=model):
        assert summarizer.summarize("A Title", ABSTRACT) is None


def test_prompt_carries_title_and_abstract():
    seen = {}

    def record(messages, info):
        seen["prompt"] = messages[0].parts[-1].content
        raise RuntimeError("stop after recording")

    with summarizer.agent.override(model=FunctionModel(record)):
        assert summarizer.summarize("  Playing Atari  ", ABSTRACT) is None
    assert seen["prompt"] == f"Title: Playing Atari\n\nAbstract: {ABSTRACT}"


def test_untitled_papers_still_summarize():
    seen = {}

    def record(messages, info):
        seen["prompt"] = messages[0].parts[-1].content
        raise RuntimeError("stop after recording")

    with summarizer.agent.override(model=FunctionModel(record)):
        summarizer.summarize("", ABSTRACT)
    assert seen["prompt"].startswith("Title: (untitled)")
