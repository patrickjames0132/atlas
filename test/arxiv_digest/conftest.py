"""Shared fixtures for the arXiv Atlas test suite.

The suite is **fully offline** — no live arXiv / Semantic Scholar / Anthropic
calls, and no touching the real ``data/`` directory. The autouse ``_isolate``
fixture enforces that baseline for every test. ``stub_embeddings`` swaps the
sentence-transformers model for a cheap deterministic hash embedder so the
sources pipeline can be tested without loading torch.

More shared fixtures (a scripted Anthropic client) arrive here alongside the
modules they stand in for.
"""

from __future__ import annotations

import hashlib
import math

import pytest

from arxiv_digest.config import config
from arxiv_digest.services.sources import embeddings


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    """Point all storage at a per-test temp dir; disable the S2 throttle.

    The three DB paths derive from ``data_dir``, so one override relocates
    them all. Zeroing ``min_interval`` keeps tests from sleeping.
    """
    monkeypatch.setattr(config.storage, "data_dir", tmp_path)
    monkeypatch.setattr(config.s2, "min_interval", 0.0)


# --- deterministic offline embeddings -----------------------------------------

def _hash_vector(text: str, dim: int) -> list[float]:
    """A cheap deterministic unit vector derived from the text's words.

    Not semantically meaningful — but identical texts embed identically and
    shared tokens overlap, which is enough to test storage, scoping, and ranking
    plumbing without loading a model.
    """
    vector = [0.0] * dim
    for word in text.lower().split():
        hashed = int.from_bytes(hashlib.md5(word.encode()).digest()[:4], "big")
        vector[hashed % dim] += 1.0
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]


@pytest.fixture()
def stub_embeddings(monkeypatch):
    """Replace the sentence-transformers embedder with the hash embedder."""
    dim = config.sources.embedding.dim
    prefix = config.sources.embedding.query_prefix
    monkeypatch.setattr(embeddings, "available", lambda: True)
    monkeypatch.setattr(
        embeddings, "embed_texts",
        lambda texts, **kw: [_hash_vector(text, dim) for text in texts] or None,
    )
    monkeypatch.setattr(
        embeddings, "embed_query",
        lambda text: _hash_vector(prefix + text, dim),
    )
