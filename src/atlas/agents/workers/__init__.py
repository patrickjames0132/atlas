"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
The agents that own one source each and answer a bounded question about it.

The other tier is ``orchestrators/``. Nothing is imported here on purpose:
constructing an agent builds its model, so consumers import the one they need
(``from ...workers import papers``) — the same rule the package root follows.

See README.md for the membership rule (what earns worker status) and the
return-shape contract (structured findings, never prose, never indices).

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations
