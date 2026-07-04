"""Bring-your-own sources (Phase 3d): a persistent, semantically-searchable
library of the user's own material — uploaded PDFs/books and fetched web pages.

Each source is extracted to text, split into overlapping chunks (page-aware for
PDFs so retrieval can cite an exact page), embedded LOCALLY (no API/key — the
text never leaves the machine), and stored in a dedicated sqlite-vec index. The
teacher searches it through tool use, the same way it searches Semantic Scholar,
so an uploaded textbook effectively makes it an expert in that subject.

Retrieval is **hybrid**: a semantic ranking (vector KNN) and a lexical one
(FTS5 BM25) are fused with Reciprocal Rank Fusion, so exact terms and proper
nouns the embedder blurs together still surface (Phase 3d.3).

Everything degrades gracefully: if the embedding model or sqlite-vec can't load,
`available()` is False and ingestion/search raise/return a clear signal rather
than crashing the app. If FTS5 isn't compiled into SQLite, lexical search is
simply skipped and retrieval falls back to pure vector KNN.
"""

from __future__ import annotations

import logging
import re
import sqlite3
import urllib.error
import urllib.request
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional, Sequence
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

# sqlite-vec (the vector index) is a loadable extension; it must be reloaded on
# every connection (extensions are per-connection). None = not yet probed.
_HAS_VEC: Optional[bool] = None
# FTS5 support is a fixed property of the SQLite build; probed once, then cached.
_HAS_FTS: Optional[bool] = None


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
        into this SQLite build (logged once, not raised — lexical search is
        then skipped and retrieval falls back to pure vector KNN).
    """
    try:
        existed = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='chunks_fts'"
        ).fetchone()
        conn.executescript(_FTS_SCHEMA)
        if not existed:
            # Freshly created (new library, or migrating one built before
            # hybrid search) — populate from the chunks already stored.
            conn.execute("INSERT INTO chunks_fts (chunks_fts) VALUES ('rebuild')")
        return True
    except sqlite3.OperationalError:
        log.warning("FTS5 unavailable — lexical search disabled")
        return False


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    """Open a connection to the sources library, committing on clean exit.

    Ensures the schema exists, probes/loads sqlite-vec (recording the result
    in the module-level ``_HAS_VEC``), creates the vector table when the
    extension is available, and sets up the FTS5 lexical index (recording
    ``_HAS_FTS``).

    Yields:
        An open ``sqlite3.Connection`` with ``Row`` as its row factory and
        foreign keys enabled.

    Raises:
        sqlite3.Error: On database failures.
    """
    global _HAS_VEC, _HAS_FTS
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
        _HAS_FTS = _try_setup_fts(conn)
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
    page_texts: Sequence[tuple[Optional[int], str]], pages: Optional[int] = None,
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
    record = get_source(sid)
    assert record is not None  # just inserted above
    return record


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


# FTS5 treats bare punctuation and words like AND/OR/NEAR as query syntax, so a
# raw question ("What's the Adam optimizer's β2?") can raise a parse error. We
# extract word tokens and OR them as quoted string literals — a safe, forgiving
# "any of these terms" match that never trips the grammar.
_FTS_TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)


def _fts_match_query(query: str) -> str:
    """Turn a free-text query into a safe FTS5 MATCH expression.

    Args:
        query: The user/agent's natural-language query.

    Returns:
        An ``"term1" OR "term2" ...`` string of quoted word tokens, or ``""``
        when the query has no usable tokens (caller then skips lexical search).
    """
    tokens = _FTS_TOKEN_RE.findall(query)
    return " OR ".join(f'"{t}"' for t in tokens)


def _scoped_where(ids: list[str], column: str) -> tuple[str, list[str]]:
    """Build an optional ``source_id IN (…)`` clause for a scoped search.

    Args:
        ids: The (already blank-filtered) source ids to restrict to; empty
            means no restriction.
        column: The qualified column to filter on, e.g. ``"c.source_id"``.

    Returns:
        A ``(clause, params)`` tuple — the clause is ``""`` (no restriction)
        or ``"AND <column> IN (?, …)"`` with matching ``params``.
    """
    if not ids:
        return "", []
    placeholders = ",".join("?" for _ in ids)
    return f"AND {column} IN ({placeholders})", list(ids)


def _vector_search(
    conn: sqlite3.Connection, query: str, fetch: int, ids: list[str]
) -> list[dict]:
    """Rank chunks by semantic similarity (sqlite-vec cosine KNN).

    Args:
        conn: An open library connection (sqlite-vec already loaded).
        query: The natural-language query to embed and match.
        fetch: How many candidates to pull (the RRF pool for this ranker).
        ids: Source-id scope (empty = whole library).

    Returns:
        Chunk dicts ``{id, source_id, source_title, page, text}`` best-first,
        or ``[]`` when the embedder or sqlite-vec is unavailable.
    """
    if not _HAS_VEC:
        return []
    qvec = embeddings.embed_query(query)
    if qvec is None:
        return []

    import sqlite_vec

    scope, scope_params = _scoped_where(ids, "c.source_id")
    rows = conn.execute(
        f"""
        SELECT c.id, c.source_id, s.title AS source_title, c.page, c.text
        FROM (SELECT rowid, distance FROM chunks_vec
              WHERE embedding MATCH ? AND k = ?) knn
        JOIN chunks c ON c.id = knn.rowid
        JOIN sources s ON s.id = c.source_id
        WHERE 1 {scope}
        ORDER BY knn.distance
        """,
        [sqlite_vec.serialize_float32(qvec), fetch, *scope_params],
    ).fetchall()
    return [dict(r) for r in rows]


def _lexical_search(
    conn: sqlite3.Connection, query: str, fetch: int, ids: list[str]
) -> list[dict]:
    """Rank chunks by lexical relevance (FTS5 BM25).

    Args:
        conn: An open library connection.
        query: The natural-language query (sanitized into an FTS5 expression).
        fetch: How many candidates to pull (the RRF pool for this ranker).
        ids: Source-id scope (empty = whole library).

    Returns:
        Chunk dicts ``{id, source_id, source_title, page, text}`` best-first,
        or ``[]`` when FTS5 is unavailable or the query has no usable terms.
    """
    if not _HAS_FTS:
        return []
    match = _fts_match_query(query)
    if not match:
        return []
    scope, scope_params = _scoped_where(ids, "c.source_id")
    rows = conn.execute(
        f"""
        SELECT c.id, c.source_id, s.title AS source_title, c.page, c.text
        FROM chunks_fts
        JOIN chunks c ON c.id = chunks_fts.rowid
        JOIN sources s ON s.id = c.source_id
        WHERE chunks_fts MATCH ? {scope}
        ORDER BY bm25(chunks_fts)
        LIMIT ?
        """,
        [match, *scope_params, fetch],
    ).fetchall()
    return [dict(r) for r in rows]


def _rrf_fuse(rankings: list[list[dict]], k: int, rrf_k: int) -> list[dict]:
    """Fuse several ranked chunk lists via Reciprocal Rank Fusion.

    Each ranker contributes ``1 / (rrf_k + rank)`` (1-based rank) to a chunk's
    score, so a chunk ranked highly by *either* the semantic or the lexical
    side rises — no score normalization across the two scales needed.

    Args:
        rankings: One best-first list of chunk dicts per ranker; each dict must
            carry a unique ``id`` plus the display fields.
        k: Maximum fused passages to return.
        rrf_k: The RRF damping constant (larger flattens rank influence).

    Returns:
        Up to ``k`` passage dicts ``{source_id, source_title, page, text,
        score}`` ordered by fused score (higher = stronger), deduplicated by
        chunk id.
    """
    scores: dict[int, float] = {}
    chunks: dict[int, dict] = {}
    for ranking in rankings:
        for rank, hit in enumerate(ranking, start=1):
            cid = hit["id"]
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (rrf_k + rank)
            chunks.setdefault(cid, hit)
    ordered = sorted(scores, key=lambda c: scores[c], reverse=True)[:k]
    return [
        {
            "source_id": chunks[c]["source_id"],
            "source_title": chunks[c]["source_title"],
            "page": chunks[c]["page"], "text": chunks[c]["text"],
            "score": scores[c],
        }
        for c in ordered
    ]


def search(
    query: str, k: Optional[int] = None, source_ids: Optional[list[str]] = None
) -> list[dict]:
    """Hybrid search over the library — semantic KNN fused with lexical BM25.

    Runs a vector (sqlite-vec cosine KNN) and a lexical (FTS5 BM25) ranking and
    combines them with Reciprocal Rank Fusion (Phase 3d.3), so both meaning and
    exact terms count. Degrades gracefully: with FTS5 missing (or hybrid off) it
    is pure vector search; with the embedder missing it is lexical-only; with
    neither it returns ``[]``.

    Args:
        query: What to look for — a concept or question.
        k: Maximum passages to return; defaults to ``config.SOURCE_SEARCH_K``.
        source_ids: Restrict retrieval to this subset of source ids. ``None``
            means "no scope" — search the whole library; an **explicit empty
            list** means "no sources selected" — search nothing (returns []).
            When filtering, each ranker's pool is over-fetched (8×) so the
            scope filter can still yield ``k`` hits from the chosen sources.

    Returns:
        Up to ``k`` passage dicts — ``{source_id, source_title, page, text,
        score}``, best-first (higher fused score = stronger). Empty when both
        rankers are unavailable, or when the scope is an explicit empty set.

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

    # Over-fetch each ranker when scoping so its pool still yields k in-scope
    # hits after the filter; also gives RRF a deeper pool to fuse over.
    fetch = k * 8 if ids else k

    with _connect() as conn:
        vector = _vector_search(conn, query, fetch, ids)
        lexical = _lexical_search(conn, query, fetch, ids) if config.SOURCE_HYBRID else []

    return _rrf_fuse([vector, lexical], k, config.SOURCE_RRF_K)
