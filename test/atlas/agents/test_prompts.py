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


def test_refs_from_text_maps_used_markers_and_ignores_out_of_range():
    nodes = [make_node("a"), make_node("b"), make_node("c")]
    text = "As [1] showed, and later [3] refined it (see also [9], unrelated to [2])."
    # Only referenced, in-range markers; keyed by the number as a string.
    assert prompts.refs_from_text(nodes, text) == {"1": "a", "3": "c", "2": "b"}
    # No markers -> empty map (a lecture beat that names no papers inline).
    assert prompts.refs_from_text(nodes, "Plain prose, no citations.") == {}


def test_refs_from_text_splits_combined_markers():
    nodes = [make_node("a"), make_node("b"), make_node("c")]
    # A combined marker contributes each of its (in-range) indices, mixing
    # comma and bare-space separators; an out-of-range member is dropped.
    assert prompts.refs_from_text(nodes, "Both [1, 3] agree, and [2 9] diverge.") == {
        "1": "a",
        "3": "c",
        "2": "b",
    }


def test_format_passages_tags_source_and_page():
    hits = [
        {"source_title": "Deep Learning", "page": 243, "text": "Momentum   helps\nconverge."},
        {"source_title": "A Web Page", "page": None, "text": "Regularization notes."},
    ]
    rendered = prompts.format_passages(hits)
    assert "[Deep Learning, p.243] Momentum helps converge." in rendered
    assert "[A Web Page] Regularization notes." in rendered


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
