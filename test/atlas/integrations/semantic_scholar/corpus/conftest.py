"""Fixtures for the offline citations-corpus tests: a tiny synthetic release.

No network and no real Datasets pull — a handful of ``papers``/``citations``
records are written as gzipped JSONL shards, ingested to a temp corpus dir, and
activated, exactly as the real ``atlas corpus download`` + ``ingest`` would. The
seed is "Attention Is All You Need" (arXiv ``1706.03762``, corpus id 1); its
citers are BERT (80k cites), GPT-3 (50k), and one paper published within the
recent window — enough to assert citation-sorted landmarks and the latest split.
"""

from __future__ import annotations

import datetime
import gzip
import json
from pathlib import Path

import pytest

from atlas.config import config
from atlas.integrations.semantic_scholar.corpus import ingest
from atlas.integrations.semantic_scholar.corpus.paths import ReleasePaths, write_current_release

RELEASE_ID = "2026-07-07"

#: A citer published a few days ago — always inside the rolling latest window,
#: whatever day the suite runs (so the split assertion never goes stale).
RECENT_DATE = (datetime.date.today() - datetime.timedelta(days=5)).isoformat()

PAPERS = [
    {"corpusid": 1, "externalids": {"ArXiv": "1706.03762", "DOI": "10.x/attn"},
     "title": "Attention Is All You Need", "year": 2017, "publicationdate": "2017-06-12",
     "citationcount": 100000, "authors": [{"authorId": "a", "name": "Vaswani"}]},
    {"corpusid": 2, "externalids": {"ArXiv": "1810.04805"}, "title": "BERT",
     "year": 2018, "publicationdate": "2018-10-11", "citationcount": 80000,
     "authors": [{"name": "Devlin"}, {"name": "Chang"}]},
    {"corpusid": 3, "externalids": {}, "title": "A recent applied paper", "year": 2026,
     "publicationdate": RECENT_DATE, "citationcount": 5, "authors": [{"name": "Someone"}]},
    {"corpusid": 4, "externalids": {"ArXiv": "2005.14165"}, "title": "GPT-3", "year": 2020,
     "publicationdate": "2020-05-28", "citationcount": 50000, "authors": [{"name": "Brown"}]},
]
#: Edges: BERT, GPT-3, and the recent paper all cite the seed (corpus id 1).
CITATIONS = [
    {"citingcorpusid": 2, "citedcorpusid": 1, "isinfluential": True},
    {"citingcorpusid": 4, "citedcorpusid": 1, "isinfluential": False},
    {"citingcorpusid": 3, "citedcorpusid": 1, "isinfluential": False},
]


def write_gzip_jsonl(path: Path, rows: list[dict]) -> None:
    """Write ``rows`` as gzipped newline-delimited JSON (a Datasets shard)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as sink:
        for row in rows:
            sink.write(json.dumps(row) + "\n")


@pytest.fixture()
def synthetic_corpus(monkeypatch, tmp_path):
    """Ingest the synthetic release into a temp corpus dir and activate it.

    Points ``config.storage.s2_corpus_dir`` at the temp root (the autouse
    isolation had forced it off), so ``active_source()`` and
    ``citation_relations`` see a live corpus.

    Returns:
        The activated release id.
    """
    root = tmp_path / "s2corpus"
    monkeypatch.setattr(config.storage, "s2_corpus_dir", root)
    paths = ReleasePaths(root=root, release_id=RELEASE_ID)
    write_gzip_jsonl(paths.raw_dataset("papers") / "papers000.gz", PAPERS)
    write_gzip_jsonl(paths.raw_dataset("citations") / "citations000.gz", CITATIONS)
    ingest.ingest_release(RELEASE_ID)
    write_current_release(root, RELEASE_ID)
    return RELEASE_ID
