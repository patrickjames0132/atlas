"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
The sync event bridge: a single stream driven to its final result, and —
the regression — many streams driven concurrently over the one shared loop
without an ``Event loop is closed`` (the failure that hit when several lectures
played at once, each formerly on its own per-call loop over the shared client).

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

import json
import threading

from pydantic import BaseModel, ConfigDict
from pydantic_ai import Agent
from pydantic_ai.models.function import DeltaToolCall, FunctionModel
from pydantic_ai.run import AgentRunResultEvent

from atlas.agents import streams


class _Out(BaseModel):
    """A tiny structured output so the run streams via the final_result tool."""

    model_config = ConfigDict(extra="forbid")

    value: str


def _agent(value: str) -> Agent[None, _Out]:
    """An agent whose model streams ``{"value": value}`` as final_result args,
    split across two chunks so the run produces several stream events."""

    async def stream(messages, info):
        payload = json.dumps({"value": value})
        half = len(payload) // 2
        yield {0: DeltaToolCall(name="final_result", json_args=payload[:half])}
        yield {0: DeltaToolCall(json_args=payload[half:])}

    return Agent(FunctionModel(stream_function=stream), output_type=_Out)


def _final_output(agent: Agent[None, _Out]) -> _Out | None:
    """Drive an agent to completion and return its final structured output."""
    result: _Out | None = None
    for event in streams.drive(agent, "go"):
        if isinstance(event, AgentRunResultEvent):
            result = event.result.output
    return result


def test_drive_runs_a_stream_to_its_final_result():
    assert _final_output(_agent("hello")) == _Out(value="hello")


def test_drive_handles_many_concurrent_streams():
    # Each thread drives its own stream; before the shared-loop bridge, running
    # several at once (separate per-call loops over the one client) tore the
    # loop out mid-run. They must now all finish, each with its own output.
    agents = {index: _agent(f"v{index}") for index in range(8)}
    results: dict[int, _Out | None] = {}
    errors: list[Exception] = []

    def worker(index: int, agent: Agent[None, _Out]) -> None:
        try:
            results[index] = _final_output(agent)
        except Exception as error:  # pragma: no cover - the regression path
            errors.append(error)

    threads = [
        threading.Thread(target=worker, args=(index, agent))
        for index, agent in agents.items()
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not errors
    assert results == {index: _Out(value=f"v{index}") for index in range(8)}
