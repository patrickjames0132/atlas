"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
Splitting a float's own label ("Figure 12.4") off the front of its caption.

Mined and ar5iv captions arrive as one string — ``"Figure 12.4: The forward
view. …"`` — but the UI wants the two halves separately: the label goes in
the figure card's heading and the trace chips ("Showed **Figure 12.4** of
…"), the remainder stays the caption text. Splitting here, server-side,
keeps the two agents' ``Figure`` events consistent and spares the frontend a
parsing job it would have to duplicate across card, chip, and lightbox.

Not every caption carries a label (a web figure, a caption the miner
truncated oddly) — ``split_label`` then returns ``None`` and the frontend
falls back to numbering attachments in answer order ("Figure 1", "Figure 2"
by slot).

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

import re

# The float's own designation at the head of its caption: a kind word, a
# number ("3", "12.4", "A.2", "S1", "3a", "3-2"), then the caption's separator
# (":" or ".") or — Algorithm captions often use neither — a space into the
# title.
#
# Chapter-hyphenated numbering ("Figure 3-2", and the en/em-dash forms
# typesetters use for it) is as common as the dotted kind — the Feynman
# Lectures are entirely hyphenated. Matching only dots truncated those to
# "Figure 3" *and* left the remainder starting with a stray "-2.", so the
# chip named a different figure than the one on screen. A separator only
# counts when digits follow it immediately: "Figure 3 - A slit" keeps its
# dash in the caption, where it belongs.
_LABEL_RE = re.compile(
    r"^(?P<kind>Figure|Fig\.?|Table|Algorithm)\s+"
    r"(?P<number>(?:[A-Za-z]\.)?\d+(?:[.\-\u2013\u2014]\d+)*[a-z]?)"
    r"\s*(?P<separator>[:.])?\s*"
)

# "Fig. 3" and "Figure 3" are the same designation; display the long form.
_KIND_DISPLAY = {"fig": "Figure", "fig.": "Figure"}


def split_label(caption: str) -> tuple[str | None, str]:
    """Split a caption into the float's own label and the remaining text.

    Args:
        caption: The full caption as mined/extracted (may be empty).

    Returns:
        ``(label, rest)`` — e.g. ``("Figure 12.4", "The forward view. …")``.
        ``label`` is None (and ``rest`` the input unchanged) when the caption
        doesn't open with a recognizable designation.
    """
    match = _LABEL_RE.match(caption or "")
    if not match:
        return None, caption or ""
    kind = match.group("kind")
    kind = _KIND_DISPLAY.get(kind.lower(), kind)
    label = f"{kind} {match.group('number')}"
    return label, caption[match.end() :].strip()
