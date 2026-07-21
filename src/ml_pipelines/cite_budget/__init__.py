"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
Training pipeline for the adaptive landmark-budget model.

``collect.py`` pulls a labelled OpenAlex corpus, ``train.py`` fits a scikit-learn
model on it and writes ``model.joblib`` (+ ``model.metadata.json``) beside it,
which the app loads via ``atlas.services.graph.budget``. The feature contract is
owned by the app (``budget.compute_features``) and imported here, so training and
serving can't disagree. See ``src/ml_pipelines/cite_budget/README.md``.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""
