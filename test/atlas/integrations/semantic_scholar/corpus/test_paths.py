"""The corpus on-disk layout and the CURRENT-release pointer."""

from __future__ import annotations

from atlas.config import config
from atlas.integrations.semantic_scholar.corpus.paths import (
    ReleasePaths,
    read_current_release,
    release_paths,
    write_current_release,
)


def test_release_paths_layout(tmp_path):
    """Every path hangs off the corpus root under releases/<id>/."""
    paths = ReleasePaths(root=tmp_path, release_id="2026-07-07")
    assert paths.base == tmp_path / "releases" / "2026-07-07"
    assert paths.raw_dataset("papers") == paths.base / "raw" / "papers"
    assert paths.parquet_dataset("citations") == paths.base / "parquet" / "citations"
    assert paths.download_state == paths.base / "download.json"


def test_current_release_roundtrip(tmp_path):
    """Writing then reading CURRENT returns the same release id."""
    assert read_current_release(tmp_path) is None
    write_current_release(tmp_path, "2026-07-07")
    assert read_current_release(tmp_path) == "2026-07-07"


def test_current_release_blank_is_none(tmp_path):
    """An empty CURRENT file reads as no active release."""
    (tmp_path / "CURRENT").write_text("  \n", encoding="utf-8")
    assert read_current_release(tmp_path) is None


def test_parquet_root_splits_parquet_onto_other_storage(tmp_path):
    """The Parquet half can live on a different drive from the shards: raw is
    ~400GB read once sequentially (fine on a spinning disk), the Parquet is the
    queried working set and takes the ingest's ~400k partitioned writes (not)."""
    shards, fast = tmp_path / "slow", tmp_path / "fast"
    paths = ReleasePaths(root=shards, release_id="2026-07-07", parquet_root=fast)
    # Shards, and the download checkpoint beside them, stay on the big drive.
    assert paths.raw_dataset("citations") == shards / "releases" / "2026-07-07" / "raw" / "citations"
    assert paths.download_state == shards / "releases" / "2026-07-07" / "download.json"
    # The Parquet mirrors the same release subtree on the fast one.
    assert paths.parquet_dataset("citations") == (
        fast / "releases" / "2026-07-07" / "parquet" / "citations"
    )


def test_parquet_root_unset_keeps_parquet_under_the_corpus_root(tmp_path):
    """The default (and the right answer once one drive holds everything)."""
    paths = ReleasePaths(root=tmp_path, release_id="2026-07-07")
    assert paths.parquet_root is None
    assert paths.parquet == paths.base / "parquet"


def test_release_paths_wires_both_roots_from_config(tmp_path, monkeypatch):
    """`release_paths` is how callers should build these — constructing
    ReleasePaths by hand defaults parquet_root to None and would silently ignore
    the configured split."""
    monkeypatch.setattr(config.storage, "s2_corpus_dir", tmp_path / "slow")
    monkeypatch.setattr(config.storage, "s2_corpus_parquet_dir", tmp_path / "fast")
    paths = release_paths("2026-07-07")
    assert paths.root == tmp_path / "slow"
    assert paths.parquet_root == tmp_path / "fast"
    assert paths.parquet.is_relative_to(tmp_path / "fast")


def test_release_paths_none_when_corpus_off(monkeypatch):
    """No corpus dir → no paths, and callers fall back to the live S2 endpoint."""
    monkeypatch.setattr(config.storage, "s2_corpus_dir", None)
    assert release_paths("2026-07-07") is None
