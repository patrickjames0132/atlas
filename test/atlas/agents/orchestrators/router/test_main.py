"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
The router: the no-model fast path claims only the phrasings that name a
lecture outright *and point at nothing in particular*, the model's decision
passes through untouched, every failure answers the question instead, and
the name resolver turns a message into graph ids without ever raising.

The most valuable assertions here are the *negative* ones. The fast path's
whole justification is that it is narrower than it could be — "summarize
this" and "walk me through X" are ambiguous and belong to the model, and
since v7.23.0 so is any lecture request that says *which* papers ("…on the
references"), because the scope is the half a regex cannot read — and
nothing about the code says so out loud. Widening the pattern is a one-line
change a later reader would find tempting, so the phrasings it must NOT
claim are pinned by name.

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
        "lecture me",
        "lecture me on these",
        "lecture us on this",
        "give me a lecture on these papers",
        "Can you lecture me on this?",
        "please give me the lecture",
        "lecture: everything",
        "   lecture me",
        "lecture me on the selected papers.",
        "lecture me about what I have on screen",
        "lecture me on all of these",
    ],
)
def test_naming_a_lecture_over_the_screen_needs_no_model(message):
    def explode(messages, info):
        raise AssertionError("the fast path must not engage the model")

    with router.agent.override(model=FunctionModel(explode)):
        decision = router.route(message)
    assert decision.target == "lecture"
    assert decision.scope == "screen"


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
        # Names a lecture — and names its SCOPE, which is the model's to read.
        # A keyword pattern could claim "the references"; it could not tell
        # "the papers that reference the seed" from it, so none of these are
        # claimed.
        "lecture me on the references",
        "Give me a lecture on the citations",
        "lecture me on the seed",
        "lecture me on this paper: Attention is all you need",
        "lecture me on these papers: BERT, GPT-2",
        "Lecture me about the attention papers",
        "lecture: transformers",
        "lecture me on the story of deep learning",
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
        ("lecture me on how we got here", "history"),
        ("lecture me on the selected papers", "summary"),
    ],
)
def test_the_fast_path_reads_the_framing_off_the_words(message, framing):
    assert router.obvious_route(message).framing == framing


def test_the_models_decision_is_passed_through():
    model = TestModel(
        custom_output_args={
            "target": "lecture",
            "framing": "history",
            "scope": "references",
            "year_from": 2010,
            "year_to": 2019,
        }
    )
    with router.agent.override(model=model):
        decision = router.route("how did the papers this one cites come together in the 2010s?")
    assert decision.target == "lecture"
    assert decision.framing == "history"
    assert decision.scope == "references"
    assert (decision.year_from, decision.year_to) == (2010, 2019)


def test_a_question_routed_to_the_researcher_stays_there():
    model = TestModel(custom_output_args={"target": "answer", "framing": "summary"})
    with router.agent.override(model=model):
        decision = router.route("what is attention?")
    assert decision.target == "answer"
    # The scope and years default rather than being demanded: a model that
    # omits them on an answer has said nothing wrong.
    assert decision.scope == "screen"
    assert decision.year_from is None and decision.year_to is None


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
    message, _, footer = seen[0].partition("\n\n")
    assert len(message) == 600
    # The date rides along after the cut, so "the last five years" has a
    # "today" to count back from however long the message is.
    assert footer.startswith("(Today's date: ")


PAPERS = [
    router.RoutePaper(id="p1", title="Black holes and entropy", year=1973, authors="J. Bekenstein"),
    router.RoutePaper(id="p2", title="Particle creation by black holes", year=1975, authors="S. Hawking, X"),
    router.RoutePaper(id="p3", title="The four laws of black hole mechanics", year=1973, authors=None),
]


class TestResolvePapers:
    """The named-scope resolver: indices in, ids out, and nothing ever raises."""

    def test_the_models_picks_come_back_as_ids_in_its_order(self):
        model = TestModel(custom_output_args={"indices": [2, 1]})
        with router.resolve_agent.override(model=model):
            ids = router.resolve_papers("lecture me on Hawking 1975 and the Bekenstein paper", PAPERS)
        assert ids == ["p2", "p1"]

    def test_the_prompt_lists_every_paper_by_title_author_and_year(self):
        seen: list[str] = []

        def capture(messages, info):
            seen.append(messages[-1].parts[-1].content)
            raise RuntimeError("enough")

        with router.resolve_agent.override(model=FunctionModel(capture)):
            router.resolve_papers("lecture me on the Bekenstein paper", PAPERS)
        prompt = seen[0]
        assert "Message: lecture me on the Bekenstein paper" in prompt
        assert "[1] Black holes and entropy (J. Bekenstein, 1973)" in prompt
        # First author only, and a missing author/year says so rather than
        # rendering "None".
        assert "[2] Particle creation by black holes (S. Hawking, 1975)" in prompt
        assert "[3] The four laws of black hole mechanics (unknown, 1973)" in prompt

    def test_hallucinated_and_repeated_indices_are_dropped(self):
        model = TestModel(custom_output_args={"indices": [3, 0, 9, 3, -1]})
        with router.resolve_agent.override(model=model):
            assert router.resolve_papers("lecture me on the four laws", PAPERS) == ["p3"]

    def test_model_failure_matches_nothing_rather_than_raising(self):
        def boom(messages, info):
            raise RuntimeError("api down")

        with router.resolve_agent.override(model=FunctionModel(boom)):
            assert router.resolve_papers("lecture me on BERT", PAPERS) == []

    @pytest.mark.parametrize("message, papers", [("", PAPERS), ("   ", PAPERS), ("BERT", [])])
    def test_nothing_to_resolve_skips_the_model(self, message, papers):
        def explode(messages, info):
            raise AssertionError("nothing to match must not be billed")

        with router.resolve_agent.override(model=FunctionModel(explode)):
            assert router.resolve_papers(message, papers) == []

    def test_the_paper_list_is_bounded(self):
        seen: list[str] = []

        def capture(messages, info):
            seen.append(messages[-1].parts[-1].content)
            raise RuntimeError("enough")

        many = [router.RoutePaper(id=f"p{index}", title=f"Paper {index}") for index in range(700)]
        with router.resolve_agent.override(model=FunctionModel(capture)):
            router.resolve_papers("lecture me on Paper 3", many)
        assert "[500] Paper 499" in seen[0]
        assert "[501]" not in seen[0]
