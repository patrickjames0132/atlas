"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
One entry point for every teacher workflow, with guaranteed termination.

* ``main`` — ``run(intent, ...)``, the dispatcher (intents are
  ``agents.models.Intent``; also the documented seam where an orchestrator
  model would land if ambiguous intents ever exist).

``run`` is re-exported here — callers use ``orchestrator.run(...)`` without
reaching into submodules.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

from .main import run

__all__ = ["run"]
