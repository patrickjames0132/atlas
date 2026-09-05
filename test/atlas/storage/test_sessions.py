"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
storage.sessions: the durable exploration store (conversation + graph reference).

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


def test_blank_name_becomes_untitled_exploration():
    assert sessions.save_session(_payload(name="   "))["name"] == "Untitled exploration"


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


def test_a_graphless_exploration_is_a_valid_row():
    """A conversation held before any graph exists must be storable.

    This is the case the autosave exists for: since the landing chat became
    the front door, refusing to store a graphless sitting throws away exactly
    the work the feature promises to keep.
    """
    record = sessions.save_session(
        {"name": "What is a diffusion model?", "chat": [{"role": "user", "text": "hi"}]}
    )
    assert record["seed_id"] is None
    assert record["n_nodes"] == 0
    fetched = sessions.get_session(record["id"])
    assert fetched is not None
    assert fetched["data"]["chat"] == [{"role": "user", "text": "hi"}]


def test_node_count_spans_the_reference_and_the_discoveries():
    """A reference-shaped save counts the graph it names plus what was found.

    Nothing in this process has fetched the graph, so the base count can only
    come from what the reference recorded; the agent's discoveries are stored
    outright and add to it.
    """
    record = sessions.save_session(
        {
            "name": "Reference shaped",
            "graph_ref": {
                "seed": {"id": "S2:123", "title": "Attention Is All You Need"},
                "seed_ref": "1706.03762",
                "n_nodes": 40,
            },
            "discovered_nodes": [{"id": "S2:999"}, {"id": "S2:998"}],
        }
    )
    assert record["n_nodes"] == 42


def test_a_legacy_inline_graph_still_counts_and_restores():
    """Rows written before the reference shape keep working, untouched."""
    record = sessions.save_session(_payload())
    assert record["n_nodes"] == 2
    fetched = sessions.get_session(record["id"])
    assert fetched is not None
    # The blob is handed back verbatim, so the frontend can spot `nodes` and
    # use them directly instead of rebuilding.
    assert fetched["data"]["nodes"] == [{"id": "S2:123"}, {"id": "S2:456"}]


def test_overwriting_in_place_preserves_created_at():
    """The autosave re-POSTs the same id constantly; that must not fork rows."""
    first = sessions.save_session(_payload())
    again = sessions.save_session(_payload(name="Renamed by a later save"), session_id=first["id"])
    assert again["id"] == first["id"]
    assert again["created_at"] == first["created_at"]
    assert len(sessions.list_sessions()) == 1


def test_the_seed_columns_are_lifted_from_either_blob_shape():
    """The list view reads these columns instead of parsing every blob, so
    they must survive the seed moving down into ``graph_ref``."""
    reference = sessions.save_session(
        {
            "name": "Reference shaped",
            "graph_ref": {
                "seed": {"id": "S2:123", "title": "Attention Is All You Need"},
                "seed_ref": "1706.03762",
            },
        }
    )
    assert reference["seed_id"] == "S2:123"
    assert reference["seed_title"] == "Attention Is All You Need"

    # Legacy blobs keep the seed at the top level.
    assert sessions.save_session(_payload())["seed_id"] == "S2:123"

    # A graphless exploration has no seed at all, and stores NULL.
    graphless = sessions.save_session({"name": "Just a chat", "chat": []})
    assert graphless["seed_id"] is None
    assert graphless["seed_title"] is None
