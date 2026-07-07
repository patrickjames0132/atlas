"""Shared enums for the agents package: the workflow intents and the
lecture modes.

They live at the package root (not inside the orchestrator's or lecturer's
package) because they're the *vocabulary of the package's public surface* —
routes construct them, the orchestrator dispatches on them, and workflows
receive them. ``StrEnum`` so members compare and serialize as their wire
strings (``Intent.RESEARCH == "research"``), which keeps the HTTP layer and
the ``MODE_INTENTS`` prompt table oblivious to the enum-ness.
"""

from __future__ import annotations

from enum import StrEnum


class Intent(StrEnum):
    """Which teacher workflow a request is asking for."""

    LECTURE = "lecture"
    RESEARCH = "research"
    LIBRARIAN = "librarian"


class LectureMode(StrEnum):
    """Which story a lecture tells."""

    HISTORY = "history"
    INTUITION = "intuition"
    BRIDGE = "bridge"
