"""Shared fixtures for the arXiv Atlas test suite.

The suite is **fully offline** — no live arXiv / Semantic Scholar / Anthropic
calls, and no touching the real ``data/`` directory. The autouse ``_isolate``
fixture enforces that baseline for every test.

More shared fixtures (a scripted Anthropic client, deterministic offline
embeddings) arrive here alongside the modules they stand in for.
"""

from __future__ import annotations

import pytest

from arxiv_digest.config import config


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    """Point all storage at a per-test temp dir; disable the S2 throttle.

    The three DB paths derive from ``data_dir``, so one override relocates
    them all. Zeroing ``min_interval`` keeps tests from sleeping.
    """
    monkeypatch.setattr(config.storage, "data_dir", tmp_path)
    monkeypatch.setattr(config.s2, "min_interval", 0.0)
