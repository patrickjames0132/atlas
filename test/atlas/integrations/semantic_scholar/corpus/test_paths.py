"""The corpus's two-root on-disk layout and the CURRENT-release pointer."""

from __future__ import annotations

import pytest

from atlas.config import S2CorpusStorage, config
from atlas.integrations.semantic_scholar.corpus.paths import (
    ReleasePaths,
    read_current_release,
    release_paths,
    write_current_release,
)


def _use_roots(monkeypatch, raw, parquet):
    """Point config at the given corpus roots (either may be None)."""
    monkeypatch.setattr(config.storage, "s2", S2CorpusStorage(raw=raw, parquet=parquet))


def test_each_half_hangs_off_its_own_root(tmp_path):
    """The halves live on separate roots: shards + their checkpoint on one, the
    queryable Parquet on the other, each under releases/<id>/."""
    shards, fast = tmp_path / "slow", tmp_path / "fast"
    paths = ReleasePaths(release_id="2026-07-07", raw_root=shards, parquet_root=fast)
    assert paths.raw_dataset("papers") == shards / "releases" / "2026-07-07" / "raw" / "papers"
    assert paths.download_state == shards / "releases" / "2026-07-07" / "download.json"
    assert paths.parquet_dataset("citations") == (
        fast / "releases" / "2026-07-07" / "parquet" / "citations"
    )


def test_one_drive_for_everything_is_just_the_same_root_twice(tmp_path):
    """No special case for the simple setup — point both at one directory."""
    paths = ReleasePaths(release_id="2026-07-07", raw_root=tmp_path, parquet_root=tmp_path)
    base = tmp_path / "releases" / "2026-07-07"
    assert paths.raw == base / "raw"
    assert paths.parquet == base / "parquet"


def test_touching_an_unconfigured_half_raises(tmp_path):
    """A serving-only machine has no raw root. Asking for its shard paths is a
    mistake worth surfacing — the alternative (defaulting to the other root) is
    how Parquet once got written to a drive nobody asked for."""
    paths = ReleasePaths(release_id="2026-07-07", parquet_root=tmp_path)
    assert paths.parquet == tmp_path / "releases" / "2026-07-07" / "parquet"
    with pytest.raises(ValueError, match=r"storage\.s2\.raw"):
        _ = paths.raw
    with pytest.raises(ValueError, match=r"storage\.s2\.raw"):
        _ = paths.download_state


def test_release_paths_wires_both_roots_from_config(monkeypatch, tmp_path):
    """`release_paths` is how callers should build these — by hand, each root
    defaults to None and the half you forget raises only when touched."""
    _use_roots(monkeypatch, raw=tmp_path / "slow", parquet=tmp_path / "fast")
    paths = release_paths("2026-07-07")
    assert paths.raw.is_relative_to(tmp_path / "slow")
    assert paths.parquet.is_relative_to(tmp_path / "fast")


def test_release_paths_carries_a_null_half_through(monkeypatch, tmp_path):
    """Corpus off (no parquet root) still yields paths — whether a half is usable
    is the caller's question, asked by touching it."""
    _use_roots(monkeypatch, raw=tmp_path, parquet=None)
    paths = release_paths("2026-07-07")
    assert paths.raw.is_relative_to(tmp_path)
    with pytest.raises(ValueError, match=r"storage\.s2\.parquet"):
        _ = paths.parquet


def test_current_release_roundtrip(tmp_path):
    """Writing then reading CURRENT returns the same release id."""
    assert read_current_release(tmp_path) is None
    write_current_release(tmp_path, "2026-07-07")
    assert read_current_release(tmp_path) == "2026-07-07"


def test_current_release_blank_is_none(tmp_path):
    """An empty CURRENT file reads as no active release."""
    (tmp_path / "CURRENT").write_text("  \n", encoding="utf-8")
    assert read_current_release(tmp_path) is None
