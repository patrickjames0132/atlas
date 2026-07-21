"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
The Datasets API client's URL parsing (no network).

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

from atlas.integrations.semantic_scholar.corpus.datasets import shard_filename


def test_shard_filename_strips_signature():
    """The stable shard name is the URL path's last segment, sans query."""
    url = (
        "https://ai2-s2ag.s3.amazonaws.com/staging/2026-07-07/citations/"
        "20260710_071652_00151_3g69z_007b2c4d.gz?X-Amz-Signature=deadbeef&X-Amz-Expires=3600"
    )
    assert shard_filename(url) == "20260710_071652_00151_3g69z_007b2c4d.gz"


def test_shard_filename_stable_across_signatures():
    """The same shard keeps one name even as its signed URL is refreshed."""
    base = "https://host/path/2026-07-07/papers/shard_007.gz"
    assert shard_filename(base + "?sig=one") == shard_filename(base + "?sig=two")
