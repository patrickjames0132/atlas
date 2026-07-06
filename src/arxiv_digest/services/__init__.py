"""Domain logic: the services that compose the integration clients + storage
into the app's actual features.

* ``graph``   — assemble a paper's neighborhood graph (S2 traversals, cached).
* ``search``  — seed discovery: live S2 search + instant local-cache search.
* ``sources`` — the bring-your-own-sources subsystem (its own subpackage:
  local ingestion, embedding, and hybrid retrieval of the user's material).
* ``model``   — the typed domain models the services produce (the graph
  ``Graph``/``Node``/``Edge``/…).
"""
