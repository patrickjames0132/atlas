"""The two Claude backends the teacher streams from, and the fallback wrapper.

Set via ``TEACHER_BACKEND``: the Anthropic API (``anthropic`` SDK) or the
``claude`` CLI under a Pro/Max subscription (no API billing). Both are consumed
as a **stream** of text so the frontend can reveal a lecture beat-by-beat and
light up graph nodes in sync with the story.

``_stream`` is the entry point: it tries the primary backend, then the fallback,
but only for failures **before the first token** — once bytes are flowing we
can't cleanly switch.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
from typing import TYPE_CHECKING, Iterator, Optional, cast

from .. import config

if TYPE_CHECKING:
    from anthropic.types import MessageParam

log = logging.getLogger(__name__)


def _stream_api(system: str, messages: list[dict], max_tokens: int) -> Iterator[str]:
    """Stream text deltas from the Anthropic API.

    Args:
        system: The system prompt.
        messages: The conversation as ``[{role, content}, ...]``.
        max_tokens: Token budget for the completion.

    Yields:
        Text deltas as they stream.

    Raises:
        RuntimeError: When ``TEACHER_BACKEND=api`` but no API key is set.
        anthropic.APIError: On API failures.
    """
    import anthropic

    if not config.ANTHROPIC_API_KEY:
        raise RuntimeError(
            "TEACHER_BACKEND=api but ANTHROPIC_API_KEY is not set. Add it to .env "
            "or set TEACHER_BACKEND=claude_cli to use your Pro/Max subscription."
        )
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    with client.messages.stream(
        model=config.TEACHER_MODEL,
        max_tokens=max_tokens,
        system=system,
        # Our {role, content} dicts are MessageParams; the cast just says so.
        messages=cast("list[MessageParam]", messages),
    ) as stream:
        for text in stream.text_stream:
            yield text


def _flatten(messages: list[dict]) -> str:
    """Collapse a message list into one prompt string for the headless CLI.

    A lecture is a single user turn; a Q&A carries prior turns, which we label
    so the model still sees the conversation.

    Args:
        messages: The conversation as ``[{role, content}, ...]``.

    Returns:
        The single message's content when there's only one; otherwise the
        turns labeled ``User:`` / ``Assistant:`` with a trailing
        ``Assistant:`` cue.
    """
    if len(messages) == 1:
        return messages[0]["content"]
    parts = []
    for m in messages:
        who = "User" if m["role"] == "user" else "Assistant"
        parts.append(f"{who}: {m['content']}")
    parts.append("Assistant:")
    return "\n\n".join(parts)


def _stream_cli(system: str, messages: list[dict], max_tokens: int) -> Iterator[str]:
    """Stream text deltas from the ``claude`` CLI (subscription, no API billing).

    Parses the CLI's ``stream-json`` events (``content_block_delta`` with a
    ``text_delta``); skips thinking deltas. Runs in a throwaway temp cwd so the
    CLI doesn't load this repo's CLAUDE.md / project context (which would bloat
    every call by thousands of cached tokens and muddy the output). If no
    deltas streamed (e.g. partial messages disabled by a CLI update), the
    final ``result`` event is yielded whole as a fallback.

    Args:
        system: The system prompt.
        messages: The conversation as ``[{role, content}, ...]`` (flattened
            into one prompt string for the headless CLI).
        max_tokens: Unused by the CLI path (kept for signature parity with
            ``_stream_api``).

    Yields:
        Text deltas as they stream.

    Raises:
        RuntimeError: When the CLI exits non-zero (its stderr is included).
        FileNotFoundError: When the ``claude`` binary isn't on PATH.
        subprocess.TimeoutExpired: When the CLI outlives
            ``TEACHER_CLI_TIMEOUT``.
    """
    cmd = [
        config.CLAUDE_CLI_PATH,
        "-p",
        _flatten(messages),
        "--system-prompt",
        system,
        "--output-format",
        "stream-json",
        "--include-partial-messages",
        "--verbose",
    ]
    if config.TEACHER_CLI_MODEL:
        cmd += ["--model", config.TEACHER_CLI_MODEL]

    # Use the subscription login, not API billing (mirrors summarizer.py).
    env = os.environ.copy()
    env.pop("ANTHROPIC_API_KEY", None)
    env.pop("ANTHROPIC_AUTH_TOKEN", None)

    with tempfile.TemporaryDirectory() as tmp:
        stderr_f = tempfile.TemporaryFile(mode="w+")
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=stderr_f,
            text=True,
            env=env,
            cwd=tmp,
        )
        saw_text = False
        result_fallback: Optional[str] = None
        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    evt = json.loads(line)
                except json.JSONDecodeError:
                    continue
                etype = evt.get("type")
                if etype == "stream_event":
                    e = evt.get("event", {})
                    if e.get("type") == "content_block_delta":
                        d = e.get("delta", {})
                        if d.get("type") == "text_delta" and d.get("text"):
                            saw_text = True
                            yield d["text"]
                elif etype == "result":
                    # Emitted once at the end; keep as a fallback if no deltas
                    # streamed (e.g. partial messages disabled by a CLI update).
                    if isinstance(evt.get("result"), str):
                        result_fallback = evt["result"]
            proc.wait(timeout=config.TEACHER_CLI_TIMEOUT)
        finally:
            if proc.poll() is None:
                proc.kill()
        if proc.returncode not in (0, None):
            stderr_f.seek(0)
            err = stderr_f.read().strip()
            raise RuntimeError(
                f"claude CLI failed (exit {proc.returncode}): {err[:300]}"
            )
        if not saw_text and result_fallback:
            yield result_fallback


def _stream(system: str, messages: list[dict], max_tokens: int) -> Iterator[str]:
    """Stream a completion, trying the primary backend then the fallback.

    Fallback only helps for failures **before the first token** (missing key,
    CLI not on PATH, spawn error) — the common case. Once streaming has begun
    we can't cleanly switch, so a mid-stream failure surfaces to the caller.

    Args:
        system: The system prompt.
        messages: The conversation as ``[{role, content}, ...]``.
        max_tokens: Token budget for the completion.

    Yields:
        Text deltas from whichever backend started successfully.

    Raises:
        RuntimeError: When every configured backend failed to start (the last
            error is included).
    """
    primary = config.TEACHER_BACKEND
    fallback = config.TEACHER_FALLBACK_BACKEND or None
    backends = [primary]
    if fallback and fallback != primary:
        backends.append(fallback)

    last_err: Optional[Exception] = None
    for backend in backends:
        fn = _stream_api if backend == "api" else _stream_cli
        try:
            gen = fn(system, messages, max_tokens)
            first = next(gen)  # trips init/spawn errors before we commit
        except StopIteration:
            return  # backend produced nothing, but didn't error
        except Exception as exc:  # noqa: BLE001 — try the fallback
            last_err = exc
            log.warning("teacher backend %r failed to start: %s", backend, exc)
            continue
        yield first
        yield from gen
        return
    raise RuntimeError(f"all teacher backends failed ({last_err})")
