"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
Shared SQLite connection helper for the storage package.

Every storage module (``cache``, ``sessions``, …) opens its database file the
same way: make sure the data directory exists, connect with row-based
access, create its schema if missing, and commit on a clean exit. The only
thing that actually differs between them is which file and which schema —
so that's the only thing each caller passes in.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

import sqlite3
from contextlib import AbstractContextManager, contextmanager
from pathlib import Path
from typing import Iterator

from ..config import config


@contextmanager
def connect(db_path: Path, schema: str) -> Iterator[sqlite3.Connection]:
    """Open a connection to a storage database, committing on clean exit.

    Args:
        db_path: The SQLite file to open.
        schema: DDL to run before yielding — typically a ``CREATE TABLE IF
            NOT EXISTS`` statement.

    Yields:
        An open ``sqlite3.Connection`` with ``Row`` as its row factory.

    Raises:
        sqlite3.Error: On database failures (locked file, corrupt db, …).
    """
    config.storage.ensure_dirs()
    conn = sqlite3.connect(db_path, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute(schema)
        yield conn
        conn.commit()
    finally:
        conn.close()


ConnectionContext = AbstractContextManager[sqlite3.Connection]
