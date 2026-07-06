"""The AI teacher as a crew of agents: an orchestrator delegating to focused
sub-agents, every workflow streaming typed events.

Layout rule: the package root is the shared directory — ``events`` (the typed
event stream), ``traversal`` (day-cached S2 hops), and ``skills/`` (skills.md
files) are shared by every agent; each sub-package *is* an agent. See
README.md for the full architecture and the workflow definitions.
"""

from __future__ import annotations

from . import events, traversal

__all__ = ["events", "traversal"]
