"""Turns app data into model input, shared by every sub-agent: skill-assembled
instructions, retrieved passages rendered for a prompt, and route-layer
conversation turns converted to PydanticAI message history.

(Named ``prompts`` rather than ``skills`` — that name belongs to the
``skills/`` directory this module reads from.)
"""

from __future__ import annotations

from pathlib import Path

from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    UserPromptPart,
)

SKILLS_DIR = Path(__file__).parent / "skills"


def load_skill(name: str) -> str:
    """Read one skill's prompt-ready markdown from ``agents/skills/``.

    Args:
        name: The skill's file stem, e.g. ``"teaching-voice"``.

    Returns:
        The skill file's content, stripped.

    Raises:
        FileNotFoundError: When no such skill exists — a typo'd name in an
            agent's config.py fails at agent import, not by silently
            weakening its prompt.
    """
    return (SKILLS_DIR / f"{name}.md").read_text().strip()


def assemble(base: str, skills: tuple[str, ...]) -> str:
    """Build an agent's full instructions: its own words plus its skills.

    Args:
        base: The agent-specific prompt (its package config.py's
            ``SYSTEM_PROMPT``).
        skills: Names of the skills to append, in the order given.

    Returns:
        The base prompt with each skill's content appended as its own block.
    """
    return "\n\n".join([base, *(load_skill(name) for name in skills)])


def format_passages(hits: list[dict]) -> str:
    """Render retrieved library passages for a prompt.

    Args:
        hits: Passage dicts from ``services.sources.search`` (each carrying
            ``source_title``, optional ``page``, and ``text``).

    Returns:
        One passage per paragraph, tagged ``[Title, p.N]`` so the model can
        attribute it inline, whitespace collapsed.
    """
    lines = []
    for hit in hits:
        location = f", p.{hit['page']}" if hit.get("page") else ""
        lines.append(f"[{hit['source_title']}{location}] {' '.join(hit['text'].split())}")
    return "\n\n".join(lines)


def history(turns: list[dict] | None) -> list[ModelMessage]:
    """Convert route-layer conversation turns into PydanticAI message history.

    Only usable with agents built on ``instructions=`` (as all of ours are):
    with ``system_prompt=``, PydanticAI drops the prompt entirely whenever a
    message history is passed, silently losing the persona on every
    follow-up turn.

    Args:
        turns: Prior turns as ``[{role: user|assistant, content: str}, ...]``.
            Malformed turns are skipped, never raised on — history is
            nice-to-have context, not worth failing an answer over.

    Returns:
        The turns as ``ModelRequest`` / ``ModelResponse`` messages.
    """
    messages: list[ModelMessage] = []
    for turn in turns or []:
        content = turn.get("content")
        if not isinstance(content, str):
            continue
        if turn.get("role") == "user":
            messages.append(ModelRequest(parts=[UserPromptPart(content=content)]))
        elif turn.get("role") == "assistant":
            messages.append(ModelResponse(parts=[TextPart(content=content)]))
    return messages
