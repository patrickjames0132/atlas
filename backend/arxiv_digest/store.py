"""SQLite persistence for papers and their AI summaries.

One small file (data/digest.db). Papers are keyed by arXiv id so we never store
a paper — or pay to summarize it — twice.
"""

from __future__ import annotations

import json
import re
import sqlite3
from contextlib import contextmanager
from datetime import date
from typing import Iterable, Iterator, Optional

from . import config


SCHEMA = """
CREATE TABLE IF NOT EXISTS papers (
    arxiv_id     TEXT PRIMARY KEY,
    title        TEXT NOT NULL,
    authors      TEXT,
    categories   TEXT,
    abstract     TEXT,
    url          TEXT,
    summary      TEXT,
    digest_date  TEXT NOT NULL,   -- ISO date the paper was first seen (YYYY-MM-DD)
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_papers_digest_date ON papers (digest_date);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

# A full-text index over the searchable columns, kept in sync with `papers` by
# triggers. It's a standalone FTS5 table (not external-content) storing arxiv_id
# UNINDEXED so we can join results back to the row. Created separately from the
# base SCHEMA because FTS5 may not be compiled into every SQLite build — if the
# CREATE fails we fall back to LIKE search (see `search_papers`).
_FTS_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS papers_fts USING fts5(
    arxiv_id UNINDEXED,
    title,
    authors,
    abstract,
    tokenize = 'porter unicode61'
);
CREATE TRIGGER IF NOT EXISTS papers_fts_ai AFTER INSERT ON papers BEGIN
    INSERT INTO papers_fts (arxiv_id, title, authors, abstract)
    VALUES (new.arxiv_id, new.title, new.authors, new.abstract);
END;
CREATE TRIGGER IF NOT EXISTS papers_fts_ad AFTER DELETE ON papers BEGIN
    DELETE FROM papers_fts WHERE arxiv_id = old.arxiv_id;
END;
CREATE TRIGGER IF NOT EXISTS papers_fts_au AFTER UPDATE ON papers BEGIN
    UPDATE papers_fts
       SET title = new.title, authors = new.authors, abstract = new.abstract
     WHERE arxiv_id = new.arxiv_id;
END;
"""

# Set by init_db(): True when FTS5 is available, False when we're on the LIKE
# fallback path.
_HAS_FTS = False

# Key under which the user's followed categories live in the settings table.
_FOLLOWED_KEY = "followed_categories"


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    config.ensure_dirs()
    # timeout lets a reader wait briefly if a write is mid-commit (the dashboard
    # polls papers while refresh writes summaries concurrently).
    conn = sqlite3.connect(config.DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    global _HAS_FTS
    with _connect() as conn:
        conn.executescript(SCHEMA)
        try:
            conn.executescript(_FTS_SCHEMA)
            _HAS_FTS = True
        except sqlite3.OperationalError:
            # FTS5 isn't compiled into this SQLite build; search falls back to
            # LIKE. Everything else keeps working.
            _HAS_FTS = False
            return
        # First run after adding search: backfill the index for rows that were
        # stored before the triggers existed. (New writes stay in sync via the
        # triggers, so this only fires once.)
        fts_count = conn.execute("SELECT count(*) FROM papers_fts").fetchone()[0]
        papers_count = conn.execute("SELECT count(*) FROM papers").fetchone()[0]
        if fts_count == 0 and papers_count > 0:
            conn.execute(
                "INSERT INTO papers_fts (arxiv_id, title, authors, abstract) "
                "SELECT arxiv_id, title, authors, abstract FROM papers"
            )


def upsert_papers(papers: Iterable[dict], digest_date: Optional[str] = None) -> int:
    """Insert papers we haven't seen before. Returns the count of NEW papers.

    Existing papers (same arxiv_id) are left untouched so we keep their original
    digest_date and any summary already generated. Each paper's own
    ``digest_date`` (its submission day) is used when present; otherwise the
    ``digest_date`` argument (or today) is the fallback for all of them.
    """
    fallback_date = digest_date or date.today().isoformat()
    new_count = 0
    with _connect() as conn:
        for p in papers:
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO papers
                    (arxiv_id, title, authors, categories, abstract, url, digest_date)
                VALUES (:arxiv_id, :title, :authors, :categories, :abstract, :url, :digest_date)
                """,
                {
                    "arxiv_id": p["arxiv_id"],
                    "title": p["title"],
                    "authors": p.get("authors", ""),
                    "categories": p.get("categories", ""),
                    "abstract": p.get("abstract", ""),
                    "url": p.get("url", ""),
                    "digest_date": p.get("digest_date") or fallback_date,
                },
            )
            new_count += cur.rowcount
    return new_count


def papers_needing_summary() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM papers WHERE summary IS NULL OR summary = ''"
        ).fetchall()
    return [dict(r) for r in rows]


def set_summary(arxiv_id: str, summary: str) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE papers SET summary = ? WHERE arxiv_id = ?", (summary, arxiv_id)
        )


def get_papers(digest_date: Optional[str] = None) -> list[dict]:
    """Return papers for a given date (default: most recent date on record)."""
    with _connect() as conn:
        if digest_date is None:
            row = conn.execute("SELECT MAX(digest_date) AS d FROM papers").fetchone()
            digest_date = row["d"] if row and row["d"] else date.today().isoformat()
        rows = conn.execute(
            "SELECT * FROM papers WHERE digest_date = ? ORDER BY created_at",
            (digest_date,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_papers_in_range(start_date: str, end_date: str) -> list[dict]:
    """Return papers whose digest_date falls in [start_date, end_date], newest
    submission day first."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM papers WHERE digest_date BETWEEN ? AND ? "
            "ORDER BY digest_date DESC, created_at",
            (start_date, end_date),
        ).fetchall()
    return [dict(r) for r in rows]


