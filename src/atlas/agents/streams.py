"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
Shared plumbing for consuming a PydanticAI run synchronously, one event
at a time.

``run_stream_events`` is async-only, but every workflow here is a sync
generator (Flask streams them as SSE). ``drive`` bridges the gap: it runs
the stream on a shared background event loop and yields each event as it
arrives — the caller stays a plain generator, and tool events / output deltas
flow out live.

This is the bridge the researcher was built on, promoted to a shared module when
the lecturer needed it too: the sync convenience wrapper
(``run_stream_sync().stream_output()``) turned out to deliver structured
output in one burst at the end against the live API — narration "streamed"
all at once. Driving the raw event stream is what actually streams.

**One persistent loop, not a fresh one per call.** The agents (and their one
shared Anthropic ``AsyncClient``) are module-level singletons, but an earlier
``drive`` opened a *new* event loop per call and closed it at the end. Under
concurrency — several lectures playing at once, each on its own Flask thread and
so its own loop — every call reused the single httpx connection pool, which
binds to the first loop that touches it; the first loop to close then tore the
pool out from under the still-running streams, surfacing as ``Event loop is
closed``. Running everything on one long-lived loop (reached from any request
thread via ``run_coroutine_threadsafe``) fixes it: httpx multiplexes concurrent
requests on a single loop safely.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

import asyncio
import threading
from typing import Any, AsyncIterator, Coroutine, Iterator, TypeVar

from pydantic_ai import Agent
from pydantic_ai.messages import AgentStreamEvent
from pydantic_ai.run import AgentRunResultEvent
from pydantic_core import from_json

OUTPUT_TOOL = "final_result"
"""PydanticAI's default output-tool name — structured final results stream
as this tool call's argument deltas."""


def partial_text(args_json: str, field: str = "text") -> str:
    """A string field's value out of a partially-streamed output-tool args JSON.

    ``allow_partial="trailing-strings"`` keeps the truncated tail of the
    in-flight string, so prose streams smoothly instead of buffering until
    the field closes. Shared by every agent that streams a structured
    result's prose (researcher, librarian) — structured output is the house
    answer to tool-call narration: text a model emits *outside* its final
    result is ignored instead of streamed-then-disavowed.

    Args:
        args_json: The output tool call's JSON args accumulated so far.
        field: The string field to extract.

    Returns:
        The field's current value; ``""`` while it's undecodable or absent.
    """
    try:
        parsed = from_json(args_json, allow_partial="trailing-strings")
    except ValueError:
        return ""
    value = parsed.get(field) if isinstance(parsed, dict) else None
    return value if isinstance(value, str) else ""

_Result = TypeVar("_Result")


class _AsyncRunner:
    """A single long-lived asyncio loop on a daemon thread.

    All agent async work runs here so the Anthropic ``AsyncClient``'s httpx
    connection pool stays bound to one loop for the process's life. Request
    threads submit coroutines with ``run`` and block until each completes,
    while the loop keeps serving every other in-flight stream — the concurrency
    model asyncio is built for.
    """

    def __init__(self) -> None:
        self._loop = asyncio.new_event_loop()
        thread = threading.Thread(
            target=self._serve, name="atlas-agent-loop", daemon=True
        )
        thread.start()

    def _serve(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def run(self, coro: Coroutine[Any, Any, _Result]) -> _Result:
        """Run a coroutine to completion on the shared loop.

        Args:
            coro: The coroutine to schedule on the background loop.

        Returns:
            The coroutine's result, once it completes. The calling (request)
            thread blocks until then; any exception the coroutine raises
            propagates here.
        """
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result()


# Created once at import — the process-wide loop every ``drive`` call shares.
_runner = _AsyncRunner()

_STREAM_DONE = object()
"""Sentinel for an exhausted stream — cleaner than threading a raw
``StopAsyncIteration`` back through a cross-thread future."""


async def _anext_or_done(stream: AsyncIterator[Any]) -> Any:
    """Pull the next stream event, or the ``_STREAM_DONE`` sentinel at the end."""
    try:
        return await anext(stream)
    except StopAsyncIteration:
        return _STREAM_DONE


def drive(
    agent: Agent[Any, Any], *args: Any, **kwargs: Any
) -> Iterator[AgentStreamEvent | AgentRunResultEvent[Any]]:
    """Run an agent and yield its stream events synchronously.

    Args:
        agent: The PydanticAI agent to run.
        *args: Positional arguments for ``run_stream_events`` (the prompt).
        **kwargs: Keyword arguments for ``run_stream_events`` (deps,
            message_history, usage_limits, ...).

    Yields:
        Every ``AgentStreamEvent``, then the final ``AgentRunResultEvent``.
        The async context manager is exited whether the consumer finishes,
        raises, or abandons the generator early. Each event is awaited on the
        shared background loop (see ``_AsyncRunner``).
    """
    stream_ctx = agent.run_stream_events(*args, **kwargs)
    stream = _runner.run(stream_ctx.__aenter__())
    try:
        while True:
            event = _runner.run(_anext_or_done(stream))
            if event is _STREAM_DONE:
                break
            yield event
    finally:
        _runner.run(stream_ctx.__aexit__(None, None, None))
