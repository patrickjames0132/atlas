"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
Lecture scoping: which nodes a lecture narrates, and in what order. Since
v7.17.0 the answer is "the ones the caller sent" — the reader's own on-screen
scope, after their filters and hand-picked selection — put in chronological
order, and nothing added to it.

This file used to pin the opposite contract: four mode buttons, each scoped
to exactly one graph relation *to the seed*, rebuilt here from the edge list
(v7.7.0). Those tests are gone with the modes. The one that mattered most
survives inverted, at the bottom: the paper a mode used to exclude is now
included, because the reader put it on screen.

This scoping lived in the orchestrator until v7.0.0, when that router was
deleted and the routes began calling agents directly — it is the lecturer's
own business, so it (and its tests) moved here.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

from atlas.agents.orchestrators.lecturer.main import _solo_subject, _story_nodes
from atlas.services.graph import Node


def make_node(node_id: str, title: str, **overrides) -> Node:
    fields = dict(
        id=node_id,
        arxiv_id=None,
        title=title,
        abstract=None,
        tldr=None,
        year=2015,
        month=None,
        pub_date=None,
        citation_count=100,
        authors=None,
        url=f"https://example.org/{node_id}",
        rels=["reference"],
        is_seed=False,
    )
    fields.update(overrides)
    return Node(**fields)


SEED = make_node("seed01", "Seed", is_seed=True, rels=[], year=2015)
NODES = [
    SEED,
    make_node("ref01", "Reference", year=1992, rels=["reference"]),
    make_node("cite01", "Landmark citer", year=2023, rels=["citation"]),
    make_node("late01", "Recent citer", year=2025, rels=["citation"]),
    make_node("simil01", "Undated Similar", year=None, rels=["similar"]),
]


def test_every_scoped_node_is_narrated_whatever_its_relation():
    """The whole change in one assertion. A lecture's subject is the scope, so
    no node is dropped for carrying the "wrong" relation tag — references,
    citers and loosely-similar work all narrate together if that is what the
    reader has on screen. Order is chronological, undated last."""
    scoped = [node.id for node in _story_nodes(SEED, NODES)]
    assert scoped == ["ref01", "seed01", "cite01", "late01", "simil01"]


def test_undated_nodes_sort_last():
    """An undated paper can't be placed in the timeline, so it goes to the end
    rather than being dropped or sorted as year zero."""
    nodes = [
        SEED,
        make_node("ref-old", "Old ref", year=1990),
        make_node("ref-nd", "Undated ref", year=None),
    ]
    assert [node.id for node in _story_nodes(SEED, nodes)] == ["ref-old", "seed01", "ref-nd"]


def test_the_seed_is_NOT_added_when_the_reader_scoped_around_it():
    """Nothing is added to the scope — the seed included.

    An earlier cut of v7.17.0 slotted the seed in when the scope arrived
    without it, on the theory that it anchors the prompt header and the figure
    pool. That is the override this whole change removed, in miniature: a
    reader who selects one paper wants a lecture on **that paper**, and
    quietly adding the seed turns it into a two-paper story about something
    they didn't ask about."""
    without_seed = [node for node in NODES if not node.is_seed]
    scoped = [node.id for node in _story_nodes(SEED, without_seed)]
    assert "seed01" not in scoped
    assert scoped == ["ref01", "cite01", "late01", "simil01"]


def test_an_empty_scope_falls_back_to_the_seed():
    """A lecture has to be about something, so the seed is the floor — but only
    when there is genuinely nothing scoped."""
    assert [node.id for node in _story_nodes(SEED, [])] == ["seed01"]


# --- the solo lecture ------------------------------------------------------


def test_a_scope_of_just_the_seed_is_solo():
    """One paper in scope is a request to teach that paper, which is what the
    retired INTUITION mode did. It is read off the scope, never chosen."""
    assert _solo_subject([SEED]) is SEED


def test_ANY_single_paper_is_the_solo_subject_not_only_the_seed():
    """The one thing the INTUITION mode could never do. It taught the seed and
    only the seed, so learning about a paper you found on the graph meant
    re-seeding the whole graph on it first. Select the node instead."""
    citer = make_node("cite01", "Landmark citer", year=2023, rels=["citation"])
    assert _solo_subject([citer]) is citer


def test_a_scope_with_two_papers_has_no_solo_subject():
    """Two papers make a story between papers, so a many-paper lecture runs."""
    assert _solo_subject([SEED, make_node("ref01", "Reference")]) is None


def test_an_empty_scope_is_solo_on_the_seed_after_the_fallback():
    """A reader who filtered everything away still gets a lecture: the seed is
    the fallback subject, and one paper means the solo lecture teaches it."""
    scoped = _story_nodes(SEED, [])
    assert _solo_subject(scoped) is SEED


# --- the v7.7.0 expanded-graph bug, inverted -------------------------------


def test_a_paper_expanded_off_a_reference_is_now_narrated_when_it_is_on_screen():
    """The inversion worth recording. `expand_node` tags a pulled-in paper with
    the relation it has to *the paper it was expanded from*, so a
    reference-of-a-reference carries `rels=["reference"]` while the seed never
    cited it. v7.7.0 read the edge list to keep that satellite OUT of the
    history lecture, because the mode claimed to narrate the seed's own
    references and would otherwise have lied.

    No mode makes that claim now. The lecture narrates what the reader scoped,
    and a satellite on screen was put there by the reader expanding a node —
    so excluding it would be the bug."""
    satellite = make_node("ref01-ref", "A reference OF the reference", year=1985)
    scoped = [node.id for node in _story_nodes(SEED, [*NODES, satellite])]
    assert "ref01-ref" in scoped
    assert scoped[0] == "ref01-ref"  # 1985, the oldest paper in scope
