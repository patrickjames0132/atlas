"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
Domain logic: the services that compose the integration clients + storage
into the app's actual features.

Each is its own package:

* ``graph``   — neighborhood-graph assembly (``build``) and its typed ``Graph``
  model (``model``).
* ``search``  — seed discovery: live S2 search + instant local-cache search.
* ``sources`` — the bring-your-own-sources subsystem (local ingestion,
  embedding, and hybrid retrieval of the user's material).

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""
