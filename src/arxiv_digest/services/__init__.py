"""Domain logic: the services that compose the integration clients + storage
into the app's actual features.

* ``graph``  — assemble a paper's neighborhood graph (S2 traversals, cached).
* ``search`` — seed discovery. Not yet ported; being rebuilt on Semantic
  Scholar (replacing the current arXiv-search path) with Claude-based query
  expansion for acronym/jargon gaps.
"""
