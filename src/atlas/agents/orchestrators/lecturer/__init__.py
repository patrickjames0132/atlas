"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
Streamed graph lecture: the story of the reader's scoped papers, in typed beats.

* ``main``   — the ``Agent`` and ``lecture`` (the Beat event generator).
* ``config`` — the agent id, prompt, skills, and the intent paragraphs.

``lecture`` and the ``Framing`` alias are re-exported here — callers use
``lecturer.lecture(...)`` without reaching into submodules.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

from .config import Framing
from .main import agent, lecture

__all__ = ["Framing", "agent", "lecture"]
