"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
The model's label — the STOP rule — plus the notebook's cap grid.

Both halves of this model's contract are the **app's**, imported from
``atlas.services.graph.budget`` and re-exported here for the pipeline's use:

* the *features* (age, log-citations) — :func:`compute_features`, and
* the *label* — :func:`number_of_ranked_citers_before_a_single_year_overflows`,
  the **STOP rule**: how deep into a seed's citation-ranked citers you get before
  one publication year overflows :data:`PER_YEAR_CAP`. That function's docstring
  has the worked example; ``docs/landmark-vocabulary.md`` defines every term.

The label used to live here, as training-only code, on the reasoning that the app
only ever *predicts* it and never computes it. That stopped being true in v5.5.0:
the **live S2 fallback** holds its whole citer pool in memory before it trims (its
deep pager has already fetched it), so it runs the rule *directly* rather than
predicting it — and it runs the better **SKIP** variant, since with the pool in
hand nothing has to collapse to a scalar. The rule therefore moved into
``budget.py`` beside the features, and training reads it back from there. One
definition, no train/serve skew — the same arrangement the features have always
had.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

from atlas.services.graph.budget import (
    PER_YEAR_CAP,
    number_of_ranked_citers_before_a_single_year_overflows,
)

#: Cap grid stored alongside the label so the notebook can show the response
#: curve without re-fetching — the ``citers_before_overflow_cap{K}`` columns, of
#: which ``cap12`` equals the label column. Training-only: the app serves a
#: single cap (:data:`PER_YEAR_CAP`).
PER_YEAR_CAP_GRID = (4, 8, 12, 16, 20)

__all__ = [
    "PER_YEAR_CAP",
    "PER_YEAR_CAP_GRID",
    "number_of_ranked_citers_before_a_single_year_overflows",
]
