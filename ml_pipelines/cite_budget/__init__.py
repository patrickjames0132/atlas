"""Training pipeline for the adaptive landmark-budget model.

``collect.py`` pulls a labelled OpenAlex corpus, ``train.py`` fits a scikit-learn
model on it and writes ``ml_pipelines/models/cite_budget.joblib`` (+ ``metadata.json``),
which the app loads via ``atlas.services.graph.budget``. The feature contract is
owned by the app (``budget.compute_features``) and imported here, so training and
serving can't disagree. See ``ml_pipelines/cite_budget/README.md``.
"""
