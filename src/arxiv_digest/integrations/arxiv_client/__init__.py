"""Seed search against the arXiv API (via the `arxiv` package).

A relevance-ranked hunt across all of arXiv to find the paper you want to drop
into the graph (by keywords, title, author, or a pasted id / URL). Its id is
then handed to the Semantic Scholar graph builder.

**Being retired:** seed search is moving to Semantic Scholar (wider coverage),
so this package is slated for removal. Its one piece needed elsewhere — the
arXiv-id regex — already moved to the ``integrations.arxiv`` package; what's
left here is search itself, until ``services/search`` replaces it.

Split by concern:

* ``clauses`` — the date-range/category filter clauses arXiv's query syntax
  expects.
* ``papers``  — normalizing an ``arxiv.Result`` into the app's paper dict.
* ``search``  — the shared ``arxiv.Client`` and the public entry point,
  ``search_arxiv``, that ties the other two together (and borrows ``ID_RE``
  from the ``arxiv`` package to spot a pasted id).
"""

from __future__ import annotations

from .search import search_arxiv

__all__ = ["search_arxiv"]
