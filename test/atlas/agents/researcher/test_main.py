"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
The tutor: live traces and discoveries while it works, streamed answer
tokens from the structured output, cited as reads + named indices, budget
exhaustion steering, and the library-gated source tool.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

import json

from pydantic_ai.models.function import DeltaToolCall, FunctionModel

from atlas.agents import events, researcher
from atlas.agents.models import PlayedBeat, PlayedLecture
from atlas.agents.researcher import config as researcher_config
from atlas.services.graph import Node


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


SEED = make_node("seed01", "Playing Atari with Deep RL", is_seed=True, rels=[],
                 arxiv_id="1312.5602", abstract="We present DQN.", tldr="DQN works.")
NODES = [
    SEED,
    make_node("node02", "Q-learning", year=1992, abstract="Q-learning proof.", tldr="Q converges."),
    make_node("node03", "TD Learning", year=1988, abstract="TD intro."),
]


def scripted(*turns, seen: dict | None = None) -> FunctionModel:
    """A model that streams the given tool calls, one `turns` entry per model
    request. Each entry is [(tool_name, args_json_chunks), ...]."""
    state = {"turn": 0}

    async def stream(messages, info):
        if seen is not None:
            seen.setdefault("turns", []).append(messages)
            seen["tools"] = [tool.name for tool in info.function_tools]
        calls = turns[state["turn"]]
        state["turn"] += 1
        for index, (name, chunks) in enumerate(calls):
            yield {index: DeltaToolCall(name=name, json_args=chunks[0])}
            for chunk in chunks[1:]:
                yield {index: DeltaToolCall(json_args=chunk)}

    return FunctionModel(stream_function=stream)


def final(text: str, cited: list[int], kind: str = "answered") -> tuple[str, list[str]]:
    """One scripted final_result call.

    ``kind`` defaults to ``answered``; the tests that exercise the
    look-before-you-answer guard set it explicitly.
    """
    return ("final_result", [json.dumps({"kind": kind, "text": text, "cited": cited})])


def run(model, monkeypatch, library=None, **kwargs) -> list:
    monkeypatch.setattr(researcher.main.store, "list_sources", lambda: library or [])
    with researcher.agent.override(model=model):
        return list(researcher.answer("why does this work?", SEED, NODES, **kwargs))


def cited_of(out: list) -> events.Cited:
    """The run's single Cited event.

    Args:
        out: The event stream the run produced.

    Returns:
        The Cited event.
    """
    return next(event for event in out if isinstance(event, events.Cited))


def provenance_of(out: list) -> events.Provenance:
    """The run's single Provenance event.

    Args:
        out: The event stream the run produced.

    Returns:
        The Provenance event.
    """
    return next(event for event in out if isinstance(event, events.Provenance))


def test_answer_streams_token_deltas_and_maps_cited(monkeypatch):
    model = scripted(
        [
            (
                "final_result",
                ['{"kind": "answered", "text": "Momentum smooths', ' updates.", "cited": [2]}'],
            )
        ]
    )
    out = run(model, monkeypatch)
    tokens = [event for event in out if isinstance(event, events.Token)]
    assert "".join(token.text for token in tokens) == "Momentum smooths updates."
    assert len(tokens) >= 2  # streamed as the args JSON grew, not one lump
    assert cited_of(out) == events.Cited(node_ids=["node02"])


def test_read_traces_live_and_joins_cited(monkeypatch):
    seen: dict = {}
    model = scripted(
        [("read_paper", ['{"index": 2, "detail": "summary"}'])],
        [final("Q-learning proves convergence.", [3])],
        seen=seen,
    )
    out = run(model, monkeypatch)
    trace = next(event for event in out if isinstance(event, events.ReadTrace))
    assert trace == events.ReadTrace(ok=True, index=2, title="Q-learning", detail="summary")
    # The read's text reached the model as the tool result.
    returns = [part for part in seen["turns"][1][-1].parts if part.part_kind == "tool-return"]
    assert "TL;DR: Q converges." in returns[0].content
    # Cited = the paper actually read first, then the one it named.
    assert cited_of(out) == events.Cited(node_ids=["node02", "node03"])


