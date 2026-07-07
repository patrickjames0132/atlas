"""Offline library chat: retrieve-then-answer RAG over the user's own
uploaded sources.

* ``main``   — the ``Agent`` and ``answer`` (the RetrievalTrace/Token event
  generator).
* ``config`` — the agent id, prompt, skills, and the no-hits answer.

``answer`` is re-exported here — callers use ``librarian.answer(...)``
without reaching into submodules.
"""

from __future__ import annotations

from .main import agent, answer

__all__ = ["agent", "answer"]
