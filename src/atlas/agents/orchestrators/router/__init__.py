"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
The router: which assistant a typed message goes to.

One decision, exposed as one function. ``route(message)`` returns a
:class:`MessageRoute` — the lecturer or the researcher, plus the framing a
lecture would use — and it always returns one, so a caller has no failure
branch to write.

* ``main``   — the classifier agent, the ``MessageRoute`` output model, the
  no-model ``obvious_route`` fast path, and ``route`` over the two.
* ``config`` — the system prompt, the obvious-lecture pattern, and the
  borrowed agent id.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

from .main import ANSWER, MessageRoute, Target, agent, obvious_route, route

__all__ = ["ANSWER", "MessageRoute", "Target", "agent", "obvious_route", "route"]
