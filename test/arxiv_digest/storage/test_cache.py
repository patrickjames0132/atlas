"""storage.cache: the shared TTL key/JSON-blob cache backing every fetch of
graph snapshots, ar5iv text/figures, and HF code links.
"""

from __future__ import annotations

import sqlite3
import time

from arxiv_digest.config import settings
from arxiv_digest.storage import cache


def _backdate(key: str, seconds_ago: float) -> None:
    """Rewrite a cached entry's created_at directly, bypassing cache.set()."""
    conn = sqlite3.connect(settings.storage.digest_db)
    conn.execute("UPDATE cache SET created_at = ? WHERE key = ?", (time.time() - seconds_ago, key))
    conn.commit()
    conn.close()


def test_set_then_get_roundtrips_json_values():
    cache.set("k", {"a": 1, "b": [1, 2, 3]})
    assert cache.get("k") == {"a": 1, "b": [1, 2, 3]}


def test_missing_key_returns_none():
    assert cache.get("nope") is None


def test_set_upserts_an_existing_key():
    cache.set("k", "first")
    cache.set("k", "second")
    assert cache.get("k") == "second"


def test_get_respects_max_age():
    cache.set("k", "value")
    _backdate("k", seconds_ago=100)
    assert cache.get("k", max_age=50) is None
    assert cache.get("k", max_age=200) == "value"


def test_get_with_no_max_age_never_expires():
    cache.set("k", "value")
    _backdate("k", seconds_ago=10_000_000)
    assert cache.get("k") == "value"


def test_corrupt_json_blob_is_treated_as_a_miss():
    cache.set("k", "placeholder")
    conn = sqlite3.connect(settings.storage.digest_db)
    conn.execute("UPDATE cache SET value = 'not json' WHERE key = ?", ("k",))
    conn.commit()
    conn.close()
    assert cache.get("k") is None


def test_delete_removes_a_key():
    cache.set("k", "value")
    cache.delete("k")
    assert cache.get("k") is None


def test_delete_is_a_noop_for_a_missing_key():
    cache.delete("never-existed")  # must not raise


def test_scan_finds_every_key_with_the_prefix():
    cache.set("graph:1", "a")
    cache.set("graph:2", "b")
    cache.set("other:1", "c")
    hits = {key: value for key, value, _created_at in cache.scan("graph:")}
    assert hits == {"graph:1": "a", "graph:2": "b"}


def test_scan_includes_stale_entries():
    """scan() takes no max_age — staleness is entirely the caller's call."""
    cache.set("graph:1", "a")
    _backdate("graph:1", seconds_ago=10_000_000)
    hits = {key: value for key, value, _created_at in cache.scan("graph:")}
    assert hits == {"graph:1": "a"}


def test_scan_prefix_special_chars_are_escaped():
    """Literal '%' and '_' in the prefix must not act as SQL LIKE wildcards."""
    cache.set("a%b", "percent literal")
    cache.set("a_b", "underscore literal")
    cache.set("aXb", "would match both patterns above if wildcards were live")
    percent_hits = {key: value for key, value, _created_at in cache.scan("a%b")}
    underscore_hits = {key: value for key, value, _created_at in cache.scan("a_b")}
    assert percent_hits == {"a%b": "percent literal"}
    assert underscore_hits == {"a_b": "underscore literal"}
