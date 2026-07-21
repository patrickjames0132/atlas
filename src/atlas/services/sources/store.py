"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
The sources store: SQLite schema, connection setup, and source-record CRUD.

Two data tables — ``sources`` (one row per uploaded doc) and ``chunks`` (its
text pieces) — plus two search indexes over the chunks that live alongside them:

* ``chunks_vec`` — a sqlite-vec virtual table for semantic (cosine KNN) search.
  sqlite-vec is a *loadable extension*, so it must be re-loaded on **every**
  connection; ``HAS_VEC`` records whether that succeeded.
* ``chunks_fts`` — an FTS5 external-content table for lexical search, kept in
  sync with ``chunks`` by triggers. FTS5 is a SQLite *compile-time* option, so
  it's probed once; ``HAS_FTS`` records whether it's available.

This is deliberately its own connection helper rather than the shared
``storage.connect`` — it needs per-connection extension loading, capability
probing, and conditional table creation that the generic helper doesn't do.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from ...config import config
from . import embeddings

log = logging.getLogger(__name__)


def pdf_dir() -> Path:
    """The directory keeping uploaded source PDFs (created on demand).

    The ingested *text* lives in the database; the original file is kept
    beside it (since v5.28.0) so figures can be mined from it later —
    ``data_dir/source_pdfs``, gitignored with the rest of ``data/``.

    Returns:
        The directory path.
    """
    directory = config.storage.data_dir / "source_pdfs"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def pdf_path(source_id: str) -> Path:
    """Where a source's original PDF lives (whether or not it exists).

    Sources ingested before v5.28.0 — and URL sources, which never had a
    file — simply have nothing at this path; callers treat that as "no
    figures", never an error.

    Args:
        source_id: The source's id.

    Returns:
        The file path.
    """
    return pdf_dir() / f"{source_id}.pdf"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    id         TEXT PRIMARY KEY,
    title      TEXT NOT NULL,
    kind       TEXT NOT NULL,               -- 'pdf' | 'url'
    origin     TEXT,                         -- filename or URL
    pages      INTEGER,                      -- page count (PDFs), else NULL
    n_chunks   INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS chunks (
    id        INTEGER PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    page      INTEGER,                       -- 1-based page (PDFs), else NULL
    text      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chunks_source ON chunks (source_id);
"""

# The FTS5 lexical index mirrors chunks.text via an external-content table kept
# in sync by triggers, so ingestion/deletion need no extra wiring. FTS5 is a
# SQLite compile-time option; when it's missing, lexical search is skipped.
_FTS_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    text, content='chunks', content_rowid='id', tokenize='porter unicode61'
);
CREATE TRIGGER IF NOT EXISTS chunks_fts_ai AFTER INSERT ON chunks BEGIN
    INSERT INTO chunks_fts (rowid, text) VALUES (new.id, new.text);
END;
CREATE TRIGGER IF NOT EXISTS chunks_fts_ad AFTER DELETE ON chunks BEGIN
    INSERT INTO chunks_fts (chunks_fts, rowid, text) VALUES ('delete', old.id, old.text);
END;
"""

# sqlite-vec (the vector index) is a loadable extension, reloaded on every
# connection (extensions are per-connection). None = not yet probed.
HAS_VEC: bool | None = None
# FTS5 support is a fixed property of the SQLite build; probed once, then cached.
HAS_FTS: bool | None = None


def _try_load_vec(conn: sqlite3.Connection) -> bool:
    """Load the sqlite-vec extension into a connection.

    Extensions are per-connection, so this runs on every ``connect``.

    Args:
        conn: The open SQLite connection.

    Returns:
        True when the extension loaded; False when sqlite-vec is missing or the
        load failed (logged, not raised — the app degrades gracefully).
    """
    try:
        import sqlite_vec

        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
        return True
    except Exception:
        log.exception("Could not load sqlite-vec")
        return False


def _try_setup_fts(conn: sqlite3.Connection) -> bool:
    """Ensure the FTS5 lexical index and its sync triggers exist.

    Creates the external-content ``chunks_fts`` table plus the insert/delete
    triggers that keep it mirrored to ``chunks``. On first creation over an
    existing library it back-fills the index from the current chunks with an
    FTS5 ``rebuild`` so previously-ingested sources become lexically searchable.

    Args:
        conn: The open SQLite connection.

    Returns:
        True when FTS5 is available and set up; False when FTS5 isn't compiled
        into this SQLite build (logged, not raised — lexical search is then
        skipped and retrieval falls back to pure vector KNN).
    """
    try:
        existed = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='chunks_fts'"
        ).fetchone()
        conn.executescript(_FTS_SCHEMA)
        if not existed:
            # Freshly created (new library, or migrating one built before hybrid
            # search) — populate from the chunks already stored.
            conn.execute("INSERT INTO chunks_fts (chunks_fts) VALUES ('rebuild')")
        return True
    except sqlite3.OperationalError:
        log.warning("FTS5 unavailable — lexical search disabled")
        return False


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    """Open a connection to the sources library, committing on clean exit.

    Ensures the schema exists, loads sqlite-vec (recording the result in
    ``HAS_VEC``), creates the vector table when the extension is available, and
    sets up the FTS5 lexical index (recording ``HAS_FTS``).

    Yields:
        An open ``sqlite3.Connection`` with ``Row`` as its row factory and
        foreign keys enabled.

    Raises:
        sqlite3.Error: On database failures.
    """
    global HAS_VEC, HAS_FTS
    config.storage.ensure_dirs()
    conn = sqlite3.connect(config.storage.sources_db, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        HAS_VEC = _try_load_vec(conn)
        conn.executescript(_SCHEMA)
        if HAS_VEC:
            conn.execute(
                f"CREATE VIRTUAL TABLE IF NOT EXISTS chunks_vec USING vec0("
                f"embedding float[{config.sources.embedding.dim}] distance_metric=cosine)"
            )
        HAS_FTS = _try_setup_fts(conn)
        yield conn
        conn.commit()
    finally:
        conn.close()


def available() -> bool:
    """Report whether the source library is fully usable.

    Returns:
        True when both the embedding model and sqlite-vec load. Note the first
        call may be slow — it triggers the lazy embedding-model load.
    """
    if not embeddings.available():
        return False
    with connect():
        return bool(HAS_VEC)


def _source_row(row: sqlite3.Row) -> dict:
    """Convert a ``sources`` table row to the API's source record.

    Args:
        row: A row from the ``sources`` table.

    Returns:
        A dict with keys ``id, title, kind, origin, pages, n_chunks, created_at``.
    """
    return {
        "id": row["id"], "title": row["title"], "kind": row["kind"],
        "origin": row["origin"], "pages": row["pages"],
        "n_chunks": row["n_chunks"], "created_at": row["created_at"],
    }


def get_source(source_id: str) -> dict | None:
    """Fetch one source's record.

    Args:
        source_id: The source's id.

    Returns:
        The source record, or None when no such source exists.

    Raises:
        sqlite3.Error: On database failures.
    """
    with connect() as conn:
        row = conn.execute("SELECT * FROM sources WHERE id = ?", (source_id,)).fetchone()
    return _source_row(row) if row else None


def list_sources() -> list[dict]:
    """List every source in the library, newest first.

    Returns:
        A list of source records (see ``_source_row``).

    Raises:
        sqlite3.Error: On database failures.
    """
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM sources ORDER BY created_at DESC, rowid DESC"
        ).fetchall()
    return [_source_row(row) for row in rows]


def delete_source(source_id: str) -> bool:
    """Remove a source and all its chunks/vectors.

    Args:
        source_id: The source's id.

    Returns:
        True when the source existed and was deleted; False otherwise.

    Raises:
        sqlite3.Error: On database failures.
    """
    with connect() as conn:
        chunk_ids = [
            row["id"] for row in conn.execute(
                "SELECT id FROM chunks WHERE source_id = ?", (source_id,)
            ).fetchall()
        ]
        if HAS_VEC and chunk_ids:
            conn.executemany(
                "DELETE FROM chunks_vec WHERE rowid = ?", [(cid,) for cid in chunk_ids]
            )
        cursor = conn.execute("DELETE FROM sources WHERE id = ?", (source_id,))
        conn.execute("DELETE FROM chunks WHERE source_id = ?", (source_id,))
    try:
        pdf_path(source_id).unlink(missing_ok=True)
    except OSError:  # the rows are gone either way; a stray file is harmless
        log.warning("couldn't remove stored PDF for %s", source_id, exc_info=True)
    return cursor.rowcount > 0
