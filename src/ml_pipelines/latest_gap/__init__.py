"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
Training pipeline for the adaptive latest-band boundary (the landmark→latest gap).

``collect.py`` pulls each corpus seed's landmark-era citer-year distribution
from OpenAlex, ``train.py`` fits the boundary rule on it and writes
``model.joblib`` (+ ``model.metadata.json``) beside it, which the app loads via
``atlas.services.graph.bands``. The boundary function itself is owned by the app
(``bands``) and imported here, so training and serving can't disagree. See
``src/ml_pipelines/latest_gap/README.md``.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""
