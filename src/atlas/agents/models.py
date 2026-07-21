"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
Shared vocabulary for the agents package: the workflow intents, the
lecture modes, and the played-lecture context the researcher receives.

They live at the package root (not inside the orchestrator's or lecturer's
package) because they're the *vocabulary of the package's public surface* —
routes construct them, the orchestrator dispatches on them, and workflows
receive them. ``StrEnum`` so members compare and serialize as their wire
strings (``Intent.RESEARCH == "research"``), which keeps the HTTP layer and
the ``MODE_INTENTS`` prompt table oblivious to the enum-ness.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class Intent(StrEnum):
    """Which teacher workflow a request is asking for."""

    LECTURE = "lecture"
    RESEARCH = "research"
    LIBRARIAN = "librarian"


class LectureMode(StrEnum):
    """Which story a lecture tells."""

    HISTORY = "history"
    INTUITION = "intuition"
    EVOLUTION = "evolution"
    FRONTIER = "frontier"
    BRIDGE = "bridge"


class PlayedBeat(BaseModel):
    """One beat of an already-delivered lecture, trimmed to what the researcher
    needs as context: the signpost heading and the narration paragraph (the
    node ids, refs, and figure the frontend renders are dropped on the wire).
    """

    model_config = ConfigDict(extra="forbid")

    heading: str
    text: str


class PlayedLecture(BaseModel):
    """A lecture already delivered to the student this session, handed to the
    researcher as grounding so a Q&A answer can build on that narrative instead
    of re-deriving the same ground and re-paying for the tokens.

    ``title`` is the lecture's display name ("How we got here", ...); ``beats``
    are its beats in order. Constructed defensively in the route from the
    frontend's transcript cache — malformed entries are skipped, never 400.
    """

    model_config = ConfigDict(extra="forbid")

    title: str
    beats: list[PlayedBeat]
