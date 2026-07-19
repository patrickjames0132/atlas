"""The librarian: retrieval trace first, grounded streamed answer, the
no-hits path, and scope/history forwarding."""

from __future__ import annotations

from pydantic_ai.models.function import DeltaToolCall, FunctionModel
from pydantic_ai.models.test import TestModel

from atlas.agents import events, librarian
from atlas.config import config

HITS = [
    {"source_id": "s1", "source_title": "Deep Learning", "page": 243, "text": "Momentum helps."},
    {"source_id": "s1", "source_title": "Deep Learning", "page": 12, "text": "Gradients flow."},
    {"source_id": "s2", "source_title": "A Web Page", "page": None, "text": "Regularization."},
]


def test_trace_then_streamed_tokens(monkeypatch):
    monkeypatch.setattr(librarian.main.sources, "search", lambda question, **kwargs: HITS)
    # call_tools=[]: TestModel would otherwise call show_source_figure with
    # schema-junk args before answering; this test is about the text path.
    model = TestModel(call_tools=[], custom_output_args={"text": "Momentum smooths updates."})
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
        "top_k": config.sources.retrieval.chat_k,
        "source_ids": ["s2"],
    }


def test_passages_and_history_reach_the_model(monkeypatch):
    monkeypatch.setattr(librarian.main.sources, "search", lambda question, **kwargs: HITS)
    seen = {}

    async def record(messages, info):
        seen["messages"] = messages
        yield {0: DeltaToolCall(name="final_result", json_args='{"text": "ok"}')}

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


def test_prompt_lists_source_ids_for_figures(monkeypatch):
    """The passage block is followed by an id → title map so the model can
    address show_source_figure (passages themselves cite by title+page)."""
    monkeypatch.setattr(librarian.main.sources, "search", lambda question, **kwargs: HITS)
    seen = {}

    async def record(messages, info):
        seen["messages"] = messages
        seen["tools"] = [tool.name for tool in info.function_tools]
        yield {0: DeltaToolCall(name="final_result", json_args='{"text": "ok"}')}

    with librarian.agent.override(model=FunctionModel(stream_function=record)):
        list(librarian.answer("q"))
    prompt = seen["messages"][-1].parts[-1].content
    assert '- [s1] "Deep Learning"' in prompt and '- [s2] "A Web Page"' in prompt
    assert seen["tools"] == ["show_source_figure"]


def test_show_source_figure_attaches_and_narration_is_suppressed(monkeypatch):
    """A tool turn's narration text never streams; the Figure event carries
    the sources image URL; the final answer's tokens stream normally."""
    monkeypatch.setattr(librarian.main.sources, "search", lambda question, **kwargs: HITS)
    monkeypatch.setattr(
        librarian.tools.library_figures.source_figures.store,
        "get_source",
        lambda source_id: {"id": source_id, "title": "Deep Learning", "kind": "pdf", "pages": 700},
    )
    monkeypatch.setattr(
        librarian.tools.library_figures.source_figures,
        "get_source_figures",
        lambda source_id: {
            "available": True,
            "floats": [
                {"kind": "figure", "page": 243, "caption": "Figure 8.5: Momentum paths.",
                 "region": [0, 0, 1, 1]},
            ],
        },
    )
    state = {"turn": 0}

    async def stream(messages, info):
        state["turn"] += 1
        if state["turn"] == 1:
            yield "Let me pull that figure. "  # narration — must NOT stream
            yield {0: DeltaToolCall(name="show_source_figure",
                                    json_args='{"source_id": "s1", "page": 243}')}
        else:
            yield {0: DeltaToolCall(name="final_result",
                                    json_args='{"text": "See the momentum figure. ')}
            yield {0: DeltaToolCall(json_args='<<FIG 1>>"}')}

    with librarian.agent.override(model=FunctionModel(stream_function=stream)):
        out = list(librarian.answer("show me momentum"))

    figure = next(event for event in out if isinstance(event, events.Figure))
    assert figure.image == "/api/sources/s1/figure/0"
    assert figure.index is None and figure.title == "Deep Learning"
    assert figure.slot == 1
    text = "".join(event.text for event in out if isinstance(event, events.Token))
    assert text == "See the momentum figure. <<FIG 1>>"  # no tool-turn narration
