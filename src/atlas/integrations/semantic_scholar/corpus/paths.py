"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
On-disk layout of the offline Semantic Scholar corpus — one root, per-release subtrees.

Everything lives under the single ``config.storage.s2_corpus`` root: each
monthly Datasets **release** gets its own subtree holding both halves (the
downloaded shards and the ingested Parquet), and the ``CURRENT`` pointer sits
at the top:

    <storage.s2_corpus>/
      CURRENT                            <- text file: the active release_id
      releases/2026-07-07/
        raw/papers/*.gz                  <- downloaded JSONL.gz shards
        raw/citations/*.gz
        download.json                    <- per-shard download checkpoint
        parquet/papers/*.parquet         <- ingested, queryable
        parquet/arxiv_index/*.parquet
        parquet/citations/bucket=NNN/*.parquet

(History: the halves used to have a root each — ``storage.s2.raw`` /
``storage.s2.parquet`` — so the write-once shards could live on a slow big
drive while the queried Parquet got the NVMe. Recombined 2026-07-19: one
drive holds everything in practice, and the split was config surface nobody
used. The per-release ``raw/`` and ``parquet/`` subtrees were already shaped
for this, so a machine whose two roots pointed at one directory migrates with
a config edit alone. A release's ``raw/`` shards remain deletable the moment
its ingest succeeds — a re-ingest just means a re-download.)

Isolating each release means a fresh monthly pull downloads and ingests
alongside the live one, and only flips ``CURRENT`` once it's complete. That
guard has a known hole — re-ingesting a release ``CURRENT`` *already* points
at exposes the half-built state live; move ``CURRENT`` aside first (see this
package's README).

Every path derives from a :class:`ReleasePaths`, so relocating the corpus (a
different drive, or the eventual S3 prefix) is a config change. Nothing here
touches the network or DuckDB — it's pure path algebra, safe to import and
call without the corpus present.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ....config import config

#: The two bulk Datasets releases the corpus is built from. ``papers`` maps
#: external ids (arXiv/DOI) to S2's integer ``corpusid`` and carries the
#: citation counts to rank by; ``citations`` is the edge list keyed by those
#: ids. Both are needed — a citer lookup joins one to the other.
DATASETS: tuple[str, ...] = ("papers", "citations")

#: Filename of the pointer naming the active (fully ingested) release. Lives at
#: the corpus root, beside the data it names. A plain text file so it's
#: trivially inspectable and editable — parking it is how you take a corpus
#: offline without deleting anything.
CURRENT_FILE = "CURRENT"


def corpus_root() -> Path | None:
    """The corpus's one root, or None when this machine runs without a corpus.

    Returns:
        ``config.storage.s2_corpus`` (already anchored to the repo root if it
        was relative), or None — in which case the app falls back to the live
        S2 citation endpoint.
    """
    return config.storage.s2_corpus


@dataclass(frozen=True)
class ReleasePaths:
    """Every path within one Datasets release under the corpus root.

    Frozen and cheap to build — construct one per operation rather than caching
    it, so a config change (or a test's temp dir) is always honored. Prefer
    :func:`release_paths`, which wires the root from config.

    The root may be absent (a machine without a corpus); touching any path
    then raises rather than silently inventing a location.
    """

    release_id: str
    root: Path | None = None

    @property
    def _release_dir(self) -> Path:
        """The release's subtree, or a clear error when the corpus is unset.

        Returns:
            ``<root>/releases/<release_id>``.

        Raises:
            ValueError: When ``config.storage.s2_corpus`` isn't set — better
                than quietly defaulting somewhere, which is how Parquet once
                ended up written to a drive nobody asked for.
        """
        if self.root is None:
            raise ValueError("config.storage.s2_corpus is not set")
        return self.root / "releases" / self.release_id

    @property
    def raw(self) -> Path:
        """Directory holding the downloaded, un-ingested ``.gz`` shards."""
        return self._release_dir / "raw"

    def raw_dataset(self, dataset: str) -> Path:
        """The raw-shard directory for one dataset (``papers`` / ``citations``)."""
        return self.raw / dataset

    @property
    def parquet(self) -> Path:
        """Directory holding the ingested, queryable Parquet."""
        return self._release_dir / "parquet"

    def parquet_dataset(self, dataset: str) -> Path:
        """The Parquet directory for one dataset (``papers`` / ``citations``)."""
        return self.parquet / dataset

    @property
    def download_state(self) -> Path:
        """The per-shard download checkpoint (JSON), enabling resume.

        Beside the shards it tracks, so deleting a release's raw subtree
        discards its checkpoint with it — and a later re-download starts clean
        rather than believing shards that are gone are still on disk.
        """
        return self._release_dir / "download.json"


def release_paths(release_id: str) -> ReleasePaths:
    """One release's paths, wired from config — how callers should build them.

    Args:
        release_id: The release the paths are for.

    Returns:
        The release's paths under the configured corpus root.
    """
    return ReleasePaths(release_id=release_id, root=corpus_root())


def current_release_file(root: Path) -> Path:
    """The ``CURRENT`` pointer's path under the corpus root."""
    return root / CURRENT_FILE


def read_current_release(root: Path) -> str | None:
    """The active (fully ingested) release id, or None when none is marked.

    Args:
        root: The corpus root — ``CURRENT`` sits beside the data it names.

    Returns:
        The release id in ``CURRENT``, stripped of whitespace, or None when the
        pointer is missing or empty.
    """
    pointer = current_release_file(root)
    if not pointer.exists():
        return None
    release_id = pointer.read_text(encoding="utf-8").strip()
    return release_id or None


def write_current_release(root: Path, release_id: str) -> None:
    """Point ``CURRENT`` at a release, marking it the one the app queries.

    Args:
        root: The corpus root (created if missing).
        release_id: The release id to activate — written verbatim.
    """
    root.mkdir(parents=True, exist_ok=True)
    current_release_file(root).write_text(release_id + "\n", encoding="utf-8")
