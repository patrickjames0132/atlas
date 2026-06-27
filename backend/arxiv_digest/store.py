"""SQLite persistence for papers and their AI summaries.

One small file (data/digest.db). Papers are keyed by arXiv id so we never store
a paper — or pay to summarize it — twice.
"""

from __future__ import annotations

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
"""


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
    with _connect() as conn:
        conn.executescript(SCHEMA)


def upsert_papers(papers: Iterable[dict], digest_date: Optional[str] = None) -> int:
    """Insert papers we haven't seen before. Returns the count of NEW papers.

    Existing papers (same arxiv_id) are left untouched so we keep their original
    digest_date and any summary already generated.
    """
    digest_date = digest_date or date.today().isoformat()
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
                    "digest_date": digest_date,
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


def get_paper(arxiv_id: str) -> Optional[dict]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM papers WHERE arxiv_id = ?", (arxiv_id,)
        ).fetchone()
    return dict(row) if row else None


def available_dates() -> list[str]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT DISTINCT digest_date FROM papers ORDER BY digest_date DESC"
        ).fetchall()
    return [r["digest_date"] for r in rows]
