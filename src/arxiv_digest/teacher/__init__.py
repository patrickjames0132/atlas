"""AI teacher — MID-REWRITE RUMP: only the lecture module remains unported.

The teacher is being rebuilt as the ``agents`` package (v2 rewrite). Already
retired from here: ``qa`` (deleted, not ported — it was the CLI backend's
consolation prize), ``agentic``/``tools`` (now ``agents/tutor``),
``neighbors`` (now ``agents/traversal``), ``sources_chat`` (now
``agents/librarian``). What's left:

  * ``lecture``  — ``lecture_beats`` (superseded by ``agents/lecturer`` but
    still hosting ``history_backfill``, which ports with the orchestrator in
    Phase 4d — then this whole package goes)
  * ``backends`` / ``common`` — plumbing ``lecture`` still leans on

To keep node references robust, the model never handles the long Semantic
Scholar paperIds: we present the visible papers as a numbered list and the
model refers to them by index, which we map back to ids on the way out.
"""

from __future__ import annotations

from .lecture import history_backfill, lecture_beats

__all__ = [
    "lecture_beats",
    "history_backfill",
]
