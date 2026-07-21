"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
The offline Semantic Scholar citations corpus — S2's *real* Field-Landmarks fix.

S2's live citation endpoint is newest-first, unsorted, and capped at a ~10k
offset, so a heavily-cited seed's most-cited (landmark) citers are simply
unreachable — the s2 provider's Field Landmarks are recency-biased. The only fix
is to hold S2's citation graph locally: this package downloads the bulk
`citations` + `papers` Datasets releases, ingests them to queryable Parquet, and
answers a seed's citers **citation-sorted across all history**.

Split by concern:

* ``paths``     — on-disk layout of the corpus root (per-release subtrees + the
  ``CURRENT`` pointer). Pure path algebra; safe to import corpus-less.
* ``datasets``  — the S2 **Datasets** API client (release id + shard URLs), with
  its own patient throttle and the ``CorpusError`` this package raises.
* ``download``  — the resumable shard downloader (checkpointed, URL-expiry-aware).
* ``ingest``    — DuckDB JSONL.gz → Parquet (papers projected + arXiv-indexed,
  citations hash-partitioned on ``citedcorpusid``).
* ``source``    — the query side: the :class:`~.source.CitationSource` seam, the
  :class:`~.source.DuckDBCitationSource` impl, and ``citation_relations`` — the
  drop-in ``build.py`` calls, returning None to fall back to the live path.

The download/ingest steps are operator actions driven by the ``atlas corpus``
CLI; only ``source`` is on a request path. See ``README.md`` for the full
workflow and the AWS (Airflow/S3/Athena) endgame this prototypes.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

from .datasets import CorpusError
from .source import CitationSource, DuckDBCitationSource, active_source, citation_relations

__all__ = [
    "CitationSource",
    "CorpusError",
    "DuckDBCitationSource",
    "active_source",
    "citation_relations",
]
