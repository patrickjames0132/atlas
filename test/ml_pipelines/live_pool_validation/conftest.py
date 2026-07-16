"""Fixtures for the live-pool-validation collector tests: a synthetic corpus.

Same approach as ``test/atlas/integrations/semantic_scholar/corpus/conftest.py``
(tiny gzipped JSONL shards → real ingest → activate, all inside ``tmp_path``),
but with a citer set built for THIS study's questions: a seed with citers spread
across years (so truncation actually changes the oldest reachable year), a
DOI-only seed (the papers-table resolution route), and an overlapping second
edge batch (the upstream duplication the reader must collapse).
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

from atlas.config import S2CorpusStorage, config
from atlas.integrations.semantic_scholar.corpus import ingest
from atlas.integrations.semantic_scholar.corpus.paths import (
    parquet_root,
    release_paths,
    write_current_release,
)

RELEASE_ID = "2026-07-07"

#: The arXiv-resolvable seed (corpus id 1) and the DOI-only seed (corpus id 10).
PAPERS = [
    {"corpusid": 1, "externalids": {"ArXiv": "1312.5602"}, "title": "Synthetic DQN",
     "year": 2013, "publicationdate": "2013-12-19", "citationcount": 900,
     "authors": [{"name": "Someone"}]},
    {"corpusid": 10, "externalids": {"DOI": "10.5555/journal-only"},
     "title": "A journal-only seed", "year": 2015, "publicationdate": "2015-01-01",
     "citationcount": 40, "authors": [{"name": "Someone Else"}]},
]
#: Six citers of seed 1, one per year 2019–2024, citation counts DESCENDING with
#: age (the oldest is the most-cited) so citation rank and date order disagree —
#: a truncation that drops old citers visibly moves both the pool's oldest year
#: and the ranking's head. One citer (2022) is undated, exercising the drops.
CITERS = [
    {"corpusid": 2, "year": 2019, "publicationdate": "2019-06-01", "citationcount": 500},
    {"corpusid": 3, "year": 2020, "publicationdate": "2020-06-01", "citationcount": 400},
    {"corpusid": 4, "year": 2021, "publicationdate": "2021-06-01", "citationcount": 300},
    {"corpusid": 5, "year": None, "publicationdate": None, "citationcount": 250},
    {"corpusid": 6, "year": 2023, "publicationdate": "2023-06-01", "citationcount": 100},
    {"corpusid": 7, "year": 2024, "publicationdate": "2024-06-01", "citationcount": 50},
]
CITATIONS = (
    [{"citingcorpusid": citer["corpusid"], "citedcorpusid": 1, "isinfluential": False}
     for citer in CITERS]
    + [{"citingcorpusid": 2, "citedcorpusid": 10, "isinfluential": False}]
)
#: The overlapping second export batch (S2 ships every edge ~twice — see
#: docs/bugs.md → Upstream). Re-ships three of seed 1's edges from another shard.
CITATIONS_SECOND_BATCH = [
    {"citingcorpusid": 2, "citedcorpusid": 1, "isinfluential": True},
    {"citingcorpusid": 6, "citedcorpusid": 1, "isinfluential": False},
    {"citingcorpusid": 7, "citedcorpusid": 1, "isinfluential": False},
]


def write_gzip_jsonl(path: Path, rows: list[dict]) -> None:
    """Write ``rows`` as gzipped newline-delimited JSON (a Datasets shard)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as sink:
        for row in rows:
            sink.write(json.dumps(row) + "\n")


@pytest.fixture()
def synthetic_corpus(monkeypatch, tmp_path):
    """Ingest the synthetic release into a temp corpus tree and activate it.

    Repoints **both** corpus roots into ``tmp_path`` and hard-verifies the paths
    the ingest will actually use resolve inside it — the sibling fixture once
    wrote a synthetic release into the machine's real corpus, so the guard is
    load-bearing, not paranoia.

    Returns:
        The activated release id.
    """
    monkeypatch.setattr(config.storage, "s2", S2CorpusStorage(
        raw=tmp_path / "s2corpus-raw", parquet=tmp_path / "s2corpus-parquet"
    ))
    paths = release_paths(RELEASE_ID)
    for path in (paths.raw, paths.parquet):
        assert path.is_relative_to(tmp_path), f"corpus test would write outside tmp: {path}"
    papers = PAPERS + [
        {"corpusid": citer["corpusid"], "externalids": {},
         "title": f"Citer {citer['corpusid']}", "year": citer["year"],
         "publicationdate": citer["publicationdate"],
         "citationcount": citer["citationcount"], "authors": []}
        for citer in CITERS
    ]
    write_gzip_jsonl(paths.raw_dataset("papers") / "papers000.gz", papers)
    write_gzip_jsonl(paths.raw_dataset("citations") / "citations000.gz", CITATIONS)
    write_gzip_jsonl(paths.raw_dataset("citations") / "citations001.gz", CITATIONS_SECOND_BATCH)
    ingest.ingest_release(RELEASE_ID)
    write_current_release(parquet_root(), RELEASE_ID)
    return RELEASE_ID
