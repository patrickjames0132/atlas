"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
The search workers — one per place an answer can be grounded in.

Grouped rather than sitting loose under ``workers/`` because "go look
something up somewhere" is one job with several backends, and the next one
(an arXiv listing, a code index, the user's notes) belongs here beside them
rather than as another top-level worker. A worker of a different *kind* —
one that transforms rather than retrieves — would get its own group.

Nothing is imported here: constructing an agent builds its model.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations
