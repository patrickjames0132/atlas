"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
On-demand paper TL;DRs: one plain-language sentence written from a
paper's title + abstract, for papers whose provider ships none (every
OpenAlex paper; the S2 papers S2 never summarized).

* ``main``   — the ``Agent``, its ``Summary`` output model, and
  ``summarize`` (the None-on-failure entry point).
* ``config`` — the agent id, system prompt, and (empty) skill list.

``summarize`` is re-exported here — callers use
``summarizer.summarize(...)`` without reaching into submodules.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

from .main import Summary, agent, summarize

__all__ = ["Summary", "agent", "summarize"]
