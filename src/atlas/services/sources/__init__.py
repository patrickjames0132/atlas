"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
Bring-your-own sources: the user's persistent, semantically-searchable
library of their own material — uploaded PDFs/books and fetched web pages.

Each source is extracted to text, split into overlapping chunks (page-aware for
PDFs so retrieval can cite an exact page), embedded LOCALLY (no API/key — the
text never leaves the machine), and stored in a dedicated SQLite database with a
vector index. The teacher searches it through tool use, the same way it searches
Semantic Scholar, so an uploaded textbook effectively makes it an expert in that
subject.

Retrieval is **hybrid**: a semantic ranking (vector KNN) and a lexical one (FTS5
BM25) are fused with Reciprocal Rank Fusion. Everything degrades gracefully when
the embedding model, sqlite-vec, or FTS5 is unavailable (see the README).

Modules:

* ``embeddings`` — the local sentence-transformers model (lazy, degrades).
* ``store``      — the SQLite schema, connection, sqlite-vec/FTS5 setup, CRUD,
  and where each uploaded PDF's original file is kept.
* ``extract``    — PDF/URL → clean, chunked text.
* ``ingest``     — chunk → embed → store (and keep the PDF beside the index).
* ``retrieval``  — the hybrid (semantic + lexical) search.
* ``figures``    — the figure manifest mined from a stored PDF + its renders.
* ``errors``     — ``SourceError``.

The public API is re-exported here, so callers use ``sources.ingest_pdf(...)`` /
``sources.search(...)`` without reaching into the submodules.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

from .errors import SourceError
from .figures import get_source_figures, render_source_figure
from .ingest import ProgressFn, add_source, ingest_pdf, ingest_url
from .retrieval import search
from .store import available, delete_source, get_source, list_sources

__all__ = [
    "ProgressFn",
    "SourceError",
    "add_source",
    "available",
    "delete_source",
    "get_source",
    "get_source_figures",
    "ingest_pdf",
    "ingest_url",
    "list_sources",
    "render_source_figure",
    "search",
]