def test_expand_discovers_numbers_and_directs_edges(monkeypatch):
    hits = [
        {"node": dict(id="anc01", arxiv_id=None, title="Bellman 1957", abstract=None,
                      tldr=None, year=1957, month=None, pub_date=None,
                      citation_count=50000, authors=None, url="https://example.org/anc01"),
         "influential": True},
        {"node": dict(id="node03", arxiv_id=None, title="TD Learning", abstract=None,
                      tldr=None, year=1988, month=None, pub_date=None,
                      citation_count=1, authors=None, url="https://example.org/node03")},
    ]
    monkeypatch.setattr(
        researcher.tools.traversal, "neighbors",
        lambda paper_id, relation, limit, provider="s2": hits,
    )
    model = scripted(
        [("expand_node", ['{"index": 1, "relation": "references"}'])],
        [final("It rests on Bellman.", [4])],
    )
    out = run(model, monkeypatch)
    trace = next(event for event in out if isinstance(event, events.ExpandTrace))
    assert trace.found == 1  # node03 was already on the graph
    discovery = next(event for event in out if isinstance(event, events.Discovery))
    assert [node.id for node in discovery.nodes] == ["anc01"]
    assert discovery.nodes[0].idx == 4 and discovery.nodes[0].discovered is True
    # reference edges point expanded paper -> neighbor; both hits carry edges.
    assert [(edge.source, edge.target, edge.type) for edge in discovery.edges] == [
        ("seed01", "anc01", "reference"),
        ("seed01", "node03", "reference"),
    ]
    # Only reads record citations; the model named [4] -> the discovered paper.
    assert cited_of(out) == events.Cited(node_ids=["anc01"])


def test_expand_uses_the_selected_provider(monkeypatch):
    """answer(provider=…) reaches the tools: expand_node hops through the chosen
    provider, not always S2."""
    seen: dict = {}

    def fake_neighbors(paper_id, relation, limit, provider="s2"):
        seen["provider"] = provider
        return []

    monkeypatch.setattr(researcher.tools.traversal, "neighbors", fake_neighbors)
    model = scripted(
        [("expand_node", ['{"index": 1, "relation": "references"}'])],
        [final("ok", [])],
    )
    run(model, monkeypatch, provider="openalex")
    assert seen["provider"] == "openalex"


def test_search_sources_offered_only_with_a_library(monkeypatch):
    for library, expected in [
        (None, False),
        ([{"id": "s1", "title": "Deep Learning", "kind": "pdf", "pages": 800}], True),
    ]:
        seen: dict = {}
        model = scripted([final("ok", [], kind="conversational")], seen=seen)
        run(model, monkeypatch, library=library)
        assert ("search_sources" in seen["tools"]) is expected


def test_user_scope_overrides_the_models_source_pick(monkeypatch):
    calls: dict = {}

    def spy(query, **kwargs):
        calls["kwargs"] = kwargs
        return []

    monkeypatch.setattr(researcher.tools.retrieval, "search", spy)
    library = [
        {"id": "s1", "title": "Deep Learning", "kind": "pdf", "pages": 800},
        {"id": "s2", "title": "RL Book", "kind": "pdf", "pages": 500},
    ]
    model = scripted(
        [("search_sources", ['{"query": "momentum", "source": 1}'])],
        [final("Not in your sources.", [])],
    )
    run(model, monkeypatch, library=library, source_ids=["s2"])
    assert calls["kwargs"]["source_ids"] == ["s2"]  # the model asked for s1; scope wins


def test_step_budget_steers_the_model_to_answer(monkeypatch):
    monkeypatch.setitem(researcher_config.BUDGETS, "max_steps", 1)
    seen: dict = {}
    model = scripted(
        [
            ("read_paper", ['{"index": 2, "detail": "summary"}']),
            ("read_paper", ['{"index": 3, "detail": "summary"}']),
        ],
        [final("Answering with what I have.", [])],
        seen=seen,
    )
    out = run(model, monkeypatch)
    traces = [event for event in out if isinstance(event, events.ReadTrace)]
    assert [trace.ok for trace in traces] == [True, False]
    returns = [part for part in seen["turns"][1][-1].parts if part.part_kind == "tool-return"]
    assert researcher.tools.STEPS_EXHAUSTED in returns[1].content


