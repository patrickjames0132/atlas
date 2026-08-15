"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
The AI teacher as a crew of agents: an orchestrator delegating to focused
sub-agents, every workflow streaming typed events.

Layout rule: the package root is the shared directory — ``events`` (the typed
event stream), ``traversal`` (day-cached S2 hops), ``factory`` (config entry
-> live PydanticAI model), and ``skills/`` (skills.md files) are shared by
every agent. The agents themselves sit in two tiers, flat and deliberately no
deeper: ``orchestrators/`` own an outcome and delegate; ``workers/`` each own
one source and answer a bounded question about it. Agents aren't imported
here — building one constructs its model, so consumers import exactly the one
they need (``from ..agents.orchestrators import query_analyst``). See
README.md for the full architecture and the workflow definitions.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

from . import events, factory, traversal

__all__ = ["events", "factory", "traversal"]
