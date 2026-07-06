"""Model-input assembly: skill loading, prompt assembly, passage rendering,
and history conversion."""

from __future__ import annotations

import pytest
from pydantic_ai.messages import ModelRequest, ModelResponse

from arxiv_digest.agents import prompts


def test_assemble_appends_each_skill_after_the_base():
    combined = prompts.assemble("BASE PROMPT", ("teaching-voice", "citation-discipline"))
    assert combined.startswith("BASE PROMPT")
    assert "# Teaching voice" in combined
    assert "# Citation discipline" in combined
    assert combined.index("# Teaching voice") < combined.index("# Citation discipline")


def test_assemble_with_no_skills_is_just_the_base():
    assert prompts.assemble("BASE PROMPT", ()) == "BASE PROMPT"


def test_unknown_skill_fails_loudly():
    with pytest.raises(FileNotFoundError):
        prompts.load_skill("no-such-skill")


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