def test_search_budget_exhausted_is_distinguished_from_an_error(monkeypatch):
    monkeypatch.setitem(researcher_config.BUDGETS, "searches", 1)
    monkeypatch.setattr(researcher.tools.traversal, "search", lambda *args, **kwargs: [])
    model = scripted(
        [
            ("search_papers", ['{"query": "momentum methods"}']),
            ("search_papers", ['{"query": "second order optimizers"}']),
        ],
        [final("Answering with what I have.", [])],
    )
    out = run(model, monkeypatch)
    traces = [event for event in out if isinstance(event, events.SearchTrace)]
    assert [(trace.ok, trace.reason) for trace in traces] == [
        (True, None),
        (False, "budget_exhausted"),
    ]


def test_show_figure_attaches_with_proxy_url_and_slot(monkeypatch):
    monkeypatch.setattr(
        researcher.tools.figures_mod,
        "get_figures",
        lambda arxiv_id: {"figures": [{"image": "https://ar5iv.org/f1.png", "caption": "The net"}]},
    )
    model = scripted(
        [("show_figure", ['{"index": 1, "figure": 1}'])],
        [final("As the figure shows. <<FIG 1>>", [1])],
    )
    out = run(model, monkeypatch)
    figure = next(event for event in out if isinstance(event, events.Figure))
    assert figure.image == "/api/figure_proxy?src=https%3A%2F%2Far5iv.org%2Ff1.png"
    assert figure.slot == 1 and figure.title == "Playing Atari with Deep RL"
    trace = next(event for event in out if isinstance(event, events.FigureTrace))
    assert trace.ok is True


def _first_user_prompt(messages) -> str:
    """The user-prompt text of the first request the model saw."""
    for message in messages:
        for part in getattr(message, "parts", []):
            if getattr(part, "part_kind", None) == "user-prompt":
                return part.content
    return ""


def test_played_lectures_enter_the_prompt(monkeypatch):
    seen: dict = {}
    model = scripted([final("Attention replaced recurrence, as the lecture said.", [])], seen=seen)
    lectures = [
        PlayedLecture(
            title="How we got here",
            beats=[PlayedBeat(heading="The RNN era", text="Sequence models leaned on recurrence.")],
        )
    ]
    run(model, monkeypatch, lectures=lectures)
    prompt = _first_user_prompt(seen["turns"][0])
    assert "Lectures already delivered" in prompt
    assert "How we got here" in prompt
    assert "Sequence models leaned on recurrence." in prompt


def test_no_lectures_adds_no_lecture_block(monkeypatch):
    seen: dict = {}
    model = scripted([final("ok", [])], seen=seen)
    run(model, monkeypatch)  # no lectures kwarg
    assert "Lectures already delivered" not in _first_user_prompt(seen["turns"][0])


def test_lectures_context_respects_the_char_budget(monkeypatch):
    # A tiny budget: the first lecture alone overflows, so it's truncated with an
    # ellipsis and every later lecture is dropped.
    monkeypatch.setattr(researcher.main, "_LECTURES_MAX_CHARS", 50)
    lectures = [
        PlayedLecture(title="First", beats=[PlayedBeat(heading="h", text="x" * 200)]),
        PlayedLecture(title="Second", beats=[PlayedBeat(heading="h", text="y" * 200)]),
    ]
    out = researcher.main._lectures_context(lectures)
    assert out.endswith("…")
    assert "Second" not in out


