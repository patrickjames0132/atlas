"""One entry point for every teacher workflow, with guaranteed termination.

* ``main``     — ``run(intent, ...)``, the dispatcher (intents are
  ``agents.models.Intent``; also the documented seam where an orchestrator
  model would land if ambiguous intents ever exist).
* ``backfill`` — the deterministic "How we got here" reference walk run
  before a history lecture.

``run`` is re-exported here — callers use ``orchestrator.run(...)`` without
reaching into submodules.
"""

from __future__ import annotations

from .main import run

__all__ = ["run"]
