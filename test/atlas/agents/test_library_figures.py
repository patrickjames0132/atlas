"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
The shared ``show_source_figure`` core (agents/library_figures.py).

Focused on what the **trace chip** ends up saying, since that's what the user
reads when an attach fails: which source was reached into, and what was
actually asked for. The resolver and the store are faked — this is about the
events the helper emits, not about mining.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

import pytest

from atlas.agents import events, library_figures


class FakeDeps:
    """The minimal run-state ``attach_source_figure`` needs, plus a log."""

    def __init__(self, figures_left: int = 3) -> None:
        self.figures_left = figures_left
        self.figures_shown: dict[tuple[str, int], int] = {}
        self.emitted: list[events.Event] = []

    def emit(self, event: events.Event) -> None:
        """Record an event the helper queued."""
        self.emitted.append(event)


@pytest.fixture(autouse=True)
def _known_source(monkeypatch):
    """Every test's source id resolves to a titled source unless overridden."""
    monkeypatch.setattr(
        library_figures.source_store,
        "get_source",
        lambda source_id: {"title": "Feynman Lectures Vol. 3"} if source_id == "s1" else None,
    )


def traces(deps: FakeDeps) -> list[events.FigureTrace]:
    """Just the FigureTrace events, in order."""
    return [event for event in deps.emitted if isinstance(event, events.FigureTrace)]


def test_unresolvable_figure_still_names_the_source_and_the_attempt(monkeypatch):
    """The bug this file exists for: a failed attach used to emit title=None
    and no label, so the chip read a bare "Tried Figure 1" — naming neither
    the source nor the page it was reaching into."""
    monkeypatch.setattr(
        library_figures.source_figures,
        "resolve_page_figure",
        lambda source_id, page, figure: (None, "p.42 has no figures."),
    )
    deps = FakeDeps()
    message = library_figures.attach_source_figure(deps, "s1", page=42, figure=2)

    assert message == "p.42 has no figures."
    (trace,) = traces(deps)
    assert trace.ok is False
    assert trace.title == "Feynman Lectures Vol. 3"
    assert trace.label == "figure 2 on p.42"


def test_mining_failure_names_the_source_too(monkeypatch):
    """The resolver blowing up is still a failure the user should be able to
    read — same chip contract as a clean miss."""

    def explode(source_id, page, figure):
        raise RuntimeError("miner died")

    monkeypatch.setattr(library_figures.source_figures, "resolve_page_figure", explode)
    deps = FakeDeps()
    library_figures.attach_source_figure(deps, "s1", page=7, figure=1)

    (trace,) = traces(deps)
    assert trace.ok is False
    assert trace.title == "Feynman Lectures Vol. 3"
    assert trace.label == "figure 1 on p.7"


def test_unknown_source_degrades_to_an_unnamed_chip(monkeypatch):
    """A source id that resolves to nothing has no title to give — the chip
    drops the "of …" clause rather than inventing one, but still says what
    was attempted."""
    monkeypatch.setattr(
        library_figures.source_figures,
        "resolve_page_figure",
        lambda source_id, page, figure: (None, "No such source."),
    )
    deps = FakeDeps()
    library_figures.attach_source_figure(deps, "ghost", page=3, figure=1)

    (trace,) = traces(deps)
    assert trace.title is None
    assert trace.label == "figure 1 on p.3"


def test_a_title_lookup_failure_never_masks_the_real_problem(monkeypatch):
    """The title lookup is a nicety on an already-failing path — if it throws,
    the chip loses the name, not the error."""

    def explode(source_id):
        raise RuntimeError("db gone")

    monkeypatch.setattr(library_figures.source_store, "get_source", explode)
    monkeypatch.setattr(
        library_figures.source_figures,
        "resolve_page_figure",
        lambda source_id, page, figure: (None, "p.9 has no figures."),
    )
    deps = FakeDeps()
    message = library_figures.attach_source_figure(deps, "s1", page=9, figure=1)

    assert message == "p.9 has no figures."
    (trace,) = traces(deps)
    assert trace.title is None and trace.label == "figure 1 on p.9"


def test_spent_budget_names_the_source_it_resolved(monkeypatch):
    """The budget check runs *after* a successful resolve, so the real title
    is in hand — no lookup needed, and the attempt is still spelled out."""
    monkeypatch.setattr(
        library_figures.source_figures,
        "resolve_page_figure",
        lambda source_id, page, figure: (
            {"title": "Deep Learning", "manifest_index": 4, "entry": {"caption": ""}},
            "",
        ),
    )
    deps = FakeDeps(figures_left=0)
    library_figures.attach_source_figure(deps, "s1", page=5, figure=1)

    (trace,) = traces(deps)
    assert trace.ok is False
    assert trace.title == "Deep Learning"
    assert trace.label == "figure 1 on p.5"


def test_success_prefers_the_floats_own_designation(monkeypatch):
    """When the caption carries the book's own number, that's what the chip
    shows — "Figure 3-2" beats "figure 1 on p.42"."""
    monkeypatch.setattr(
        library_figures.source_figures,
        "resolve_page_figure",
        lambda source_id, page, figure: (
            {
                "title": "Feynman Lectures Vol. 3",
                "manifest_index": 4,
                "entry": {"caption": "Figure 3-2. Two-slit interference."},
            },
            "",
        ),
    )
    deps = FakeDeps()
    library_figures.attach_source_figure(deps, "s1", page=42, figure=1)

    (trace,) = traces(deps)
    assert trace.ok is True
    assert trace.label == "Figure 3-2"


def test_success_without_a_designation_falls_back_to_the_attempt(monkeypatch):
    """A caption with no designation of its own leaves the chip describing the
    address — never a bare "Figure 1", which names a figure the source
    probably numbers differently (`figure` is a page-local ordinal)."""
    monkeypatch.setattr(
        library_figures.source_figures,
        "resolve_page_figure",
        lambda source_id, page, figure: (
            {
                "title": "Feynman Lectures Vol. 3",
                "manifest_index": 4,
                "entry": {"caption": "Two-slit interference."},
            },
            "",
        ),
    )
    deps = FakeDeps()
    library_figures.attach_source_figure(deps, "s1", page=42, figure=2)

    (trace,) = traces(deps)
    assert trace.ok is True
    assert trace.label == "figure 2 on p.42"
    # The card itself keeps an honest empty label — the fallback is chip-only,
    # so no synthetic designation heads the image.
    (figure_event,) = [event for event in deps.emitted if isinstance(event, events.Figure)]
    assert figure_event.label is None


def test_a_repeat_reuses_the_marker_and_still_reads_clearly(monkeypatch):
    """Asking twice returns the existing marker; the chip says what was asked
    for rather than falling back to the bare ordinal."""
    monkeypatch.setattr(
        library_figures.source_figures,
        "resolve_page_figure",
        lambda source_id, page, figure: (
            {"title": "Deep Learning", "manifest_index": 4, "entry": {"caption": ""}},
            "",
        ),
    )
    deps = FakeDeps()
    library_figures.attach_source_figure(deps, "s1", page=5, figure=1)
    message = library_figures.attach_source_figure(deps, "s1", page=5, figure=1)

    assert "already shown" in message and "<<FIG 1>>" in message
    assert traces(deps)[-1].label == "figure 1 on p.5"
