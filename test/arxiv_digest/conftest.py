"""Shared fixtures for the arXiv Atlas test suite.

The suite is **fully offline** — no live arXiv / Semantic Scholar / Anthropic
calls, and no touching the real ``data/`` databases. Two fixtures enforce that
baseline for every test:

- ``_isolate`` (autouse) points every database path at a per-test temp dir and
  zeroes the S2 throttle, so tests can't read or write real user data — or
  sleep.
- ``fake_claude`` builds a scripted stand-in for the Anthropic client out of
  **real SDK event objects** (``RawContentBlockDeltaEvent`` etc.), so the
  agentic loop's isinstance narrowing is exercised exactly as in production.

``stub_embeddings`` swaps the sentence-transformers model for a cheap
deterministic embedder so library tests can ingest and search without torch.
"""

from __future__ import annotations

import hashlib
import math

import pytest
from anthropic.types import (
    Message,
    RawContentBlockDeltaEvent,
    RawContentBlockStartEvent,
    TextBlock,
    TextDelta,
    ToolUseBlock,
    Usage,
)
from arxiv_digest import config
from arxiv_digest.library import embeddings


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    """Point every DB at a temp dir and disable the S2 throttle (autouse)."""
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "digest.db")
    monkeypatch.setattr(config, "SOURCES_DB_PATH", tmp_path / "sources.db")
    monkeypatch.setattr(config, "SESSIONS_DB_PATH", tmp_path / "sessions.db")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "S2_MIN_INTERVAL", 0.0)


@pytest.fixture()
def flask_client():
    """A Flask test client over the real app (no network is touched)."""
    from arxiv_digest.app import app as flask_app

    flask_app.config.update(TESTING=True)
    return flask_app.test_client()


# --- fake Anthropic client ----------------------------------------------------

def text_delta(text: str, index: int = 0) -> RawContentBlockDeltaEvent:
    """A real SDK text-delta stream event carrying ``text``."""
    return RawContentBlockDeltaEvent(
        type="content_block_delta", index=index,
        delta=TextDelta(type="text_delta", text=text),
    )


def tool_use_block(name: str, tool_input: dict, block_id: str = "tu_1") -> ToolUseBlock:
    """A real SDK tool_use content block."""
    return ToolUseBlock(type="tool_use", id=block_id, name=name, input=tool_input)


def tool_start(block: ToolUseBlock, index: int = 1) -> RawContentBlockStartEvent:
    """The stream event announcing ``block`` (what flips a turn to a tool turn)."""
    return RawContentBlockStartEvent(
        type="content_block_start", index=index, content_block=block
    )


def final_message(content: list, stop_reason: str) -> Message:
    """A real SDK final Message with the given content blocks and stop reason."""
    return Message(
        id="msg_1", content=content, model="claude-test", role="assistant",
        stop_reason=stop_reason, type="message",
        usage=Usage(input_tokens=1, output_tokens=1),
    )


def text_turn(text: str) -> tuple[list, Message]:
    """Script one plain answer turn: its stream events + end_turn final."""
    return ([text_delta(text)], final_message([TextBlock(type="text", text=text)], "end_turn"))


def tool_turn(name: str, tool_input: dict, preamble: str = "") -> tuple[list, Message]:
    """Script one tool-call turn (optionally preceded by streamed preamble)."""
    block = tool_use_block(name, tool_input)
    events: list = [text_delta(preamble)] if preamble else []
    events.append(tool_start(block))
    content: list = [TextBlock(type="text", text=preamble)] if preamble else []
    content.append(block)
    return (events, final_message(content, "tool_use"))


class _FakeStream:
    """Context-manager + iterator standing in for the SDK's MessageStream."""

    def __init__(self, events: list, final: Message):
        self._events, self._final = events, final

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def __iter__(self):
        return iter(self._events)

    def get_final_message(self) -> Message:
        return self._final

    @property
    def text_stream(self):
        """Text deltas only — what the non-tool paths consume."""
        return (
            e.delta.text for e in self._events
            if isinstance(e, RawContentBlockDeltaEvent) and isinstance(e.delta, TextDelta)
        )


class FakeClaude:
    """A scripted Anthropic client: returns one scripted turn per stream() call.

    ``calls`` records each stream() call's kwargs so tests can assert what the
    loop offered the model (tools present/absent, message growth, …).
    """

    def __init__(self, turns: list[tuple[list, Message]]):
        self._turns = list(turns)
        self.calls: list[dict] = []
        self.messages = self  # client.messages.stream(...) resolves to self.stream

    def stream(self, **kwargs) -> _FakeStream:
        self.calls.append(kwargs)
        if not self._turns:
            raise AssertionError("FakeClaude ran out of scripted turns")
        events, final = self._turns.pop(0)
        return _FakeStream(events, final)


@pytest.fixture()
def fake_claude(monkeypatch):
    """Patch anthropic.Anthropic with a scripted client; returns the installer.

    Usage::

        client = fake_claude([text_turn("hi <<CITED>> [1]")])
        events = list(answer_agentic(...))
        assert client.calls[0]["tools"]
    """
    import anthropic

    def install(turns: list[tuple[list, Message]]) -> FakeClaude:
        client = FakeClaude(turns)
        monkeypatch.setattr(anthropic, "Anthropic", lambda **kw: client)
        return client

    return install


# --- deterministic offline embeddings -----------------------------------------

def _hash_vector(text: str, dim: int) -> list[float]:
    """A cheap deterministic unit vector derived from the text's words.

    Not semantically meaningful — but identical texts embed identically and
    share tokens overlap, which is enough to test storage, scoping, and
    ranking plumbing without loading a model.
    """
    vec = [0.0] * dim
    for word in text.lower().split():
        h = int.from_bytes(hashlib.md5(word.encode()).digest()[:4], "big")
        vec[h % dim] += 1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


@pytest.fixture()
def stub_embeddings(monkeypatch):
    """Replace the sentence-transformers embedder with the hash embedder."""
    monkeypatch.setattr(embeddings, "available", lambda: True)
    monkeypatch.setattr(
        embeddings, "embed_texts",
        lambda texts, **kw: [_hash_vector(t, config.EMBED_DIM) for t in texts] or None,
    )
    monkeypatch.setattr(
        embeddings, "embed_query",
        lambda text: _hash_vector(config.EMBED_QUERY_PREFIX + text, config.EMBED_DIM),
    )
