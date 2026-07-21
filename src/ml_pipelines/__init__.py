"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
Offline ML training pipelines for arXiv Atlas.

Each sub-package trains a model the *app* then loads and serves. Nothing here is
imported by the running app or the quality gate — it's tooling, run on demand
(``python -m ml_pipelines.<pipeline>.train``) to (re)produce that pipeline's
``model.joblib`` artifact, which lives beside its code. The pipelines depend on
the app (for its feature contract and data-source clients); the app never depends
on them. See ``src/ml_pipelines/README.md``.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""
