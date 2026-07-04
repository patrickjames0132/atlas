"""Bring-your-own sources (Phase 3d): a persistent, semantically-searchable
library of the user's own material — uploaded PDFs/books and fetched web pages.

Each source is extracted to text, split into overlapping chunks (page-aware for
PDFs so retrieval can cite an exact page), embedded LOCALLY (no API/key — the
text never leaves the machine), and stored in a dedicated sqlite-vec index. The
teacher searches it through tool use, the same way it searches Semantic Scholar,
so an uploaded textbook effectively makes it an expert in that subject.

Everything degrades gracefully: if the embedding model or sqlite-vec can't load,
`available()` is False and ingestion/search raise/return a clear signal rather
than crashing the app.
"""

from __future__ import annotations

import logging
import re
import sqlite3
import urllib.error
import urllib.request
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional
from uuid import uuid4

from .. import config
from ..integrations import fulltext
from . import embeddings

log = logging.getLogger(__name__)


class SourceError(RuntimeError):
    """Ingestion or search failed for a reason worth surfacing to the user."""


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

# sqlite-vec (the vector index) is a loadable extension; it must be reloaded on
# every connection (extensions are per-connection). None = not yet probed.
_HAS_VEC: Optional[bool] = None


def _try_load_vec(conn: sqlite3.Connection) -> bool:
    """Load the sqlite-vec extension into a connection.

    Extensions are per-connection, so this runs on every ``_connect``.

    Args:
        conn: The open SQLite connection.

    Returns:
        True when the extension loaded; False when sqlite-vec is missing or
        the load failed (logged, not raised — the app degrades gracefully).
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


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    """Open a connection to the sources library, committing on clean exit.

    Ensures the schema exists, probes/loads sqlite-vec (recording the result
    in the module-level ``_HAS_VEC``), and creates the vector table when the
    extension is available.

    Yields:
        An open ``sqlite3.Connection`` with ``Row`` as its row factory and
        foreign keys enabled.

    Raises:
        sqlite3.Error: On database failures.
    """
    global _HAS_VEC
    config.ensure_dirs()
    conn = sqlite3.connect(config.SOURCES_DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        has_vec = _try_load_vec(conn)
        _HAS_VEC = has_vec
        conn.executescript(_SCHEMA)
        if has_vec:
            conn.execute(
                f"CREATE VIRTUAL TABLE IF NOT EXISTS chunks_vec USING vec0("
                f"embedding float[{config.EMBED_DIM}] distance_metric=cosine)"
            )
        yield conn
        conn.commit()
    finally:
        conn.close()


def available() -> bool:
    """Report whether the source library is fully usable.

    Returns:
        True when both the embedding model and sqlite-vec load. Note the
        first call may be slow — it triggers the lazy embedding-model load.
    """
    if not embeddings.available():
        return False
    with _connect() as _:
        return bool(_HAS_VEC)


# --- chunking ----------------------------------------------------------------

def _chunk_text(text: str, size: int, overlap: int) -> list[str]:
    """Split text into overlapping windows for embedding.

    Windows are ~``size`` chars, breaking on a space near each boundary so
    chunks don't cut mid-word; whitespace is collapsed first.

    Args:
        text: The raw text to split.
        size: Target window size in characters.
        overlap: Characters of overlap carried between consecutive windows
            (preserves context across chunk boundaries).

    Returns:
        The chunk strings, in order; empty when ``text`` is blank.
    """
    text = " ".join(text.split())
    if not text:
        return []
    if len(text) <= size:
        return [text]
    out: list[str] = []
    n = len(text)
    start = 0
    while start < n:
        end = min(start + size, n)
        if end < n:
            sp = text.rfind(" ", start + size - overlap, end)
            if sp > start:
                end = sp
        chunk = text[start:end].strip()
        if chunk:
            out.append(chunk)
        if end >= n:
            break
        start = max(end - overlap, start + 1)
    return out


# --- extraction --------------------------------------------------------------

def extract_pdf(path: str | Path) -> tuple[list[tuple[int, str]], int]:
    """Extract per-page text from a PDF.

    Args:
        path: Filesystem path to the PDF.

    Returns:
        A ``(pages, total)`` tuple: ``pages`` is ``[(page_no, text)]`` for
        pages that had extractable text (1-based numbering), ``total`` is the
        document's full page count.

    Raises:
        SourceError: For a scanned/image-only PDF (no extractable text — OCR
            isn't supported yet), or when no text was found at all.
        fitz.FileDataError: When the file isn't a readable PDF.
    """
    import fitz  # pymupdf

    doc = fitz.open(path)
    try:
        total = doc.page_count
        pages: list[tuple[int, str]] = []
        for i in range(total):
            text = doc.load_page(i).get_text("text")
            if text and text.strip():
                pages.append((i + 1, text))
    finally:
        doc.close()
    if total >= 3 and sum(len(t) for _, t in pages) < 100:
        raise SourceError(
            "This PDF appears to be scanned/image-only — no extractable text. "
            "OCR isn't supported yet."
        )
    if not pages:
        raise SourceError("No extractable text found in this PDF.")
    return pages, total


_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)


def fetch_url(url: str) -> tuple[str, Optional[str]]:
    """Fetch a web page and reduce it to readable text.

    Args:
        url: The page URL.

    Returns:
        A ``(readable_text, page_title)`` tuple; the title is None when the
        page declares none.

    Raises:
        SourceError: On network failure or when no readable text could be
            extracted.
    """
    req = urllib.request.Request(url, headers={"User-Agent": "arxiv-atlas/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=config.S2_TIMEOUT) as resp:
            raw = resp.read()
    except (urllib.error.URLError, urllib.error.HTTPError) as exc:
        raise SourceError(f"Couldn't fetch {url}: {exc}") from exc
    html = raw.decode("utf-8", errors="replace")
    text = fulltext.html_to_text(html)
    if not text.strip():
        raise SourceError(f"No readable text extracted from {url}.")
    m = _TITLE_RE.search(html)
    title = " ".join(m.group(1).split()) if m else None
    return text, title


# --- ingestion ---------------------------------------------------------------

def add_source(
    title: str, kind: str, origin: Optional[str],
    page_texts: list[tuple[Optional[int], str]], pages: Optional[int] = None,
) -> dict:
    """Chunk, embed, and store a source's page texts.

    Args:
        title: Display title for the source.
        kind: ``"pdf"`` or ``"url"``.
        origin: Where it came from — the original filename or URL (or None).
        page_texts: ``[(page_no, text)]`` — page numbers are 1-based for PDFs
            and None for pageless sources (web pages).
        pages: Total page count (PDFs), or None.

    Returns:
        The stored source record (see ``get_source``).

    Raises:
        SourceError: When the embedding model or sqlite-vec is unavailable,
            embedding fails, or chunking produced no text to index.
        sqlite3.Error: On database failures.
    """
    if not embeddings.available():
        raise SourceError("Embedding model unavailable — cannot ingest sources.")

    chunk_rows: list[tuple[Optional[int], str]] = []
    for page, text in page_texts:
        for chunk in _chunk_text(text, config.SOURCE_CHUNK_CHARS, config.SOURCE_CHUNK_OVERLAP):
            chunk_rows.append((page, chunk))
    if not chunk_rows:
        raise SourceError("No text to index after chunking.")

    vectors = embeddings.embed_texts([c for _, c in chunk_rows])
    if vectors is None:
        raise SourceError("Embedding failed — cannot ingest sources.")

    import sqlite_vec

    sid = uuid4().hex
    with _connect() as conn:
        if not _HAS_VEC:
            raise SourceError("sqlite-vec unavailable — cannot store embeddings.")
        conn.execute(
            "INSERT INTO sources (id, title, kind, origin, pages, n_chunks) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (sid, title, kind, origin, pages, len(chunk_rows)),
        )
        for (page, text), vec in zip(chunk_rows, vectors):
            cur = conn.execute(
                "INSERT INTO chunks (source_id, page, text) VALUES (?, ?, ?)",
                (sid, page, text),
            )
            conn.execute(
                "INSERT INTO chunks_vec (rowid, embedding) VALUES (?, ?)",
                (cur.lastrowid, sqlite_vec.serialize_float32(vec)),
            )
    log.info("Ingested source %s (%s, %d chunks)", title, kind, len(chunk_rows))
    return get_source(sid)


def ingest_pdf(path: str | Path, title: Optional[str] = None) -> dict:
    """Ingest a PDF file into the source library.

    Args:
        path: Filesystem path to the PDF.
        title: Display title; defaults to the filename stem.

    Returns:
        The stored source record.

    Raises:
        SourceError: When extraction or ingestion fails (see ``extract_pdf``
            and ``add_source``).
    """
    path = Path(path)
    pages, total = extract_pdf(path)
    return add_source(title or path.stem, "pdf", path.name, pages, pages=total)


def ingest_url(url: str, title: Optional[str] = None) -> dict:
    """Fetch a web page and ingest its readable text as a single source.

    Args:
        url: The page URL.
        title: Display title; defaults to the page's own ``<title>``, then
            the URL.

    Returns:
        The stored source record.

    Raises:
        SourceError: When the fetch or ingestion fails (see ``fetch_url`` and
            ``add_source``).
    """
    text, page_title = fetch_url(url)
    return add_source(title or page_title or url, "url", url, [(None, text)])


# --- library + search --------------------------------------------------------

def _source_row(row: sqlite3.Row) -> dict:
    """Convert a ``sources`` table row to the API's source record.

    Args:
        row: A row from the ``sources`` table.

    Returns:
        A dict with keys ``id, title, kind, origin, pages, n_chunks,
        created_at``.
    """
    return {
        "id": row["id"], "title": row["title"], "kind": row["kind"],
        "origin": row["origin"], "pages": row["pages"],
        "n_chunks": row["n_chunks"], "created_at": row["created_at"],
    }


def get_source(source_id: str) -> Optional[dict]:
    """Fetch one source's record.

    Args:
        source_id: The source's id.

    Returns:
        The source record, or None when no such source exists.

    Raises:
        sqlite3.Error: On database failures.
    """
    with _connect() as conn:
        row = conn.execute("SELECT * FROM sources WHERE id = ?", (source_id,)).fetchone()
    return _source_row(row) if row else None


def list_sources() -> list[dict]:
    """List every source in the library, newest first.

    Returns:
        A list of source records (see ``_source_row``).

    Raises:
        sqlite3.Error: On database failures.
    """
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM sources ORDER BY created_at DESC, rowid DESC"
        ).fetchall()
    return [_source_row(r) for r in rows]


def delete_source(source_id: str) -> bool:
    """Remove a source and all its chunks/vectors.

    Args:
        source_id: The source's id.

    Returns:
        True when the source existed and was deleted; False otherwise.

    Raises:
        sqlite3.Error: On database failures.
    """
    with _connect() as conn:
        ids = [r["id"] for r in conn.execute(
            "SELECT id FROM chunks WHERE source_id = ?", (source_id,)).fetchall()]
        if _HAS_VEC and ids:
            conn.executemany("DELETE FROM chunks_vec WHERE rowid = ?", [(i,) for i in ids])
        cur = conn.execute("DELETE FROM sources WHERE id = ?", (source_id,))
        conn.execute("DELETE FROM chunks WHERE source_id = ?", (source_id,))
        return cur.rowcount > 0


def search(
    query: str, k: Optional[int] = None, source_ids: Optional[list[str]] = None
) -> list[dict]:
    """Semantic (KNN) search over the library's chunk vectors.

    Args:
        query: What to look for — a concept or question.
        k: Maximum passages to return; defaults to ``config.SOURCE_SEARCH_K``.
        source_ids: Restrict retrieval to this subset of source ids. ``None``
            means "no scope" — search the whole library; an **explicit empty
            list** means "no sources selected" — search nothing (returns []).
            When filtering, the KNN pool is over-fetched (8×) so the join
            filter can still yield ``k`` hits from the chosen sources.

    Returns:
        Up to ``k`` passage dicts — ``{source_id, source_title, page, text,
        distance}`` — ordered by cosine distance (lower = closer). Empty when
        the embedding model or sqlite-vec is unavailable, or when the scope is
        an explicit empty set.

    Raises:
        sqlite3.Error: On database failures.
    """
    k = k or config.SOURCE_SEARCH_K
    # None = whole library; an explicit (possibly empty) list = exactly those
    # sources, so an empty scope searches nothing rather than everything.
    if source_ids is not None:
        ids = [s for s in source_ids if s]
        if not ids:
            return []
    else:
        ids = []

    qvec = embeddings.embed_query(query)
    if qvec is None:
        return []

    import sqlite_vec

    # Over-fetch when filtering so the KNN pool still yields k hits from the
    # chosen sources after the join filter.
    fetch = k * 8 if ids else k
    where = f"WHERE c.source_id IN ({','.join('?' for _ in ids)})" if ids else ""
    params: list = [sqlite_vec.serialize_float32(qvec), fetch]
    params.extend(ids)
    params.append(k)

    with _connect() as conn:
        if not _HAS_VEC:
            return []
        rows = conn.execute(
            f"""
            SELECT c.source_id, s.title AS source_title, c.page, c.text, knn.distance
            FROM (SELECT rowid, distance FROM chunks_vec
                  WHERE embedding MATCH ? AND k = ?) knn
            JOIN chunks c ON c.id = knn.rowid
            JOIN sources s ON s.id = c.source_id
            {where}
            ORDER BY knn.distance
            LIMIT ?
            """,
            params,
        ).fetchall()
    return [
        {
            "source_id": r["source_id"], "source_title": r["source_title"],
            "page": r["page"], "text": r["text"], "distance": r["distance"],
        }
        for r in rows
    ]
