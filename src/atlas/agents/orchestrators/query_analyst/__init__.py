"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
Seed-search query analysis: acronyms and jargon spelled out so S2's
lexical search can find the papers that never use them, plus confidently
recalled exact paper titles for S2 title-match verification.

* ``main``   — the ``Agent``, its ``Expansion`` output model, and
  ``analyze`` (the passthrough-on-failure entry point).
* ``config`` — the agent id, system prompt, and (empty) skill list.

``analyze`` is re-exported here — callers use ``query_analyst.analyze(...)``
without reaching into submodules.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

from .main import Expansion, agent, analyze

__all__ = ["Expansion", "agent", "analyze"]
