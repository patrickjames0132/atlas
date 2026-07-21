"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
Device selection and graceful degradation in the local embedder (sources/embeddings.py).

Offline — no torch, no model download. ``sentence_transformers`` is injected into
``sys.modules`` as a fake, because ``_load_model`` imports it lazily *inside* the
function; that keeps these tests fast and lets them assert exactly which device
the real code asks for.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

import sys
import types

import pytest

from atlas.config import config
from atlas.services.sources import embeddings


@pytest.fixture(autouse=True)
def _reset_singletons():
    """Clear the cached model between tests — it's a process-wide singleton."""
    embeddings._model = None
    embeddings._load_failed = False
    yield
    embeddings._model = None
    embeddings._load_failed = False


class _FakeModel:
    """Stands in for a loaded SentenceTransformer, recording its device."""

    def __init__(self, model_id: str, device=None, fail_on=None):
        if fail_on is not None and device == fail_on:
            raise RuntimeError(f"no such device: {device}")
        self.model_id = model_id
        # Real sentence-transformers resolves device=None itself; "cpu" is a
        # stand-in for whatever it would have picked.
        self.device = device or "cpu"

    def get_embedding_dimension(self) -> int:
        return config.sources.embedding.dim


def _install_fake(monkeypatch, *, fail_on: str | None = None) -> list[str | None]:
    """Put a fake ``sentence_transformers`` in sys.modules; return the device log.

    Args:
        monkeypatch: pytest's monkeypatch fixture.
        fail_on: Device string whose construction should raise, simulating an
            unusable device.

    Returns:
        A list that receives the ``device`` argument of every construction
        attempt, in order.
    """
    attempted: list[str | None] = []

    def build(model_id, device=None, **kwargs):
        attempted.append(device)
        return _FakeModel(model_id, device=device, fail_on=fail_on)

    module = types.ModuleType("sentence_transformers")
    module.SentenceTransformer = build
    monkeypatch.setitem(sys.modules, "sentence_transformers", module)
    return attempted


@pytest.mark.parametrize("configured", ["auto", "AUTO", "  auto  ", ""])
def test_resolve_device_auto_delegates(monkeypatch, configured: str) -> None:
    """'auto' (any casing/padding) and empty defer to sentence-transformers' own pick."""
    monkeypatch.setattr(config.sources.embedding, "device", configured)
    assert embeddings._resolve_device() is None


@pytest.mark.parametrize("configured", ["cpu", "cuda", "cuda:1", "mps"])
def test_resolve_device_explicit_passes_through(monkeypatch, configured: str) -> None:
    """An explicit torch device string is handed to sentence-transformers verbatim."""
    monkeypatch.setattr(config.sources.embedding, "device", configured)
    assert embeddings._resolve_device() == configured


def test_load_model_uses_configured_device(monkeypatch) -> None:
    """The configured device reaches the SentenceTransformer constructor."""
    attempted = _install_fake(monkeypatch)
    monkeypatch.setattr(config.sources.embedding, "device", "cuda")

    model = embeddings._load_model()

    assert attempted == ["cuda"]
    assert model.device == "cuda"


def test_load_model_falls_back_to_cpu_when_device_unusable(monkeypatch) -> None:
    """A configured-but-broken device degrades to CPU instead of killing search."""
    attempted = _install_fake(monkeypatch, fail_on="cuda")
    monkeypatch.setattr(config.sources.embedding, "device", "cuda")

    model = embeddings._load_model()

    # Tried the configured device first, then retried on CPU.
    assert attempted == ["cuda", "cpu"]
    assert model.device == "cpu"
    assert embeddings.available() is True


def test_load_model_auto_failure_does_not_retry(monkeypatch) -> None:
    """When 'auto' itself fails there's no better device to try — degrade to unavailable."""
    attempted = _install_fake(monkeypatch, fail_on=None)

    def explode(model_id, device=None, **kwargs):
        attempted.append(device)
        raise RuntimeError("torch is a smoking crater")

    sys.modules["sentence_transformers"].SentenceTransformer = explode
    monkeypatch.setattr(config.sources.embedding, "device", "auto")

    assert embeddings._load_model() is None
    assert attempted == [None]        # no pointless CPU retry — CPU *was* the fallback
    assert embeddings.available() is False


def test_semantic_disabled_never_loads(monkeypatch) -> None:
    """The master switch short-circuits before any import or device work."""
    attempted = _install_fake(monkeypatch)
    monkeypatch.setattr(config.sources, "semantic_enabled", False)

    assert embeddings._load_model() is None
    assert attempted == []
    assert embeddings.available() is False
