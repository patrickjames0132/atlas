"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
Server-Sent-Events plumbing, shared by every streaming route (the agent
endpoints and source ingestion).

One trap worth knowing for any route that uses these: SSE generators run
during response iteration, AFTER the request/app context is gone — touching
``request`` or ``current_app`` inside one raises ``RuntimeError`` and kills
the stream. Parse the request and use a module logger before/outside the
generator.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

import json
from typing import Iterator

from flask import Response


def sse(event: str, data: object) -> str:
    """Format one Server-Sent Event frame.

    Args:
        event: The event name (``beat``, ``token``, ``progress``, …).
        data: A JSON-serializable payload.

    Returns:
        The wire-format frame: ``event:`` and ``data:`` lines terminated by
        a blank line.
    """
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def sse_response(generator: Iterator[str]) -> Response:
    """Wrap a generator of SSE frames as a streaming response.

    ``X-Accel-Buffering: no`` keeps nginx (if ever put in front) from
    buffering the stream; ``Cache-Control: no-cache`` stops intermediaries
    caching partial output.

    Args:
        generator: An iterator yielding SSE frame strings (from ``sse``).

    Returns:
        A ``text/event-stream`` Flask Response streaming the frames.
    """
    return Response(
        generator,
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
