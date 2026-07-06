"""Neighborhood-graph assembly and its typed models.

* ``build``  — ``build_graph``: the assembly logic (S2 traversals, dedupe,
  typed edges, cached).
* ``model``  — the Pydantic ``Graph`` / ``Node`` / ``Edge`` / ``Seed`` /
  ``Counts`` the graph is made of.

Both are re-exported here, so callers use ``graph.build_graph(...)`` /
``graph.Graph`` without reaching into the submodules.
"""

from __future__ import annotations

from .build import build_graph
from .model import Counts, Edge, Graph, Node, Seed

__all__ = ["Counts", "Edge", "Graph", "Node", "Seed", "build_graph"]