def test_show_source_figure_attaches_a_library_figure(monkeypatch):
    """The library twin of show_figure: page-addressed, image served by the
    sources figure route, no numbered-paper index."""
    monkeypatch.setattr(
        researcher.tools.library_figures.source_figures.store,
        "get_source",
        lambda source_id: {"id": source_id, "title": "My Textbook", "kind": "pdf", "pages": 300},
    )
    monkeypatch.setattr(
        researcher.tools.library_figures.source_figures,
        "get_source_figures",
        lambda source_id: {
            "available": True,
            "floats": [
                {"kind": "table", "page": 3, "caption": "Table 1: Setup.", "region": [0, 0, 1, 1]},
                {"kind": "figure", "page": 12, "caption": "Figure 3.1: Backprop.",
                 "region": [0, 0, 1, 1]},
            ],
        },
    )
    library = [{"id": "src1", "title": "My Textbook", "kind": "pdf", "pages": 300}]
    model = scripted(
        [("search_sources", ['{"query": "x"}'])],
        [("show_source_figure", ['{"source": 1, "page": 12}'])],
        [final("See the book's figure. <<FIG 1>>", [])],
    )
    out = run(model, monkeypatch, library=library)
    figure = next(event for event in out if isinstance(event, events.Figure))
    # Manifest index 1 (the page-12 float), served by the sources route.
    assert figure.image == "/api/sources/src1/figure/1"
    assert figure.index is None and figure.title == "My Textbook"
    # The designation splits off as `label`; the caption keeps the rest.
    assert figure.label == "Figure 3.1" and figure.caption == "Backprop."
    trace = next(event for event in out if isinstance(event, events.FigureTrace))
    assert trace.ok is True and trace.index is None


def test_show_source_figure_wrong_page_reports_figure_pages(monkeypatch):
    monkeypatch.setattr(
        researcher.tools.library_figures.source_figures.store,
        "get_source",
        lambda source_id: {"id": source_id, "title": "My Textbook", "kind": "pdf", "pages": 300},
    )
    monkeypatch.setattr(
        researcher.tools.library_figures.source_figures,
        "get_source_figures",
        lambda source_id: {
            "available": True,
            "floats": [
                {"kind": "figure", "page": 12, "caption": "Figure 3.1.", "region": [0, 0, 1, 1]},
            ],
        },
    )
    library = [{"id": "src1", "title": "My Textbook", "kind": "pdf", "pages": 300}]
    seen: dict = {}
    model = scripted(
        [("search_sources", ['{"query": "x"}'])],
        [("show_source_figure", ['{"source": 1, "page": 5}'])],
        [final("No figure then.", [])],
        seen=seen,
    )
    out = run(model, monkeypatch, library=library)
    trace = next(event for event in out if isinstance(event, events.FigureTrace))
    assert trace.ok is False
    assert not any(isinstance(event, events.Figure) for event in out)


def test_show_source_figure_gated_on_the_library(monkeypatch):
    """No library, no tool — same prepare gate as search_sources."""
    seen: dict = {}
    model = scripted([final("done", [], kind="conversational")], seen=seen)
    run(model, monkeypatch, library=None)
    assert "show_source_figure" not in seen["tools"]

    seen_with: dict = {}
    model = scripted([final("done", [], kind="conversational")], seen=seen_with)
    run(model, monkeypatch, library=[{"id": "s", "title": "T", "kind": "pdf", "pages": 1}])
    assert "show_source_figure" in seen_with["tools"]


def test_library_index_precedes_the_prose(monkeypatch):
    """The [Sn] map is emitted before any token, so a marker renders as a real
    title while the answer is still streaming (not after it lands, like Cited).
    """
    library = [
        {"id": "src1", "title": "My Textbook", "kind": "pdf", "pages": 300},
        {"id": "src2", "title": "A Web Page", "kind": "url"},
    ]
    model = scripted([final("Grounded [S1, p.12].", [], kind="conversational")])
    out = run(model, monkeypatch, library=library)
    assert out[0] == events.SourceRefs(
        refs={
            "1": events.SourceRef(source_id="src1", title="My Textbook"),
            "2": events.SourceRef(source_id="src2", title="A Web Page"),
        }
    )


def test_no_library_index_without_a_library(monkeypatch):
    out = run(scripted([final("ok", [])]), monkeypatch, library=None)
    assert not any(isinstance(event, events.SourceRefs) for event in out)


def test_prompt_numbers_the_library_and_hides_ids(monkeypatch):
    seen: dict = {}
    library = [{"id": "src-hex-id", "title": "My Textbook", "kind": "pdf", "pages": 300}]
    run(
        scripted([final("ok", [], kind="conversational")], seen=seen),
        monkeypatch,
        library=library,
    )
    prompt = seen["turns"][0][-1].parts[-1].content
    assert '[S1] "My Textbook" (300pp)' in prompt
    # The id is what the model must never see — an index is the only token it
    # can reproduce exactly (see prompts.source_lines).
    assert "src-hex-id" not in prompt


