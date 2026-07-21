"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
Client for the Semantic Scholar Academic Graph + Recommendations APIs.

arXiv Atlas connects to S2 dynamically rather than storing a paper corpus.
S2 is the backbone Connected Papers itself uses: it maps arXiv ids directly
(``ARXIV:<id>``) and exposes references, citations, SPECTER2 embeddings,
``tldr`` summaries, and related-paper recommendations.

Split by concern:

* ``client``    — HTTP transport: throttling, retries/backoff, headers, id
  quoting, and the one exception type (``S2Error``) this whole package raises.
* ``nodes``     — normalizing a raw S2 paper object into the app's graph-node
  shape (the single place that shape is defined), and the field lists used
  to request it.
* ``traversal`` — hydrating paper details (``get_papers``/``get_paper``) and
  walking the citation graph from a seed (``references``/``citations``/
  ``recommendations``).
* ``search``    — ungrounded free-text search across all of Semantic Scholar
  (``search_papers``), for recent/topical work citation hops can't reach;
  plus exact-title resolution (``match_title``, S2's ``/paper/search/match``).
* ``vocab``     — S2's fields of study (``fields`` / ``valid_fields``): the ~20
  coarse subjects the seed-search filter uses. (arXiv's parallel finer
  vocabulary is ``arxiv.vocab``.)
* ``corpus``    — the offline S2 citations corpus (bulk Datasets releases,
  downloaded and ingested to local Parquet). Its ``corpus.citation_relations``
  is the drop-in the graph build prefers over the recency-biased live citation
  endpoint, falling back to it when the corpus is absent.

Everything callers need is re-exported here, so ``from ..integrations import
semantic_scholar as s2`` and ``s2.get_papers(...)`` etc. work exactly as if
this were still one file. (The ``vocab`` submodule is accessed as
``s2.vocab.fields()``.)

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

from . import corpus, vocab
from .client import S2Error
from .search import match_title, search_papers
from .traversal import (
    citation_relations,
    citations,
    get_paper,
    get_papers,
    recommendations,
    references,
)

__all__ = [
    "S2Error",
    "citation_relations",
    "citations",
    "corpus",
    "get_paper",
    "get_papers",
    "match_title",
    "recommendations",
    "references",
    "search_papers",
    "vocab",
]
