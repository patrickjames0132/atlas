"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
The corpus's single-root on-disk layout and the CURRENT-release pointer.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

import pytest

from atlas.config import config
from atlas.integrations.semantic_scholar.corpus.paths import (
    ReleasePaths,
    read_current_release,
    release_paths,
    write_current_release,
)


def test_both_halves_hang_off_the_one_root(tmp_path):
    """Everything lives under the single root: shards + their checkpoint and the
    queryable Parquet, each in its subtree under releases/<id>/."""
    paths = ReleasePaths(release_id="2026-07-07", root=tmp_path)
    base = tmp_path / "releases" / "2026-07-07"
    assert paths.raw_dataset("papers") == base / "raw" / "papers"
    assert paths.download_state == base / "download.json"
    assert paths.parquet_dataset("citations") == base / "parquet" / "citations"


def test_touching_paths_without_a_corpus_raises(tmp_path):
    """A machine without a corpus has no root. Asking for its paths is a
    mistake worth surfacing — the alternative (defaulting somewhere) is how
    Parquet once got written to a drive nobody asked for."""
    paths = ReleasePaths(release_id="2026-07-07")
    with pytest.raises(ValueError, match=r"storage\.s2_corpus"):
        _ = paths.raw
    with pytest.raises(ValueError, match=r"storage\.s2_corpus"):
        _ = paths.parquet
    with pytest.raises(ValueError, match=r"storage\.s2_corpus"):
        _ = paths.download_state


def test_release_paths_wires_the_root_from_config(monkeypatch, tmp_path):
    """`release_paths` is how callers should build these — by hand, the root
    defaults to None and raises only when touched."""
    monkeypatch.setattr(config.storage, "s2_corpus", tmp_path / "s2corpus")
    paths = release_paths("2026-07-07")
    assert paths.raw.is_relative_to(tmp_path / "s2corpus")
    assert paths.parquet.is_relative_to(tmp_path / "s2corpus")


def test_current_release_roundtrip(tmp_path):
    """Writing then reading CURRENT returns the same release id."""
    assert read_current_release(tmp_path) is None
    write_current_release(tmp_path, "2026-07-07")
    assert read_current_release(tmp_path) == "2026-07-07"


def test_current_release_blank_is_none(tmp_path):
    """An empty CURRENT file reads as no active release."""
    (tmp_path / "CURRENT").write_text("  \n", encoding="utf-8")
    assert read_current_release(tmp_path) is None
