"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
The router: the no-model fast path claims only the phrasings that name a
lecture outright, the model's decision passes through untouched, and every
failure answers the question instead.

The most valuable assertions here are the *negative* ones. The fast path's
whole justification is that it is narrower than it could be — "summarize
this" and "walk me through X" are ambiguous and belong to the model — and
nothing about the code says so out loud. Widening the pattern is a one-line
change a later reader would find tempting, so the phrasings it must NOT claim
are pinned by name.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

import pytest
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.models.test import TestModel

from atlas.agents.orchestrators import router


@pytest.mark.parametrize(
    "message",
    [
        "lecture me on these",
        "Lecture me about the attention papers",
        "lecture us on this",
        "give me a lecture on these papers",
        "Can you lecture me on this?",
        "please give me the lecture",
        "lecture: transformers",
        "   lecture me",
    ],
)
def test_naming_a_lecture_needs_no_model(message):
    def explode(messages, info):
        raise AssertionError("the fast path must not engage the model")

    with router.agent.override(model=FunctionModel(explode)):
        assert router.route(message).target == "lecture"


@pytest.mark.parametrize(
    "message",
    [
        # Means the scoped papers about half the time and "your last answer"
        # the other half. Only the conversation says which — so the model,
        # which sees the message, decides rather than a regex.
        "summarize this",
        "summarize these papers",
        # As likely a question about the mechanism as a request to be taught
        # the literature about it.
        "walk me through attention",
        "teach me about transformers",
        # Contains the word, but is a question ABOUT a lecture, not a request
        # for one.
        "what did the lecture say about ResNet?",
        "why is the lecture ordered that way",
        # Plain questions, which must reach the classifier unclaimed.
        "what is a transformer",
        "which of these papers introduced layer norm?",
    ],
)
def test_the_fast_path_leaves_the_ambiguous_cases_to_the_model(message):
    # `obvious_route` — not `route`, whose fallback would hide a match.
    assert router.obvious_route(message) is None


@pytest.mark.parametrize(
    "message, framing",
    [
        ("lecture me on these", "summary"),
        ("lecture me on the history of these papers", "history"),
        ("lecture me on how this field evolved", "history"),
        ("lecture me on the story of deep learning", "history"),
        ("lecture me on how we got here", "history"),
        ("lecture me on what these papers cover", "summary"),
    ],
)
def test_the_fast_path_reads_the_framing_off_the_words(message, framing):
    assert router.obvious_route(message).framing == framing


def test_the_models_decision_is_passed_through():
    model = TestModel(custom_output_args={"target": "lecture", "framing": "history"})
    with router.agent.override(model=model):
        decision = router.route("how did this whole area come together?")
    assert decision.target == "lecture"
    assert decision.framing == "history"


def test_a_question_routed_to_the_researcher_stays_there():
    model = TestModel(custom_output_args={"target": "answer", "framing": "summary"})
    with router.agent.override(model=model):
        assert router.route("what is attention?").target == "answer"


def test_model_failure_answers_rather_than_raising():
    def boom(messages, info):
        raise RuntimeError("api down")

    with router.agent.override(model=FunctionModel(boom)):
        assert router.route("how did this area come together?") == router.ANSWER


def test_blocked_live_call_answers():
    # No override: conftest's ALLOW_MODEL_REQUESTS=False makes the run raise
    # before any network reaches out, and `route` eats even that.
    assert router.route("how did this area come together?") == router.ANSWER


@pytest.mark.parametrize("message", ["", "   ", None])
def test_an_empty_message_answers_without_a_model(message):
    def explode(messages, info):
        raise AssertionError("an empty message must not be classified")

    with router.agent.override(model=FunctionModel(explode)):
        assert router.route(message) == router.ANSWER


def test_a_long_message_is_truncated_before_billing_for_it():
    seen: list[str] = []

    def capture(messages, info):
        seen.append(messages[-1].parts[-1].content)
        raise RuntimeError("enough")

    with router.agent.override(model=FunctionModel(capture)):
        router.route("why " + "x" * 5000)
    assert len(seen[0]) == 600
