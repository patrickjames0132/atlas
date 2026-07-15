"""The corpus on-disk layout and the CURRENT-release pointer."""

from __future__ import annotations

from atlas.integrations.semantic_scholar.corpus.paths import (
    ReleasePaths,
    read_current_release,
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
