"""Ingestion: chunk a source's text, embed it locally, and store it.

``add_source`` is the core pipeline (chunk → embed → write to ``sources`` +
``chunks`` + ``chunks_vec`` in one transaction); ``ingest_pdf`` / ``ingest_url``
are thin wrappers that extract the text first.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from pathlib import Path
from uuid import uuid4

from ...config import config
from . import embeddings, extract, store
from .errors import SourceError

log = logging.getLogger(__name__)

ProgressFn = Callable[[int, int], None]
"""Ingestion progress callback: ``(chunks_embedded_so_far, total_chunks)``.
Called once with ``(0, total)`` when chunking finishes, then after every
embedding batch — embedding is where the time goes, so it's what a progress
bar should measure."""

# Chunks embedded per progress step. The encoder batches internally anyway;
# this only sets how often the callback (and any progress UI) ticks.
_EMBED_BATCH = 64


def add_source(
    title: str,
    kind: str,
    origin: str | None,
    page_texts: Sequence[tuple[int | None, str]],
    pages: int | None = None,
    on_progress: ProgressFn | None = None,
) -> dict:
    """Chunk, embed, and store a source's page texts.

    Args:
        title: Display title for the source.
        kind: ``"pdf"`` or ``"url"``.
        origin: Where it came from — the original filename or URL (or None).
        page_texts: ``[(page_no, text)]`` — page numbers are 1-based for PDFs and
            None for pageless sources (web pages).
        pages: Total page count (PDFs), or None.
        on_progress: Optional ``(done, total)`` callback, ticked per
            embedding batch (see ``ProgressFn``).

    Returns:
        The stored source record (see ``store.get_source``).

    Raises:
        SourceError: When the embedding model or sqlite-vec is unavailable,
            embedding fails, or chunking produced no text to index.
        sqlite3.Error: On database failures.
    """
    if not embeddings.available():
        raise SourceError("Embedding model unavailable — cannot ingest sources.")

    chunk_rows: list[tuple[int | None, str]] = []
    for page, text in page_texts:
        for chunk in extract.chunk_text(
            text, config.sources.chunking.chars, config.sources.chunking.overlap
        ):
            chunk_rows.append((page, chunk))
    if not chunk_rows:
        raise SourceError("No text to index after chunking.")

    texts = [chunk for _, chunk in chunk_rows]
    total = len(texts)
    if on_progress:
        on_progress(0, total)
    vectors: list[list[float]] = []
    for start in range(0, total, _EMBED_BATCH):
        batch = embeddings.embed_texts(texts[start : start + _EMBED_BATCH])
        if batch is None:
            raise SourceError("Embedding failed — cannot ingest sources.")
        vectors.extend(batch)
        if on_progress:
            on_progress(len(vectors), total)

    import sqlite_vec

    source_id = uuid4().hex
    with store.connect() as conn:
        if not store.HAS_VEC:
            raise SourceError("sqlite-vec unavailable — cannot store embeddings.")
        conn.execute(
            "INSERT INTO sources (id, title, kind, origin, pages, n_chunks) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (source_id, title, kind, origin, pages, len(chunk_rows)),
        )
        for (page, text), vector in zip(chunk_rows, vectors):
            cursor = conn.execute(
                "INSERT INTO chunks (source_id, page, text) VALUES (?, ?, ?)",
                (source_id, page, text),
            )
            conn.execute(
                "INSERT INTO chunks_vec (rowid, embedding) VALUES (?, ?)",
                (cursor.lastrowid, sqlite_vec.serialize_float32(vector)),
            )
    log.info("Ingested source %s (%s, %d chunks)", title, kind, len(chunk_rows))
    record = store.get_source(source_id)
    assert record is not None  # just inserted above
    return record


def ingest_pdf(
    path: str | Path, title: str | None = None, on_progress: ProgressFn | None = None
) -> dict:
    """Ingest a PDF file into the source library.

    Args:
        path: Filesystem path to the PDF.
        title: Display title; defaults to the filename stem.

    Returns:
        The stored source record.

    Raises:
        SourceError: When extraction or ingestion fails (see ``extract.extract_pdf``
            and ``add_source``).
    """
    path = Path(path)
    pages, total = extract.extract_pdf(path)
    return add_source(
        title or path.stem, "pdf", path.name, pages, pages=total, on_progress=on_progress
    )


def ingest_url(
    url: str, title: str | None = None, on_progress: ProgressFn | None = None
) -> dict:
    """Fetch a web page and ingest its readable text as a single source.

    Args:
        url: The page URL.
        title: Display title; defaults to the page's own ``<title>``, then the URL.

    Returns:
        The stored source record.

    Raises:
        SourceError: When the fetch or ingestion fails (see ``extract.fetch_url``
            and ``add_source``).
    """
    text, page_title = extract.fetch_url(url)
    return add_source(
        title or page_title or url, "url", url, [(None, text)], on_progress=on_progress
    )
