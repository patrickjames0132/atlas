"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
The one exception the sources subsystem raises.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations


class SourceError(RuntimeError):
    """Ingestion or search failed for a reason worth surfacing to the user."""
