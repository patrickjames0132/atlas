"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
Mode scoping: which visible nodes each lecture mode may narrate, and in what
order. A lecture never expands the graph, and each directional mode is pinned
to exactly ONE graph relation **to the seed** so the four lectures don't
overlap.

The "to the seed" part is the whole of v7.7.0: scoping reads *edges* now, not
node tags, because a tag says what a relation is and never what it is to.

This scoping lived in the orchestrator until v7.0.0, when that router was
deleted and the routes began calling agents directly — it is the lecturer's
own business, so it (and its tests) moved here.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

from atlas.agents.models import LectureMode
from atlas.agents.orchestrators.lecturer.main import _story_nodes
from atlas.services.graph import Edge, Node


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
    make_node("late01", "Latest", year=2025, rels=["latest"]),
    make_node("simil01", "Undated Similar", year=None, rels=["similar"]),
]
# A reference edge runs seed -> cited; citation/latest run citer -> seed.
EDGES = [
    Edge(source="seed01", target="ref01", type="reference"),
    Edge(source="cite01", target="seed01", type="citation"),
    Edge(source="late01", target="seed01", type="latest"),
]



def test_each_mode_is_scoped_to_one_relation():
    """History narrates the seed's references, evolution the landmark citers,
    frontier the Latest-Publications nodes. Loosely-similar work never enters
    a directional mode. Directional sets come back oldest-first (with the seed
    slotted by its own year); intuition stays on the seed alone; bridge sees
    everything, unsorted."""
    expected = {
        LectureMode.HISTORY: ["ref01", "seed01"],  # 1992, then the 2015 seed
        LectureMode.EVOLUTION: ["seed01", "cite01"],  # 2015 seed, then 2023
        LectureMode.FRONTIER: ["seed01", "late01"],  # 2015 seed, then 2025
        LectureMode.INTUITION: ["seed01"],  # the seed alone
        LectureMode.BRIDGE: ["seed01", "ref01", "cite01", "late01", "simil01"],
    }
    for mode, node_ids in expected.items():
        assert [node.id for node in _story_nodes(SEED, NODES, EDGES, mode)] == node_ids


def test_a_directional_mode_sorts_undated_nodes_last():
    """An undated paper carrying the relation's tag is still included, sorted
    to the end — it can't be placed in the timeline."""
    nodes = [
        SEED,
        make_node("ref-old", "Old ref", year=1990, rels=["reference"]),
        make_node("ref-nd", "Undated ref", year=None, rels=["reference"]),
    ]
    edges = [
        Edge(source="seed01", target="ref-old", type="reference"),
        Edge(source="seed01", target="ref-nd", type="reference"),
    ]
    scoped = _story_nodes(SEED, nodes, edges, LectureMode.HISTORY)
    # 1990, 2015 seed, then the undated reference last.
    assert [node.id for node in scoped] == ["ref-old", "seed01", "ref-nd"]


# --- the expanded-graph bug (v7.7.0) ---------------------------------------------


def test_a_paper_expanded_off_a_reference_is_not_part_of_the_seeds_history():
    """The bug this scoping exists to fix. `expand_node` tags a pulled-in paper
    with the relation it has to *the paper it was expanded from* — so a
    reference-of-a-reference carries `rels=["reference"]` and is, by tag alone,
    indistinguishable from something the seed actually cites. Playing the
    history lecture over an expanded graph narrated papers the seed had never
    cited. Edges know the difference; tags structurally cannot."""
    satellite = make_node("ref01-ref", "A reference OF the reference", year=1985)
    nodes = [*NODES, satellite]
    edges = [*EDGES, Edge(source="ref01", target="ref01-ref", type="reference")]

    scoped = [node.id for node in _story_nodes(SEED, nodes, edges, LectureMode.HISTORY)]
    assert scoped == ["ref01", "seed01"]  # the satellite is out, despite its tag
    # And the tag really is identical — the test would be meaningless otherwise.
    assert satellite.rels == ["reference"]


def test_scoping_is_direction_agnostic_about_which_way_an_edge_points():
    """The question is adjacency to the seed, not which way the arrow runs — so
    a relation whose direction is the other way round can't be silently
    mis-scoped. Both endpoints are checked."""
    nodes = [SEED, make_node("cite02", "Another citer", year=2024, rels=["citation"])]
    # Deliberately backwards from how build.py writes a citation edge.
    edges = [Edge(source="seed01", target="cite02", type="citation")]
    scoped = [node.id for node in _story_nodes(SEED, nodes, edges, LectureMode.EVOLUTION)]
    assert scoped == ["seed01", "cite02"]


def test_no_edges_falls_back_to_tag_scoping_rather_than_narrating_nothing():
    """A lecture that over-includes beats one with no papers in it. An empty
    edge list means the caller couldn't say (an old client, a malformed
    payload), and scoping by tags is exactly the pre-v7.7.0 behavior."""
    assert [node.id for node in _story_nodes(SEED, NODES, [], LectureMode.HISTORY)] == [
        "ref01",
        "seed01",
    ]


def test_an_unrelated_edge_between_two_neighbours_does_not_widen_the_story():
    """Only edges touching the seed count. Two of its references citing each
    other is a real edge on a real graph, and says nothing about whether
    either belongs to a mode."""
    nodes = [SEED, make_node("ref02", "Another reference", year=1995, rels=["reference"])]
    edges = [Edge(source="ref01", target="ref02", type="reference")]
    assert [node.id for node in _story_nodes(SEED, nodes, edges, LectureMode.HISTORY)] == [
        "seed01"
    ]
