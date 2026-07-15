"""The model's label — the density budget ``n*`` — plus the notebook's K-grid.

Both halves of this model's contract are the **app's**, imported from
``atlas.services.graph.budget`` and re-exported here for the pipeline's use:

* the *features* (age, log-citations) — :func:`compute_features`, and
* the *label* (the density budget ``n*``) — :func:`density_budget`, with its
  per-year cap :data:`DENSITY_CAP`.

The label used to live here, as training-only code, on the reasoning that the app
only ever *predicts* ``n*`` and never computes it. That stopped being true in
v5.5.0: the **live S2 fallback** holds its whole citer pool in memory before it
trims (its deep pager has already fetched it), so it applies the density rule
*directly* rather than predicting it — the model is fit on all-time-ranked
landmarks and that path's pool is recency-capped, so the prediction doesn't
transfer. The rule therefore moved into ``budget.py`` beside the features, and
training reads it back from there. One definition, no train/serve skew — the same
arrangement the features have always had.

See ``atlas.services.graph.budget.density_budget`` for what ``n*`` is and why it
measures clutter, and this package's README for the derivation.
"""

from __future__ import annotations

from atlas.services.graph.budget import DENSITY_CAP, density_budget

#: K-grid stored alongside the label so the notebook can show the response
#: curve without re-fetching — ``n_star_k{K}`` columns; k12 equals the label.
#: Training-only: the app serves a single cap (:data:`DENSITY_CAP`).
DENSITY_CAP_GRID = (4, 8, 12, 16, 20)

__all__ = ["DENSITY_CAP", "DENSITY_CAP_GRID", "density_budget"]
