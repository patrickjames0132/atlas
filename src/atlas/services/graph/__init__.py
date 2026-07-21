"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
Neighborhood-graph assembly and its typed models.

* ``build``  — ``build_graph``: the assembly logic (single-provider traversals,
  dedupe, typed edges, cached). ``Provider`` names the backends it can build from.
* ``model``  — the Pydantic ``Graph`` / ``Node`` / ``Edge`` / ``Seed`` /
  ``Counts`` the graph is made of.

Both are re-exported here, so callers use ``graph.build_graph(...)`` /
``graph.Graph`` without reaching into the submodules.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

from .build import Provider, build_graph, resolve_provider
from .model import Counts, Edge, Graph, Node, Seed

__all__ = [
    "Counts", "Edge", "Graph", "Node", "Provider", "Seed", "build_graph", "resolve_provider",
]
