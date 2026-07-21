"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
Local text embeddings for semantic search, via sentence-transformers.

The model is loaded lazily and cached process-wide the first time an embedding is
actually needed, so importing this module never pays the (large) torch import +
model-load cost. Everything degrades gracefully: if sentence-transformers isn't
installed or the model can't load, ``available()`` returns False and callers
report that instead of crashing.

Embeddings are L2-normalized, so a dot product equals cosine similarity — the
distance metric configured on the sqlite-vec table (see ``store``).

The model runs on whatever ``config.sources.embedding.device`` selects — by
default "auto", i.e. sentence-transformers' own detection, which lands on the
GPU when torch has a CUDA build. Ingest is where that matters: it embeds
thousands of chunks in batches, while a single query embedding is dominated by
overhead either way.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

import logging

from ...config import config

log = logging.getLogger(__name__)

# Cached singletons. `_model` is the loaded SentenceTransformer; `_load_failed`
# flips True after a failed attempt so we don't retry (and re-log) every query.
_model = None
_load_failed = False


def _resolve_device() -> str | None:
    """Turn ``config.sources.embedding.device`` into a device for sentence-transformers.

    "auto" (the default) deliberately resolves to None — which tells
    sentence-transformers to run its own detection. That's better than a
    hand-rolled ``torch.cuda.is_available()`` ladder here: it already knows
    about cuda, mps, xpu and npu, and it stays right as torch grows new
    backends. We only override when the config names a device explicitly.

    Returns:
        The configured torch device string, or None to let sentence-transformers
        choose.
    """
    configured = config.sources.embedding.device.strip()
    if not configured or configured.lower() == "auto":
        return None
    return configured


def _load_model():
    """Load (or return the cached) sentence-transformers model.

    The first call pays the torch import + model download/load; afterwards the
    singleton is returned. A failed load is remembered so subsequent calls don't
    retry (and re-log) on every query. Also warns when the model's embedding
    dimension disagrees with ``config.sources.embedding.dim``.

    An explicitly configured device that won't load (a CUDA build without a GPU,
    a typo, a busy device) falls back to CPU rather than taking semantic search
    down with it — slow beats unavailable.

    Returns:
        The loaded ``SentenceTransformer``, or None when semantic search is
        disabled, the package is missing, or the model failed to load.
    """
    global _model, _load_failed
    if _model is not None or _load_failed:
        return _model
    if not config.sources.semantic_enabled:
        _load_failed = True
        return None
    model_id = config.sources.embedding.model
    try:
        from sentence_transformers import SentenceTransformer

        device = _resolve_device()
        log.info("Loading embedding model %s (device=%s) …", model_id, device or "auto")
        try:
            _model = SentenceTransformer(model_id, device=device)
        except Exception:
            if device is None:
                raise
            log.exception(
                "Could not load embedding model %s on configured device %r; "
                "falling back to CPU. Set config.sources.embedding.device to a "
                "valid torch device (or 'auto') to silence this.",
                model_id, device,
            )
            _model = SentenceTransformer(model_id, device="cpu")
        log.info("Embedding model %s ready on device %s", model_id, _model.device)
        dim = _model.get_embedding_dimension()
        if dim != config.sources.embedding.dim:
            log.warning(
                "Embedding model %s has dimension %d but config.sources.embedding.dim=%d. "
                "Set the config to %d and re-ingest existing sources.",
                model_id, dim, config.sources.embedding.dim, dim,
            )
        return _model
    except Exception:
        log.exception("Could not load embedding model %s", model_id)
        _load_failed = True
        return None


def available() -> bool:
    """Report whether the embedding model is usable.

    Note the first call may be slow — it triggers the lazy model load.

    Returns:
        True when the model loaded (so semantic search can run); False when
        disabled or the load failed.
    """
    return _load_model() is not None


def embed_texts(texts: list[str], *, batch_size: int = 64) -> list[list[float]] | None:
    """Embed a batch of documents.

    Args:
        texts: The passages to embed (stored chunks — no query prefix).
        batch_size: Encoder batch size.

    Returns:
        One L2-normalized vector per input text (so dot product = cosine
        similarity), or None when the model is unavailable or ``texts`` is empty.
    """
    model = _load_model()
    if model is None or not texts:
        return None
    vectors = model.encode(
        texts,
        normalize_embeddings=True,
        convert_to_numpy=True,
        batch_size=batch_size,
        show_progress_bar=False,
    )
    return [vector.tolist() for vector in vectors]


def embed_query(text: str) -> list[float] | None:
    """Embed a single search query.

    Prepends ``config.sources.embedding.query_prefix`` (empty by default) so
    asymmetric-retrieval models like bge-small get their expected query
    instruction, while stored passages (``embed_texts``) stay un-prefixed.

    Args:
        text: The query text.

    Returns:
        The L2-normalized query vector, or None when the model is unavailable.
    """
    result = embed_texts([config.sources.embedding.query_prefix + text])
    return result[0] if result else None
