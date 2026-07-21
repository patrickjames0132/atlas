"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
The shared heart of the two ``show_source_figure`` tools.

The researcher (graph Q&A) and the librarian (graph-free library chat) both
let the model attach a figure from the user's uploaded PDFs, addressed the
way passages are cited: source + page. Everything past each agent's own
budget checks is identical — resolve the address against the mined manifest
(``services.sources.figures``), dedupe repeats onto their existing marker,
assign the next ``<<FIG n>>`` slot, emit the ``FigureTrace``/``Figure``
events — so it lives here once, against a small structural protocol both
deps classes already satisfy.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

import logging
from typing import Protocol

from ..services.sources import figures as source_figures
from ..services.sources import store as source_store
from . import captions, events

log = logging.getLogger(__name__)


class FigureDeps(Protocol):
    """What attaching a library figure needs from an agent's run-state."""

    figures_left: int
    figures_shown: dict[tuple[str, int], int]

    def emit(self, event: events.Event) -> None:
        """Queue an event for the agent's stream bridge."""
        ...  # pragma: no cover — protocol signature only


def _source_title(source_id: str) -> str | None:
    """The source's display title, for a trace chip — None when unknowable.

    A failed attach still has to say *which* source it was reaching into, and
    the failure paths below run before (or instead of) a successful
    resolution, so the title isn't in hand. Looking it up is one local SQLite
    read on a path that's already an error, and any failure here degrades to
    an unnamed chip rather than masking the original problem.

    Args:
        source_id: The source's id, as the model gave it.

    Returns:
        The source's title, or None when no such source exists (or the
        lookup itself fails).
    """
    try:
        source = source_store.get_source(source_id)
    except Exception:
        log.warning("source title lookup failed for %r", source_id, exc_info=True)
        return None
    return source["title"] if source else None


def _attempted_label(page: int, figure: int) -> str:
    """What the model asked for, in words — the chip's label when no float
    designation is available.

    ``figure`` addresses a **page-local** ordinal ("the 2nd figure on p.42"),
    not the book's own numbering, so the bare fallback the chip used to draw
    ("Figure 2") named a figure the source may well call something else. This
    says what was actually attempted.

    Args:
        page: The 1-based page the figure was addressed on.
        figure: Which figure on that page, 1-based.

    Returns:
        E.g. ``"figure 2 on p.42"``.
    """
    return f"figure {figure} on p.{page}"


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
    attempted = _attempted_label(page, figure)
    try:
        resolution, problem = source_figures.resolve_page_figure(source_id, page, figure)
    except Exception:
        log.exception("show_source_figure mining failed")
        deps.emit(
            events.FigureTrace(
                ok=False, index=None, title=_source_title(source_id),
                figure=figure, label=attempted,
            )
        )
        return f"Couldn't extract figures from source {source_id!r}."
    if resolution is None:
        deps.emit(
            events.FigureTrace(
                ok=False, index=None, title=_source_title(source_id),
                figure=figure, label=attempted,
            )
        )
        return problem
    title = resolution["title"]
    if deps.figures_left <= 0:
        deps.emit(
            events.FigureTrace(
                ok=False, index=None, title=title, figure=figure, label=attempted
            )
        )
        return "Figure budget spent — answer with the figures already shown."

    shown_key = (f"{source_id}:p{page}", figure)
    if shown_key in deps.figures_shown:
        # A repeat: the float's own designation isn't in hand here (no
        # resolution was re-read), so the chip says what was asked for.
        deps.emit(
            events.FigureTrace(
                ok=True, index=None, title=title, figure=figure, label=attempted
            )
        )
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
        events.FigureTrace(
            ok=True, index=None, title=title, figure=figure, label=label or attempted
        )
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
