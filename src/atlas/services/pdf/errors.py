"""The one error type this package raises.

Split into its own module (mirroring ``services/sources/errors.py``) so any
submodule can raise it without import cycles, and so callers can catch one
exception type for every way PDF mining can fail — download refused, file too
big, not actually a PDF, unparseable.
"""

from __future__ import annotations


class PdfError(RuntimeError):
    """Fetching or mining an open-access PDF failed.

    Callers treat this as "unavailable", never as a crash: the detail panel
    shows no figure strip, the researcher's full read degrades to the
    summary form — the same graceful degradation as a missing ar5iv render.
    """
