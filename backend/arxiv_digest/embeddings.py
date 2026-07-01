"""Text embeddings for semantic search, via sentence-transformers.

The model is loaded lazily and cached process-wide the first time an embedding
is actually needed, so importing this module (or running the lexical-only paths)
never pays the ~torch import + model-load cost. Everything degrades gracefully:
if sentence-transformers isn't installed or the model can't load, `available()`
returns False and callers fall back to lexical search.

Embeddings are L2-normalized, so a dot product equals cosine similarity — which
is also the distance metric we configure on the sqlite-vec table.
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
                "Set ARXIV_EMBED_DIM=%d and re-embed (run.py embed --rebuild).",
                config.EMBED_MODEL,
                dim,
                config.EMBED_DIM,
                dim,
            )
        return _model
    except Exception:
        log.exception("Could not load embedding model %s", config.EMBED_MODEL)
        _load_failed = True
        return None


def available() -> bool:
    """True when the embedding model is usable (so semantic search can run)."""
    return _load_model() is not None


def embed_texts(texts: list[str]) -> Optional[list[list[float]]]:
    """Embed a batch of documents. Returns None if the model is unavailable."""
    model = _load_model()
    if model is None or not texts:
        return None
    vecs = model.encode(
        texts,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
    )
    return [v.tolist() for v in vecs]


def embed_query(text: str) -> Optional[list[float]]:
    """Embed a single search query. Returns None if the model is unavailable."""
    result = embed_texts([text])
    return result[0] if result else None


def document_text(paper: dict) -> str:
    """The text we embed for a paper: title carries the most signal, then the
    abstract. Authors are left out (they add noise for topical similarity)."""
    title = paper.get("title") or ""
    abstract = paper.get("abstract") or ""
    return f"{title}\n\n{abstract}".strip()
