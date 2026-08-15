"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
The agents that own one source each and answer a bounded question about it.

The other tier is ``orchestrators/``. Workers are grouped by *kind* rather
than sitting loose here — ``search/`` holds the ones that go and look
something up (papers, the web), and a worker that transforms rather than
retrieves would get its own group beside it.

Nothing is imported here on purpose: constructing an agent builds its model,
so consumers import the one they need
(``from ...workers.search import papers``) — the same rule the package root
follows.

See ``search/README.md`` for the membership rule (what earns worker status)
and the return-shape contract (structured findings, never prose, never
indices).

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations
