"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
The agents that own an outcome: they decide what the work is, delegate parts
of it, and are answerable for the result the user sees.

The other tier is ``agents/workers/`` — one source each, one bounded question
each. The line between them is in ``workers/README.md``; the short version is
that an orchestrator owns everything that has to be globally consistent (the
numbered paper list, citation resolution, provenance, the event-stream
contract, the answer itself), which is precisely what can't be delegated
without two delegates disagreeing.

Nothing is imported here on purpose: constructing an agent builds its model,
so a bare ``import orchestrators`` would build five. Consumers import the one
they need (``from ..agents.orchestrators import researcher``) — the same rule
the package root follows, and for the same reason.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations
