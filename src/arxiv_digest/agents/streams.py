"""Shared plumbing for consuming a PydanticAI run synchronously, one event
at a time.

``run_stream_events`` is async-only, but every workflow here is a sync
generator (Flask streams them as SSE). ``drive`` bridges the gap: it runs
the stream on a private event loop and yields each event as it arrives —
the caller stays a plain generator, and tool events / output deltas flow
out live.

This is the bridge the researcher was built on, promoted to a shared module when
the lecturer needed it too: the sync convenience wrapper
(``run_stream_sync().stream_output()``) turned out to deliver structured
output in one burst at the end against the live API — narration "streamed"
all at once. Driving the raw event stream is what actually streams.
"""

from __future__ import annotations

import asyncio
from typing import Any, Iterator

from pydantic_ai import Agent
from pydantic_ai.messages import AgentStreamEvent
from pydantic_ai.run import AgentRunResultEvent

OUTPUT_TOOL = "final_result"
"""PydanticAI's default output-tool name — structured final results stream
as this tool call's argument deltas."""


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
        The async context manager is exited (and the loop closed) whether
        the consumer finishes, raises, or abandons the generator early.
    """
    loop = asyncio.new_event_loop()
    try:
        stream_ctx = agent.run_stream_events(*args, **kwargs)
        stream = loop.run_until_complete(stream_ctx.__aenter__())
        try:
            while True:
                try:
                    event = loop.run_until_complete(anext(stream))
                except StopAsyncIteration:
                    break
                yield event
        finally:
            loop.run_until_complete(stream_ctx.__aexit__(None, None, None))
    finally:
        loop.close()
