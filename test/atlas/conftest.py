"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
Shared fixtures for the arXiv Atlas test suite.

The suite is **fully offline** — no live arXiv / Semantic Scholar / Anthropic
calls, and no touching the real ``data/`` directory. The autouse ``_isolate``
fixture enforces that baseline for every test, and PydanticAI's
``ALLOW_MODEL_REQUESTS`` kill switch (flipped off below, process-wide) makes
any un-overridden agent run raise before it can touch the network — agent
tests swap in ``TestModel`` / ``FunctionModel`` via ``agent.override(...)``.
``stub_embeddings`` swaps the sentence-transformers model for a cheap
deterministic hash embedder so the sources pipeline can be tested without
loading torch.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

import hashlib
import math

import pytest
from pydantic_ai import models as ai_models

from atlas.agents.orchestrators.researcher import config as researcher_config
from atlas.config import config
from atlas.services.sources import embeddings

# Hard guard: no live LLM calls, ever. Any agent run that reaches a real model
# raises RuntimeError instead of making a request.
ai_models.ALLOW_MODEL_REQUESTS = False


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    """Point all storage at a per-test temp dir; disable the S2 throttle.

    The three DB paths derive from ``data_dir``, so one override relocates
    them all. Zeroing the ``min_interval`` throttles keeps tests from sleeping.

    The offline S2 citations corpus is forced **off** (``s2_corpus`` nulled). A
    real corpus in config.json would otherwise make citation tests query the
    machine's live one — in the two-root era this isolation once leaked when
    only one root was nulled and the corpus tests wrote their synthetic
    release into the real (mid-ingest) Parquet root. A corpus test opts back
    in by pointing the root at its own temp dir (see that package's conftest).

    Semantic search is forced **off** (``semantic_enabled``) for the same
    reason, and it is not theoretical: any test that reaches
    ``sources.retrieval.search`` — the researcher's ``search_sources`` tool,
    for one — would otherwise call the *real* embedder, download a
    sentence-transformers model, and run it. That silently made the suite
    non-offline on any machine with torch installed, and on Windows CI's CUDA
    build with no GPU it crashed the interpreter outright (access violation in
    ``torch/cuda/graphs.py``). Nothing here needs a real model: a test that
    wants embeddings takes ``stub_embeddings``, which patches
    ``available``/``embed_texts``/``embed_query`` directly and so is unaffected
    by this switch.
    """
    monkeypatch.setattr(config.storage, "data_dir", tmp_path)
    monkeypatch.setattr(config.storage, "s2_corpus", None)
    monkeypatch.setattr(config.sources, "semantic_enabled", False)
    # The web scout is forced **off**, for the third time and the same reason:
    # a capability configured on the developer's machine must not silently
    # become part of every test. Here it also changes what the researcher's
    # coverage guard demands — with the web on, every scripted `answered` turn
    # gets bounced for not searching it, which is correct behavior and pure
    # noise in a test about something else. A web test opts back in (see the
    # researcher package's tests) and stubs the scout.
    monkeypatch.setitem(researcher_config.BUDGETS, "web_searches", 0)
    monkeypatch.setattr(config.providers.s2, "min_interval", 0.0)
    monkeypatch.setattr(config.providers.openalex, "min_interval", 0.0)


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
