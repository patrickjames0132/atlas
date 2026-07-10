"""Offline ML training pipelines for arXiv Atlas.

Each sub-package trains a model the *app* then loads and serves. Nothing here is
imported by the running app or the quality gate — it's tooling, run on demand
(``python -m ml.<pipeline>.train``) to (re)produce an artifact under
``ml_pipelines/models/``. The pipelines depend on the app (for its feature contract and
data-source clients); the app never depends on them. See ``ml/README.md``.
"""
