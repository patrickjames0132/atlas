"""The AI teacher as a crew of agents: an orchestrator delegating to focused
sub-agents, every workflow streaming typed events.

Layout rule: the package root is the shared directory — ``events`` (the typed
event stream), ``traversal`` (day-cached S2 hops), ``factory`` (config entry
-> live PydanticAI model), and ``skills/`` (skills.md files) are shared by
every agent; each sub-package *is* an agent. Sub-agents aren't imported here —
building one constructs its model, so consumers import exactly the agent they
need (``from ..agents import query_analyst``). See README.md for the full
architecture and the workflow definitions.
"""

from __future__ import annotations

from . import events, factory, traversal

__all__ = ["events", "factory", "traversal"]
