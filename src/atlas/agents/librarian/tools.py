"""The librarian's tool surface: its run-state (deps) and show_source_figure.

One tool, deliberately: the librarian stays the lightweight retrieve-then-
answer path — no graph, no searches — but since v5.28.0 it can attach real
figures from the user's uploaded PDFs, the same way the researcher does. The
tool follows the researchers' one hard rule: **failures are reported in the
tool-result text, never raised** — steerable information, not a dead answer.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic_ai import RunContext

from .. import events, library_figures
from .config import BUDGETS


@dataclass
class LibrarianDeps:
    """One answer's run-state: the event queue and the figure budget.

    The ``queue`` is how tool-side happenings reach the workflow's event
    stream — the same push/drain bridge as the researcher's deps, just far
    smaller (the librarian has one tool and one budget).
    """

    figures_left: int = 0
    figures_shown: dict[tuple[str, int], int] = field(default_factory=dict)
    queue: list[events.Event] = field(default_factory=list)

    def emit(self, event: events.Event) -> None:
        """Queue a trace/figure event for the stream bridge to flush.

        Args:
            event: The typed event to queue.
        """
        self.queue.append(event)

    def drain(self) -> list[events.Event]:
        """Take (and clear) everything queued since the last drain.

        Returns:
            The queued events, oldest first.
        """
        queued, self.queue = self.queue, []
        return queued


def make_deps() -> LibrarianDeps:
    """Fresh run-state for one answer, budgets loaded from config.

    Returns:
        The deps, with the figure budget primed.
    """
    return LibrarianDeps(figures_left=BUDGETS["figures"])


def show_source_figure(
    ctx: RunContext[LibrarianDeps], source_id: str, page: int, figure: int = 1
) -> str:
    """Place a figure/table from one of the student's uploaded sources into
    your answer. Use it when a passage you're citing refers to a figure the
    student would benefit from seeing. The result gives you a <<FIG n>>
    marker: put it on its own line in your prose exactly where the figure
    belongs.

    Args:
        ctx: The run context carrying the librarian's deps (framework-injected).
        source_id: The source's id, as listed with the passages.
        page: The 1-based page the figure is on (usually the cited
            passage's page).
        figure: Which figure on that page, 1-based, when it has several.

    Returns:
        The ``<<FIG n>>`` marker to place in your prose, or a
        budget/validity message (a page with no figures lists the source's
        pages that do have them).
    """
    return library_figures.attach_source_figure(ctx.deps, source_id, page, figure)
