"""The one exception the sources subsystem raises."""

from __future__ import annotations


class SourceError(RuntimeError):
    """Ingestion or search failed for a reason worth surfacing to the user."""