def test_out_of_range_source_number_comes_back_as_text(monkeypatch):
    """A hallucinated [Sn] is steerable information, never a raise — the house
    rule for every researcher tool."""
    library = [{"id": "src1", "title": "My Textbook", "kind": "pdf", "pages": 300}]
    model = scripted(
        [("search_sources", ['{"query": "momentum", "source": 9}'])],
        # The bad index never reached retrieval, so the guard is still unmet —
        # the model lands this turn conversationally rather than claiming an
        # answer it never looked for.
        [final("Couldn't find it.", [], kind="conversational")],
    )
    out = run(model, monkeypatch, library=library)
    trace = next(
        event
        for event in out
        if isinstance(event, events.SourceSearchTrace) and not event.ok
    )
    assert trace.query == "momentum"


# --- look before you answer -------------------------------------------------
#
# The guard that replaces the librarian's grounding-by-construction. When
# retrieval ran before the model, it could not answer without the passages;
# as a tool it can skip them and answer from memory, which a student would
# reasonably mistake for their own book talking.

LIBRARY = [{"id": "src1", "title": "My Textbook", "kind": "pdf", "pages": 300}]


def test_answering_without_searching_an_available_library_is_retried(monkeypatch):
    monkeypatch.setattr(researcher.tools.retrieval, "search", lambda query, **kwargs: [])
    model = scripted(
        [final("Momentum smooths updates.", [])],  # skipped the library
        [("search_sources", ['{"query": "momentum"}'])],  # bounced, so it looks
        [final("Your library has nothing on it, but: momentum smooths.", [])],
    )
    out = run(model, monkeypatch, library=LIBRARY)
    prose = "".join(event.text for event in out if isinstance(event, events.Token))
    assert prose == "Your library has nothing on it, but: momentum smooths."
    assert provenance_of(out).searches == 1


def test_the_retried_answer_never_reaches_the_stream(monkeypatch):
    """The rejected attempt must not stream and then be replaced on screen —
    prose is withheld until the attempt is known-good (see `_doomed`)."""
    monkeypatch.setattr(researcher.tools.retrieval, "search", lambda query, **kwargs: [])
    model = scripted(
        [final("WRONG: answered from memory.", [])],
        [("search_sources", ['{"query": "q"}'])],
        [final("Right answer.", [])],
    )
    out = run(model, monkeypatch, library=LIBRARY)
    prose = "".join(event.text for event in out if isinstance(event, events.Token))
    assert "WRONG" not in prose
    assert prose == "Right answer."


def test_an_empty_search_satisfies_the_guard(monkeypatch):
    """The rule is that the library was *consulted*, not that it helped —
    otherwise an empty library would make every answer unreachable."""
    monkeypatch.setattr(researcher.tools.retrieval, "search", lambda query, **kwargs: [])
    model = scripted(
        [("search_sources", ['{"query": "momentum"}'])],
        [final("Nothing in your library covers it.", [])],
    )
    out = run(model, monkeypatch, library=LIBRARY)
    assert "Nothing in your library" in "".join(
        event.text for event in out if isinstance(event, events.Token)
    )
    provenance = provenance_of(out)
    assert provenance.searches == 1 and provenance.passages == 0


def test_a_conversational_turn_never_searches(monkeypatch):
    """Saying hello is not a research question. This is the whole point of the
    ticket: the librarian searched the student's books to answer "hi"."""

    def explode(query, **kwargs):
        raise AssertionError("a greeting must not search the library")

    monkeypatch.setattr(researcher.tools.retrieval, "search", explode)
    model = scripted([final("Hi! What are you working on?", [], kind="conversational")])
    out = run(model, monkeypatch, library=LIBRARY)
    assert not any(isinstance(event, events.SourceSearchTrace) for event in out)
    assert provenance_of(out).searches == 0


def test_no_library_means_no_guard(monkeypatch):
    """Nothing to look in — search_sources isn't even registered."""
    model = scripted([final("From what I know: momentum smooths.", [])])
    out = run(model, monkeypatch, library=None)
    assert provenance_of(out) == events.Provenance(
        kind="answered", had_library=False, searches=0, passages=0,
        paper_searches=0, cited_sources=0, cited_papers=0,
    )


