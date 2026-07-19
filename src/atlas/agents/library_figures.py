"""The shared heart of the two ``show_source_figure`` tools.

The researcher (graph Q&A) and the librarian (graph-free library chat) both
let the model attach a figure from the user's uploaded PDFs, addressed the
way passages are cited: source + page. Everything past each agent's own
budget checks is identical — resolve the address against the mined manifest
(``services.sources.figures``), dedupe repeats onto their existing marker,
assign the next ``<<FIG n>>`` slot, emit the ``FigureTrace``/``Figure``
events — so it lives here once, against a small structural protocol both
deps classes already satisfy.
"""

from __future__ import annotations

import logging
from typing import Protocol

from ..services.sources import figures as source_figures
from . import captions, events

log = logging.getLogger(__name__)


class FigureDeps(Protocol):
    """What attaching a library figure needs from an agent's run-state."""

    figures_left: int
    figures_shown: dict[tuple[str, int], int]

    def emit(self, event: events.Event) -> None:
        """Queue an event for the agent's stream bridge."""
        ...  # pragma: no cover — protocol signature only


def attach_source_figure(deps: FigureDeps, source_id: str, page: int, figure: int) -> str:
    """Attach one library figure to the answer, emitting its events.

    Args:
        deps: The calling agent's run-state (its own step budget, if any,
            is charged before this).
        source_id: The source's id.
        page: The 1-based page the figure is on.
        figure: Which figure on that page, 1-based.

    Returns:
        The tool-result text: the ``<<FIG n>>`` marker instruction on
        success, else a budget/validity message the model steers by (never
        raises).
    """
    try:
        resolution, problem = source_figures.resolve_page_figure(source_id, page, figure)
    except Exception:
        log.exception("show_source_figure mining failed")
        deps.emit(events.FigureTrace(ok=False, index=None, title=None, figure=figure))
        return f"Couldn't extract figures from source {source_id!r}."
    if resolution is None:
        deps.emit(events.FigureTrace(ok=False, index=None, title=None, figure=figure))
        return problem
    title = resolution["title"]
    if deps.figures_left <= 0:
        deps.emit(events.FigureTrace(ok=False, index=None, title=title, figure=figure))
        return "Figure budget spent — answer with the figures already shown."

    shown_key = (f"{source_id}:p{page}", figure)
    if shown_key in deps.figures_shown:
        deps.emit(events.FigureTrace(ok=True, index=None, title=title, figure=figure))
        return (
            f'That figure from "{title}" is already shown — its marker is '
            f"<<FIG {deps.figures_shown[shown_key]}>>."
        )
    slot = len(deps.figures_shown) + 1
    deps.figures_shown[shown_key] = slot
    deps.figures_left -= 1
    # The float's own designation ("Figure 12.4") heads the card and the
    # chip; the caption travels without it so it isn't shown twice.
    label, caption_text = captions.split_label(resolution["entry"].get("caption") or "")
    deps.emit(
        events.FigureTrace(ok=True, index=None, title=title, figure=figure, label=label)
    )
    deps.emit(
        events.Figure(
            image=f"/api/sources/{source_id}/figure/{resolution['manifest_index']}",
            caption=caption_text,
            title=title,
            index=None,
            figure=figure,
            slot=slot,
            label=label,
        )
    )
    # Echo what was actually attached: the caption is the model's only way
    # to notice it grabbed the wrong figure BEFORE describing it as
    # something it isn't (docs/bugs.md: the backup-diagrams incident).
    caption = (resolution["entry"].get("caption") or "(no caption)")[:150]
    kind = resolution["entry"].get("kind") or "figure"
    return (
        f'Attached the {kind} captioned "{caption}" (page {page} of "{title}") '
        f"to your answer. Place the marker <<FIG {slot}>> on its own line in "
        f"your prose at exactly the point where it belongs — and describe it "
        f"only as what its caption says it is. If this is not the figure you "
        f"meant, tell the student what it actually shows (it will render "
        f"regardless), or explain the intended figure in prose."
    )
