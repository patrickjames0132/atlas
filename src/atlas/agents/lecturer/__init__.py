"""Streamed graph lecture: the story of the visible papers, in typed beats.

* ``main``   — the ``Agent`` and ``lecture`` (the Beat event generator).
* ``config`` — the agent id, prompt, skills, and mode intents.

``lecture`` is re-exported here — callers use ``lecturer.lecture(...)``
without reaching into submodules.
"""

from __future__ import annotations

from .main import agent, lecture

__all__ = ["agent", "lecture"]
