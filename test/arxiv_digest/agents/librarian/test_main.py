"""The librarian: retrieval trace first, grounded streamed answer, the
no-hits path, and scope/history forwarding."""

from __future__ import annotations

from pydantic_ai.models.function import FunctionModel
from pydantic_ai.models.test import TestModel

from arxiv_digest.agents import events, librarian
from arxiv_digest.config import config

HITS = [
    {"source_id": "s1", "source_title": "Deep Learning", "page": 243, "text": "Momentum helps."},
    {"source_id": "s1", "source_title": "Deep Learning", "page": 12, "text": "Gradients flow."},
    {"source_id": "s2", "source_title": "A Web Page", "page": None, "text": "Regularization."},
]


def test_trace_then_streamed_tokens(monkeypatch):
    monkeypatch.setattr(librarian.main.sources, "search", lambda question, **kwargs: HITS)
    model = TestModel(custom_output_text="Momentum smooths updates.")
    with librarian.agent.override(model=model):
        out = list(librarian.answer("what is momentum?"))
    trace, *tokens = out
    assert trace == events.RetrievalTrace(found=3, sources=["Deep Learning", "A Web Page"])
    assert tokens and all(isinstance(token, events.Token) for token in tokens)
    assert "".join(token.text for token in tokens) == "Momentum smooths updates."


def test_no_hits_answers_without_engaging_the_model(monkeypatch):
    monkeypatch.setattr(librarian.main.sources, "search", lambda question, **kwargs: [])

    def explode(messages, info):
        raise AssertionError("the model must not be engaged when retrieval is empty")

    with librarian.agent.override(model=FunctionModel(explode)):
        out = list(librarian.answer("anything"))
    assert out[0] == events.RetrievalTrace(found=0, sources=[])
    assert out[1].text.startswith("I couldn't find anything")


def test_scope_and_chat_k_reach_retrieval(monkeypatch):
    seen = {}

    def fake_search(question, **kwargs):
        seen["question"], seen["kwargs"] = question, kwargs
        return []

    monkeypatch.setattr(librarian.main.sources, "search", fake_search)
    list(librarian.answer("q", source_ids=["s2"]))
    assert seen["question"] == "q"
    assert seen["kwargs"] == {
        "k": config.sources.retrieval.chat_k,
        "source_ids": ["s2"],
    }


def test_passages_and_history_reach_the_model(monkeypatch):
    monkeypatch.setattr(librarian.main.sources, "search", lambda question, **kwargs: HITS)
    seen = {}

    async def record(messages, info):
        seen["messages"] = messages
        yield "ok"

    turns = [
        {"role": "user", "content": "earlier question"},
        {"role": "assistant", "content": "earlier answer"},
    ]
    with librarian.agent.override(model=FunctionModel(stream_function=record)):
        list(librarian.answer("what is momentum?", history=turns))

    messages = seen["messages"]
    assert len(messages) == 3  # two history turns ride ahead of the new request
    prompt = messages[-1].parts[-1].content
    assert "[Deep Learning, p.243] Momentum helps." in prompt
    assert prompt.strip().endswith("Question: what is momentum?")
    # instructions= survives alongside message history (the house rule).
    assert messages[-1].instructions and "grounded ONLY" in messages[-1].instructions