def _fts_query(raw: str) -> str:
    """Turn free-text into a safe FTS5 prefix-AND query.

    Each bare word becomes a quoted prefix term (``"word"*``): quoting neutralizes
    FTS5 operators/punctuation so user input can't cause a syntax error, and the
    trailing ``*`` lets partial words match (typing "transform" finds
    "transformer"). Multiple terms are implicitly AND-ed. Returns "" when the
    input has no word characters.
    """
    terms = re.findall(r"\w+", raw, flags=re.UNICODE)
    return " ".join(f'"{t}"*' for t in terms)


def search_papers(
    query: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 200,
) -> list[dict]:
    """Full-text search stored papers by title/authors/abstract.

    Ranked best-match-first via BM25. Optionally scoped to a ``digest_date``
    range (both bounds required to scope; otherwise searches all stored papers).
    Falls back to a substring LIKE search when FTS5 isn't available.
    """
    q = (query or "").strip()
    if not q:
        return []
    scoped = bool(start_date and end_date)
    with _connect() as conn:
        if _HAS_FTS:
            match = _fts_query(q)
            if not match:
                return []
            sql = (
                "SELECT papers.* FROM papers_fts "
                "JOIN papers ON papers.arxiv_id = papers_fts.arxiv_id "
                "WHERE papers_fts MATCH ? "
            )
            params: list = [match]
            if scoped:
                sql += "AND papers.digest_date BETWEEN ? AND ? "
                params += [start_date, end_date]
            sql += "ORDER BY bm25(papers_fts) LIMIT ?"
            params.append(limit)
        else:
            like = f"%{q}%"
            sql = (
                "SELECT * FROM papers "
                "WHERE (title LIKE ? OR abstract LIKE ? OR authors LIKE ?) "
            )
            params = [like, like, like]
            if scoped:
                sql += "AND digest_date BETWEEN ? AND ? "
                params += [start_date, end_date]
            sql += "ORDER BY digest_date DESC, created_at LIMIT ?"
            params.append(limit)
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def get_paper(arxiv_id: str) -> Optional[dict]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM papers WHERE arxiv_id = ?", (arxiv_id,)
        ).fetchone()
    return dict(row) if row else None


def get_followed_categories() -> list[str]:
    """The categories the user follows (pulled from arXiv + used as filters).

    Stored in the settings table; falls back to the .env default (config) the
    first time, before the user has customized anything.
    """
    with _connect() as conn:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = ?", (_FOLLOWED_KEY,)
        ).fetchone()
    if row is None:
        return list(config.ARXIV_CATEGORIES)
    return json.loads(row["value"])


def set_followed_categories(categories: list[str]) -> list[str]:
    """Persist the followed categories (order preserved, duplicates dropped)."""
    seen: dict[str, None] = {}
    for c in categories:
        if c not in seen:
            seen[c] = None
    cleaned = list(seen)
    with _connect() as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (_FOLLOWED_KEY, json.dumps(cleaned)),
        )
    return cleaned


def available_dates() -> list[str]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT DISTINCT digest_date FROM papers ORDER BY digest_date DESC"
        ).fetchall()
    return [r["digest_date"] for r in rows]
