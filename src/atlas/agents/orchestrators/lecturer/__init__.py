"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
Streamed graph lecture: the story of the visible papers, in typed beats.

* ``main``   — the ``Agent`` and ``lecture`` (the Beat event generator).
* ``config`` — the agent id, prompt, skills, and mode intents.

``lecture`` is re-exported here — callers use ``lecturer.lecture(...)``
without reaching into submodules.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

from .main import agent, lecture

__all__ = ["agent", "lecture"]
