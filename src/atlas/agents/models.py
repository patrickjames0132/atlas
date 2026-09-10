"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
Shared vocabulary for the agents package: the played-lecture context the
researcher receives.

It lives at the package root (not inside the lecturer's or researcher's
package) because it's the *vocabulary of the package's public surface* —
routes construct these, the agents take them, and workflows receive them.

``LectureMode`` used to live here too: a five-member ``StrEnum`` naming which
story a lecture told. It went in v7.17.0 with the mode buttons themselves —
a lecture now narrates whatever the reader has scoped on screen, and the one
remaining variation (the bridge) is signalled by the presence of a target
paper rather than by a string the route has to parse and validate.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class PlayedBeat(BaseModel):
    """One beat of an already-delivered lecture, trimmed to what the researcher
    needs as context: the signpost heading and the narration paragraph (the
    node ids, graph_refs, and figure the frontend renders are dropped on the wire).
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
