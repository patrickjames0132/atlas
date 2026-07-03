"""AI teacher: streaming lecture + grounded Q&A over the on-screen graph.

Phase 3a — narration is grounded **only** in the papers currently visible on the
user's graph (the seed plus its references / citations / similar work). The
agentic layer (Phase 3b) adds a tool-use loop with a hop budget and a visited-set
to kill reference cycles, so the teacher can also read full text and jump to
papers that aren't on screen yet.

The concern is split across modules, re-exported here so callers keep importing
``teacher.<fn>``:

  * ``lecture``       — ``lecture_beats`` / ``history_backfill`` (Phase 3a / 3e)
  * ``qa``            — ``answer_stream`` (non-agentic grounded Q&A, Phase 3a)
  * ``agentic``       — ``answer_agentic`` + ``agentic_available`` (Phase 3b)
  * ``sources_chat``  — ``answer_from_sources`` (offline library RAG, Phase 3d)
  * ``backends``      — the two Claude streaming backends + fallback
  * ``tools`` / ``neighbors`` / ``common`` — agent tools, cached S2 hops, and the
    shared node/citation text plumbing

To keep node references robust, the model never handles the long Semantic Scholar
paperIds: we present the visible papers as a numbered list and the model refers
to them by index, which we map back to ids on the way out.
"""

from __future__ import annotations

from .agentic import answer_agentic
from .lecture import history_backfill, lecture_beats
from .qa import answer_stream
from .sources_chat import answer_from_sources
from .tools import agentic_available

__all__ = [
    "lecture_beats",
    "history_backfill",
    "answer_stream",
    "answer_agentic",
    "agentic_available",
    "answer_from_sources",
]
