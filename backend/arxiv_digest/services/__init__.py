"""Domain logic: the services that compose the integration clients + storage
into the app's actual features.

* ``graph``  — assemble a paper's neighborhood graph (S2 traversals, cached).
* ``search`` — seed discovery: live arXiv relevance search + instant search
  over the local snapshot cache.
"""
