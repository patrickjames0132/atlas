"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
Mode scoping: which visible nodes each lecture mode may narrate, and in what
order. A lecture never expands the graph, and each directional mode is pinned
to exactly ONE graph relation so the four lectures don't overlap.

This scoping lived in the orchestrator until v7.0.0, when that router was
deleted and the routes began calling agents directly — it is the lecturer's
own business, so it (and its tests) moved here.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

from atlas.agents.models import LectureMode
from atlas.agents.orchestrators.lecturer.main import _story_nodes
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
    make_node("late01", "Latest", year=2025, rels=["latest"]),
    make_node("simil01", "Undated Similar", year=None, rels=["similar"]),
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
        assert [node.id for node in _story_nodes(SEED, NODES, mode)] == node_ids


def test_a_directional_mode_sorts_undated_nodes_last():
    """An undated paper carrying the relation's tag is still included, sorted
    to the end — it can't be placed in the timeline."""
    nodes = [
        SEED,
        make_node("ref-old", "Old ref", year=1990, rels=["reference"]),
        make_node("ref-nd", "Undated ref", year=None, rels=["reference"]),
    ]
    scoped = _story_nodes(SEED, nodes, LectureMode.HISTORY)
    # 1990, 2015 seed, then the undated reference last.
    assert [node.id for node in scoped] == ["ref-old", "seed01", "ref-nd"]
