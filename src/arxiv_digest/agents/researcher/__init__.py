"""Agentic Q&A over the graph: read, expand, search — then answer, grounded.

* ``main``   — the ``Agent``, the ``Answer`` output model, and ``answer``
  (the Trace/Discovery/Figure/Token/Cited event generator).
* ``tools``  — the model-callable tool surface and ``ResearcherDeps`` run-state.
* ``config`` — the agent id, prompt, skills, and budgets.

``answer`` is re-exported here — callers use ``researcher.answer(...)`` without
reaching into submodules.
"""

from __future__ import annotations

from .main import Answer, agent, answer

__all__ = ["Answer", "agent", "answer"]
