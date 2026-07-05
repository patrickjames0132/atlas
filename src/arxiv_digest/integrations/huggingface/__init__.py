"""Hugging Face Papers — a paper's code & artifact links.

Papers with Code sunset into Hugging Face Papers, so HF is now the place that
maps an arXiv id to runnable implementations: a community-linked GitHub repo
plus the models, datasets, and Spaces that cite the paper. One call to
``/api/papers/{arxiv_id}`` returns all of it, and this package normalizes that
into a small envelope for the detail panel's "code & artifacts" section:

* ``client``     — the single HTTP fetch (``fetch_paper``), host/base URL, and
  the cache TTL. One external service, one transport layer.
* ``code_links`` — flattens HF's loosely-typed response into the
  ``{available, github, models, datasets, spaces, totals, …}`` envelope
  (``get_code_links``), plus the empty-envelope fallback (``empty_result``).

A single-service, single-shape client — smaller than the ar5iv/
semantic_scholar packages, but split the same way (transport vs. domain) so
the ``integrations`` packages all read alike.
"""

from __future__ import annotations

from .code_links import empty_result, get_code_links

__all__ = ["empty_result", "get_code_links"]