# --- graph-free mode --------------------------------------------------------


def test_answers_with_no_seed_or_nodes(monkeypatch):
    """The path the librarian used to own — the researcher with an empty
    numbered list."""
    seen: dict = {}
    model = scripted([final("Happy to help.", [], kind="conversational")], seen=seen)
    monkeypatch.setattr(researcher.main.store, "list_sources", lambda: [])
    with researcher.agent.override(model=model):
        out = list(researcher.answer("what can you do?"))
    prose = "".join(event.text for event in out if isinstance(event, events.Token))
    assert prose == "Happy to help."
    prompt = seen["turns"][0][-1].parts[-1].content
    assert "No citation graph is open" in prompt
    assert "SEED paper" not in prompt


def test_provenance_counts_what_the_prose_cites(monkeypatch):
    monkeypatch.setattr(
        researcher.tools.retrieval,
        "search",
        lambda query, **kwargs: [
            {"source_id": "src1", "source_title": "My Textbook", "page": 12, "text": "Momentum."}
        ],
    )
    model = scripted(
        [("search_sources", ['{"query": "momentum"}'])],
        [final("Your book covers it [S1, p.12], and so does [1].", [1])],
    )
    out = run(model, monkeypatch, library=LIBRARY)
    provenance = provenance_of(out)
    assert provenance.had_library is True
    assert provenance.searches == 1 and provenance.passages == 1
    # Counted off the finished prose, not the model's say-so.
    assert provenance.cited_sources == 1
    assert provenance.cited_papers == 1


def test_paper_refs_resolve_the_markers_the_prose_used(monkeypatch):
    """With no graph the frontend holds no numbered list, so [n] can only be
    resolved server-side — otherwise it renders as dead text."""
    model = scripted([final("As shown in [2], and [9] is out of range.", [])])
    out = run(model, monkeypatch)
    refs = next(event for event in out if isinstance(event, events.PaperRefs)).refs
    assert set(refs) == {"2"}  # the hallucinated index is dropped
    assert refs["2"].node_id == "node02"
    assert refs["2"].title == "Q-learning"


def test_paper_refs_carry_the_backend_that_minted_the_ids(monkeypatch):
    """A node id resolves only in the provider that issued it, so the reference
    carries its own — the click that maps it has nothing else to go on once the
    dropdown has moved on."""
    model = scripted([final("As shown in [2].", [])])
    out = run(model, monkeypatch, provider="openalex")
    refs = next(event for event in out if isinstance(event, events.PaperRefs)).refs
    assert refs["2"].provider == "openalex"


def test_no_paper_refs_when_the_prose_cites_nothing(monkeypatch):
    out = run(scripted([final("No papers needed.", [])]), monkeypatch)
    assert not any(isinstance(event, events.PaperRefs) for event in out)


def test_provenance_carries_the_models_own_classification(monkeypatch):
    """The one self-reported field on Provenance, carried so a `conversational`
    turn that skipped the library can be checked against what it produced —
    the loophole the output guard can't close from the inside."""
    model = scripted([final("The Odyssey is an epic poem.", [], kind="conversational")])
    out = run(model, monkeypatch, library=LIBRARY)
    provenance = provenance_of(out)
    assert provenance.kind == "conversational"
    assert provenance.had_library is True and provenance.searches == 0


def test_provenance_counts_paper_searches_separately(monkeypatch):
    """A trip to Semantic Scholar and an answer written from the model's own
    weights are very different things to report — and were indistinguishable
    until paper searches were counted."""
    monkeypatch.setattr(
        researcher.tools.traversal,
        "search",
        lambda query, limit, year_from, year_to, provider: [],
    )
    model = scripted(
        [("search_papers", ['{"query": "black holes"}'])],
        [final("Nothing turned up; here is what I know.", [])],
    )
    out = run(model, monkeypatch, library=None)
    provenance = provenance_of(out)
    assert provenance.paper_searches == 1
    assert provenance.searches == 0  # library searches stay their own count
