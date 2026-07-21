"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
storage.sessions: the durable saved-workspace store (graph + transcript).

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

import sqlite3

from atlas.config import config
from atlas.storage import sessions


def _touch(session_id: str, updated_at: float) -> None:
    """Force a session's updated_at directly, to make list ordering deterministic."""
    conn = sqlite3.connect(config.storage.sessions_db)
    conn.execute(
        "UPDATE saved_sessions SET updated_at = ? WHERE id = ?", (updated_at, session_id)
    )
    conn.commit()
    conn.close()


def _payload(**overrides) -> dict:
    """A minimal valid session payload, with overrides for the fields under test."""
    base = {
        "name": "Attention mechanisms",
        "seed": {"id": "S2:123", "title": "Attention Is All You Need"},
        "nodes": [{"id": "S2:123"}, {"id": "S2:456"}],
    }
    base.update(overrides)
    return base


def test_save_session_creates_a_new_session_with_a_fresh_id():
    record = sessions.save_session(_payload())
    assert record["id"]
    assert record["name"] == "Attention mechanisms"
    assert record["seed_id"] == "S2:123"
    assert record["seed_title"] == "Attention Is All You Need"
    assert record["n_nodes"] == 2
    assert record["created_at"] == record["updated_at"]


def test_blank_name_becomes_untitled_session():
    assert sessions.save_session(_payload(name="   "))["name"] == "Untitled session"


def test_get_session_returns_the_full_payload():
    saved = sessions.save_session(_payload())
    fetched = sessions.get_session(saved["id"])
    assert fetched is not None
    assert fetched["data"] == _payload()
    assert fetched["name"] == "Attention mechanisms"


def test_get_session_returns_none_for_a_missing_id():
    assert sessions.get_session("nonexistent") is None


def test_get_session_with_corrupt_blob_reports_empty_data():
    saved = sessions.save_session(_payload())
    conn = sqlite3.connect(config.storage.sessions_db)
    conn.execute("UPDATE saved_sessions SET data = 'not json' WHERE id = ?", (saved["id"],))
    conn.commit()
    conn.close()
    fetched = sessions.get_session(saved["id"])
    assert fetched is not None
    assert fetched["data"] == {}


def test_save_session_with_existing_id_overwrites_in_place():
    saved = sessions.save_session(_payload())
    _touch(saved["id"], updated_at=saved["updated_at"] - 100)  # force a clear time gap

    updated = sessions.save_session(_payload(name="Renamed"), session_id=saved["id"])

    assert updated["id"] == saved["id"]
    assert updated["name"] == "Renamed"
    assert updated["created_at"] == saved["created_at"]  # preserved, not reset
    assert updated["updated_at"] > saved["updated_at"] - 100  # bumped


def test_save_session_with_an_unknown_id_creates_that_session():
    """Passing a session_id that doesn't exist yet still creates a row (not
    an error) — there's simply no prior created_at to preserve."""
    record = sessions.save_session(_payload(), session_id="brand-new-id")
    assert record["id"] == "brand-new-id"
    assert sessions.get_session("brand-new-id") is not None


def test_list_sessions_omits_the_data_blob():
    saved = sessions.save_session(_payload())
    (listed,) = sessions.list_sessions()
    assert listed["id"] == saved["id"]
    assert "data" not in listed


def test_list_sessions_orders_newest_updated_first():
    older = sessions.save_session(_payload(name="Older"))
    newer = sessions.save_session(_payload(name="Newer"))
    _touch(older["id"], updated_at=1000)
    _touch(newer["id"], updated_at=2000)

    names = [row["name"] for row in sessions.list_sessions()]
    assert names == ["Newer", "Older"]


def test_delete_session_removes_it_and_reports_true():
    saved = sessions.save_session(_payload())
    assert sessions.delete_session(saved["id"]) is True
    assert sessions.get_session(saved["id"]) is None


def test_delete_session_reports_false_for_a_missing_id():
    assert sessions.delete_session("nonexistent") is False
