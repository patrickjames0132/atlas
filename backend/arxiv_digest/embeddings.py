"""Local text embeddings for semantic search, via sentence-transformers.

Revived from the digest era (Phase 3d). The model is loaded lazily and cached
process-wide the first time an embedding is actually needed, so importing this
module never pays the ~torch import + model-load cost. Everything degrades
gracefully: if sentence-transformers isn't installed or the model can't load,
`available()` returns False and callers report that instead of crashing.

Embeddings are L2-normalized, so a dot product equals cosine similarity — the
distance metric we configure on the sqlite-vec table.
"""

from __future__ import annotations

import logging
from typing import Optional

from . import config

log = logging.getLogger(__name__)

# Cached singletons. _model is the loaded SentenceTransformer; _load_failed flips
# True after a failed attempt so we don't retry (and re-log) on every query.
_model = None
_load_failed = False


def _load_model():
    """Return the cached model, loading it on first call. None if unavailable."""
    global _model, _load_failed
    if _model is not None or _load_failed:
        return _model
    if not config.SEMANTIC_ENABLED:
        _load_failed = True
        return None
    try:
        from sentence_transformers import SentenceTransformer

        log.info("Loading embedding model %s …", config.EMBED_MODEL)
        _model = SentenceTransformer(config.EMBED_MODEL)
        dim = _model.get_sentence_embedding_dimension()
        if dim != config.EMBED_DIM:
            log.warning(
                "Embedding model %s has dimension %d but config.EMBED_DIM=%d. "
                "Set ARXIV_EMBED_DIM=%d and re-ingest.",
                config.EMBED_MODEL, dim, config.EMBED_DIM, dim,
            )
        return _model
    except Exception:
        log.exception("Could not load embedding model %s", config.EMBED_MODEL)
        _load_failed = True
        return None


def available() -> bool:
    """True when the embedding model is usable (so semantic search can run)."""
    return _load_model() is not None


def embed_texts(texts: list[str], *, batch_size: int = 64) -> Optional[list[list[float]]]:
    """Embed a batch of documents. Returns None if the model is unavailable."""
    model = _load_model()
    if model is None or not texts:
        return None
    vecs = model.encode(
        texts,
        normalize_embeddings=True,
        convert_to_numpy=True,
        batch_size=batch_size,
        show_progress_bar=False,
    )
    return [v.tolist() for v in vecs]


def embed_query(text: str) -> Optional[list[float]]:
    """Embed a single search query. Returns None if the model is unavailable.

    Prepends config.EMBED_QUERY_PREFIX (empty by default) so asymmetric-retrieval
    models like bge-small get their expected query instruction, while stored
    passages (embed_texts) stay un-prefixed."""
    result = embed_texts([config.EMBED_QUERY_PREFIX + text])
    return result[0] if result else None
