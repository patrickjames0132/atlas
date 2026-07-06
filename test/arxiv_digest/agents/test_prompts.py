"""Model-input parts: skill loading, passage rendering, and history
conversion. (Joining the parts into one prompt is PydanticAI's job — agents
pass ``instructions=[SYSTEM_PROMPT, *skills]`` and it joins with blank
lines.)"""

from __future__ import annotations

import pytest
from pydantic_ai.messages import ModelRequest, ModelResponse

from arxiv_digest.agents import prompts
from arxiv_digest.services.graph import Node


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


def test_idx_to_id_maps_and_ignores_out_of_range():
    nodes = [make_node("a"), make_node("b")]
    assert prompts.idx_to_id(nodes, [2, 1, 99, 0, -3]) == ["b", "a"]


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
