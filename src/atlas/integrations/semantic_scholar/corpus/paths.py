"""On-disk layout of the offline Semantic Scholar corpus.

The corpus root (``config.storage.s2_corpus_dir``) holds one subtree per
monthly Datasets **release**, plus a ``CURRENT`` pointer naming the release the
app should query. Isolating each release means a fresh monthly pull can be
downloaded and ingested alongside the live one, and only flipped to ``CURRENT``
once it's complete — the app never reads a half-ingested release.

    <corpus_dir>/
      CURRENT                        <- text file: the active release_id
      releases/
        2026-07-07/
          raw/papers/*.gz            <- downloaded JSONL.gz shards
          raw/citations/*.gz
          parquet/papers/*.parquet   <- ingested, queryable
          parquet/citations/bucket=NNN/*.parquet
          download.json              <- per-shard download checkpoint

Every path in the corpus derives from a :class:`ReleasePaths`, so relocating
the corpus (a different drive, or the eventual S3 prefix) is a one-line config
change. Nothing here touches the network or DuckDB — it's pure path algebra,
so it's safe to import and call without the corpus present.
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

#: Filename of the corpus-root pointer naming the active (fully ingested)
#: release. A plain text file so it's trivially inspectable and editable.
CURRENT_FILE = "CURRENT"


def corpus_root() -> Path | None:
    """The configured corpus root, or None when the feature is off.

    Returns:
        ``config.storage.s2_corpus_dir`` (already anchored to the repo root if
        it was relative), or None when unset — in which case the app falls back
        to the live S2 citation endpoint.
    """
    return config.storage.s2_corpus_dir


@dataclass(frozen=True)
class ReleasePaths:
    """Every path within one Datasets release, derived from the corpus root.

    Frozen and cheap to build — construct one per operation rather than caching
    it, so a config change (or a test's temp dir) is always honored.
    """

    root: Path
    release_id: str

    @property
    def base(self) -> Path:
        """The release's own subtree under ``<root>/releases/<release_id>``."""
        return self.root / "releases" / self.release_id

    @property
    def raw(self) -> Path:
        """Directory holding the downloaded, un-ingested ``.gz`` shards."""
        return self.base / "raw"

    def raw_dataset(self, dataset: str) -> Path:
        """The raw-shard directory for one dataset (``papers`` / ``citations``)."""
        return self.raw / dataset

    @property
    def parquet(self) -> Path:
        """Directory holding the ingested, queryable Parquet."""
        return self.base / "parquet"

    def parquet_dataset(self, dataset: str) -> Path:
        """The Parquet directory for one dataset (``papers`` / ``citations``)."""
        return self.parquet / dataset

    @property
    def download_state(self) -> Path:
        """The per-shard download checkpoint (JSON), enabling resume."""
        return self.base / "download.json"


def current_release_file(root: Path) -> Path:
    """The corpus-root pointer file naming the active release."""
    return root / CURRENT_FILE


def read_current_release(root: Path) -> str | None:
    """The active (fully ingested) release id, or None when none is marked.

    Args:
        root: The corpus root directory.

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
        root: The corpus root directory (created if missing).
        release_id: The release id to activate — written verbatim.
    """
    root.mkdir(parents=True, exist_ok=True)
    current_release_file(root).write_text(release_id + "\n", encoding="utf-8")
