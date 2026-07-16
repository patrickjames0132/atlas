"""On-disk layout of the offline Semantic Scholar corpus — two roots, one per half.

The corpus has two halves with **opposite access patterns**, so they get a root
each (``config.storage.s2.raw`` / ``config.storage.s2.parquet``). Each holds one
subtree per monthly Datasets **release**, and owns its own state file:

    <storage.s2.raw>/                    the downloads — write once, read once
      releases/2026-07-07/
        raw/papers/*.gz                  <- downloaded JSONL.gz shards
        raw/citations/*.gz
        download.json                    <- per-shard download checkpoint

    <storage.s2.parquet>/                what gets queried
      CURRENT                            <- text file: the active release_id
      releases/2026-07-07/
        parquet/papers/*.parquet         <- ingested, queryable
        parquet/arxiv_index/*.parquet
        parquet/citations/bucket=NNN/*.parquet

**``CURRENT`` lives with the Parquet, not the shards** — it names an *ingested*
release, so it belongs beside the data it points at. The payoff is that the
parquet root is the app's **only serving dependency**: unplug the raw drive and
graph builds carry on. (It lived on the raw side until v5.7.0, which meant
serving needed both drives just to read a one-line pointer.)

Isolating each release means a fresh monthly pull downloads and ingests alongside
the live one, and only flips ``CURRENT`` once it's complete. That guard has a
known hole — re-ingesting a release ``CURRENT`` *already* points at exposes the
half-built state live; move ``CURRENT`` aside first (see this package's README).

Both roots may be the same directory when one drive holds everything; the raw
root may be null on a machine that only serves. Every path derives from a
:class:`ReleasePaths`, so relocating either half (a different drive, or the
eventual S3 prefix) is a config change. Nothing here touches the network or
DuckDB — it's pure path algebra, safe to import and call without the corpus
present.
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
#: the **parquet** root, beside the data it names. A plain text file so it's
#: trivially inspectable and editable — parking it is how you take a corpus
#: offline without deleting anything.
CURRENT_FILE = "CURRENT"


def raw_root() -> Path | None:
    """Where downloaded shards live, or None when this machine doesn't download.

    Returns:
        ``config.storage.s2.raw`` (already anchored to the repo root if it was
        relative), or None. Only ``download``/``ingest`` need it — serving
        doesn't.
    """
    return config.storage.s2.raw


def parquet_root() -> Path | None:
    """Where the ingested Parquet and ``CURRENT`` live — the serving root.

    Returns:
        ``config.storage.s2.parquet`` (anchored the same way), or None when the
        corpus is off, in which case the app falls back to the live S2 citation
        endpoint.
    """
    return config.storage.s2.parquet


@dataclass(frozen=True)
class ReleasePaths:
    """Every path within one Datasets release, across both roots.

    Frozen and cheap to build — construct one per operation rather than caching
    it, so a config change (or a test's temp dir) is always honored. Prefer
    :func:`release_paths`, which wires both roots from config.

    Each side may be absent: a serving-only machine has no ``raw_root``, and a
    download-only one has no ``parquet_root``. Touching the paths of an
    unconfigured half raises rather than silently inventing a location.
    """

    release_id: str
    raw_root: Path | None = None
    parquet_root: Path | None = None

    def _root(self, which: str, root: Path | None) -> Path:
        """The release's subtree under one root, or a clear error when unset.

        Args:
            which: The config key to name in the error (``raw`` / ``parquet``).
            root: The configured root, or None.

        Returns:
            ``<root>/releases/<release_id>``.

        Raises:
            ValueError: When that half isn't configured — better than quietly
                defaulting to the other root, which is how Parquet once ended up
                written to a drive nobody asked for.
        """
        if root is None:
            raise ValueError(f"config.storage.s2.{which} is not set")
        return root / "releases" / self.release_id

    @property
    def raw(self) -> Path:
        """Directory holding the downloaded, un-ingested ``.gz`` shards."""
        return self._root("raw", self.raw_root) / "raw"

    def raw_dataset(self, dataset: str) -> Path:
        """The raw-shard directory for one dataset (``papers`` / ``citations``)."""
        return self.raw / dataset

    @property
    def parquet(self) -> Path:
        """Directory holding the ingested, queryable Parquet."""
        return self._root("parquet", self.parquet_root) / "parquet"

    def parquet_dataset(self, dataset: str) -> Path:
        """The Parquet directory for one dataset (``papers`` / ``citations``)."""
        return self.parquet / dataset

    @property
    def download_state(self) -> Path:
        """The per-shard download checkpoint (JSON), enabling resume.

        Beside the shards it tracks, so deleting a raw root discards its
        checkpoint with it — and a later re-download starts clean rather than
        believing shards that are gone are still on disk.
        """
        return self._root("raw", self.raw_root) / "download.json"


def release_paths(release_id: str) -> ReleasePaths:
    """One release's paths, wired from config — how callers should build them.

    Reads *both* roots in one place, so no caller has to remember there are two.
    Building :class:`ReleasePaths` by hand is easy to get subtly wrong: each root
    defaults to None, and the half you forget raises only when something touches
    it. Always returns paths — whether a given half is *usable* is the caller's
    question, asked by touching it (or by checking the root directly).

    Args:
        release_id: The release the paths are for.

    Returns:
        The release's paths across both configured roots.
    """
    return ReleasePaths(
        release_id=release_id, raw_root=raw_root(), parquet_root=parquet_root()
    )


def current_release_file(root: Path) -> Path:
    """The ``CURRENT`` pointer's path under a **parquet** root."""
    return root / CURRENT_FILE


def read_current_release(root: Path) -> str | None:
    """The active (fully ingested) release id, or None when none is marked.

    Args:
        root: The **parquet** root — ``CURRENT`` sits beside the data it names.

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
        root: The **parquet** root (created if missing).
        release_id: The release id to activate — written verbatim.
    """
    root.mkdir(parents=True, exist_ok=True)
    current_release_file(root).write_text(release_id + "\n", encoding="utf-8")
