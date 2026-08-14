"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
Model-input parts: skill loading, passage rendering, and history
conversion. (Joining the parts into one prompt is PydanticAI's job — agents
pass ``instructions=[SYSTEM_PROMPT, *skills]`` and it joins with blank
lines.)

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

import pytest
from pydantic_ai.messages import ModelRequest, ModelResponse

from atlas.agents import prompts
from atlas.services.graph import Node


def test_skill_loads_prompt_ready_markdown():
    assert prompts.skill("teaching-voice").startswith("# Teaching voice")


def test_unknown_skill_fails_loudly():
    with pytest.raises(FileNotFoundError):
        prompts.skill("no-such-skill")


def make_node(node_id: str, **overrides) -> Node:
    fields = dict(
        id=node_id,
        arxiv_id=None,
        title="A Paper",
        abstract=None,
        tldr=None,
        year=2015,
        month=None,
        pub_date=None,
        citation_count=None,
        authors=None,
        url=f"https://example.org/{node_id}",
        rels=["reference"],
        is_seed=False,
    )
    fields.update(overrides)
    return Node(**fields)


def test_node_lines_numbers_by_position():
    nodes = [
        make_node("a", title="Old Root", year=1988, citation_count=50000, tldr="TD\nlearning."),
        make_node("b", title="No Year", year=None, rels=[]),
    ]
    lines = prompts.node_lines(nodes).splitlines()
    assert lines[0] == "[1] (1988, 50000 citations; reference) Old Root — TD learning."
    assert lines[1] == "[2] (n.d.; ?) No Year"


def test_node_lines_truncates_long_summaries():
    nodes = [make_node("a", abstract="x" * 500)]
    line = prompts.node_lines(nodes)
    assert len(line) < 400 and line.endswith("x")


def test_node_lines_by_era_bands_by_year_keeping_positional_numbers():
    # Oldest-first (as the orchestrator hands them); the numbers still come from
    # list position, so idx_to_id stays valid, and era headers split the range.
    nodes = [
        make_node("a", title="Roots", year=1990),
        make_node("b", title="Middle", year=2004),
        make_node("c", title="Recent", year=2018),
    ]
    lines = prompts.node_lines_by_era(nodes).splitlines()
    # 1990–2018 span, width 10: three era bands, each with its paper beneath.
    assert lines[0].startswith("--- 1990")
    assert lines[1].startswith("[1] (1990")
    assert any(line.startswith("[3] (2018") for line in lines)
    assert sum(line.startswith("---") for line in lines) == 3


def test_node_lines_by_era_falls_back_without_a_range():
    # A single distinct year has nothing to band — plain node_lines, no headers.
    nodes = [make_node("a", year=2015), make_node("b", year=2015)]
    assert prompts.node_lines_by_era(nodes) == prompts.node_lines(nodes)


def test_node_lines_by_era_sorts_undated_nodes_under_their_own_header():
    nodes = [
        make_node("a", title="Dated", year=2000),
        make_node("b", title="Other", year=2010),
        make_node("c", title="Undated", year=None),
    ]
    lines = prompts.node_lines_by_era(nodes).splitlines()
    assert "--- undated ---" in lines
    assert lines[-1].startswith("[3] (n.d.")


def test_idx_to_id_maps_and_ignores_out_of_range():
    nodes = [make_node("a"), make_node("b")]
    assert prompts.idx_to_id(nodes, [2, 1, 99, 0, -3]) == ["b", "a"]


def test_graph_refs_from_text_maps_used_markers_and_ignores_out_of_range():
    nodes = [make_node("a"), make_node("b"), make_node("c")]
    text = "As [1] showed, and later [3] refined it (see also [9], unrelated to [2])."
    # Only referenced, in-range markers; keyed by the number as a string.
    assert prompts.graph_refs_from_text(nodes, text) == {"1": "a", "3": "c", "2": "b"}
    # No markers -> empty map (a lecture beat that names no papers inline).
    assert prompts.graph_refs_from_text(nodes, "Plain prose, no citations.") == {}


def test_graph_refs_from_text_splits_combined_markers():
    nodes = [make_node("a"), make_node("b"), make_node("c")]
    # A combined marker contributes each of its (in-range) indices, mixing
    # comma and bare-space separators; an out-of-range member is dropped.
    assert prompts.graph_refs_from_text(nodes, "Both [1, 3] agree, and [2 9] diverge.") == {
        "1": "a",
        "3": "c",
        "2": "b",
    }


def _library_hits() -> list[dict]:
    """Two passages from two sources, one of them page-less (a web page).

    Returns:
        The passage dicts, as ``services.sources.search`` returns them.
    """
    return [
        {
            "source_id": "src-dl",
            "source_title": "Deep Learning",
            "page": 243,
            "text": "Momentum   helps\nconverge.",
        },
        {
            "source_id": "src-web",
            "source_title": "A Web Page",
            "page": None,
            "text": "Regularization notes.",
        },
    ]


def test_format_passages_tags_the_marker_to_copy():
    hits = _library_hits()
    rendered = prompts.format_passages(hits, prompts.source_order(hits))
    # The tag IS the citation marker — the model copies it rather than
    # rewording a title, and a page-less source drops the page half.
    assert "[S1, p.243] Momentum helps converge." in rendered
    assert "[S2] Regularization notes." in rendered


def test_format_passages_falls_back_to_the_title_when_unnumbered():
    # A surface with no numbered library (nothing can resolve a marker there)
    # still shows the passage, attributed by title — never silently dropped.
    rendered = prompts.format_passages(_library_hits(), [])
    assert "[Deep Learning, p.243] Momentum helps converge." in rendered
    assert "[A Web Page] Regularization notes." in rendered


def test_source_order_dedupes_by_source_first_seen():
    hits = _library_hits() + [
        {"source_id": "src-dl", "source_title": "Deep Learning", "page": 12, "text": "More."}
    ]
    assert prompts.source_order(hits) == [
        {"id": "src-dl", "title": "Deep Learning"},
        {"id": "src-web", "title": "A Web Page"},
    ]


def test_source_lines_numbers_the_library_with_extent():
    lines = prompts.source_lines(
        [
            {"id": "src-dl", "title": "Deep Learning", "pages": 800},
            {"id": "src-web", "title": "A Web Page", "kind": "url"},
            {"id": "src-bare", "title": "No Extent"},
        ]
    )
    assert lines == '[S1] "Deep Learning" (800pp)\n[S2] "A Web Page" (url)\n[S3] "No Extent"'


def test_source_refs_resolves_only_the_markers_used():
    sources = prompts.source_order(_library_hits())
    # S9 is hallucinated and dropped; the page in the marker is ignored here
    # (it rides on the marker, not the map).
    refs = prompts.source_refs(sources, "As shown [S1, p.243] and [S9, p.1] — also [S2].")
    assert refs == {
        "1": {"source_id": "src-dl", "title": "Deep Learning"},
        "2": {"source_id": "src-web", "title": "A Web Page"},
    }


def test_source_refs_with_no_text_maps_the_whole_library():
    # The up-front emit: no prose exists yet, so every source is resolvable.
    sources = prompts.source_order(_library_hits())
    assert set(prompts.source_refs(sources, "")) == {"1", "2"}


def test_history_converts_turns_and_skips_malformed():
    turns = [
        {"role": "user", "content": "q1"},
        {"role": "assistant", "content": "a1"},
        {"role": "system", "content": "not a chat role"},
        {"role": "user", "content": 42},
        {"content": "no role"},
    ]
    messages = prompts.history(turns)
    assert [type(message) for message in messages] == [ModelRequest, ModelResponse]
    assert prompts.history(None) == []
