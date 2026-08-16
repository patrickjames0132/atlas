"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
Saved-session routes: the save/list/get/delete round trip against the
real store (on the per-test temp DB), plus the validation and error edges.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

from atlas.routes import sessions as sessions_routes

BLOB = {
    "name": "atari deep dive",
    "seed": {"id": "s2id01", "title": "Playing Atari"},
    "nodes": [{"id": "s2id01"}, {"id": "node02"}],
    "edges": [],
    "chat": [{"role": "user", "content": "q"}],
}


def test_save_list_get_delete_round_trip(client):
    saved = client.post("/api/sessions", json=BLOB).json
    assert saved["name"] == "atari deep dive"
    session_id = saved["id"]

    listed = client.get("/api/sessions").json["sessions"]
    assert [row["id"] for row in listed] == [session_id]
    assert "nodes" not in listed[0]  # metadata only, no payload

    # The store returns metadata + the blob nested under "data".
    full = client.get(f"/api/sessions/{session_id}").json
    assert full["data"]["nodes"] == BLOB["nodes"]
    assert full["data"]["chat"] == BLOB["chat"]
    assert full["n_nodes"] == 2

    assert client.delete(f"/api/sessions/{session_id}").json == {"deleted": True}
    assert client.get("/api/sessions").json == {"sessions": []}


def test_save_with_id_overwrites(client):
    session_id = client.post("/api/sessions", json=BLOB).json["id"]
    renamed = {**BLOB, "id": session_id, "name": "renamed"}
    assert client.post("/api/sessions", json=renamed).json["id"] == session_id
    sessions = client.get("/api/sessions").json["sessions"]
    assert len(sessions) == 1 and sessions[0]["name"] == "renamed"


def test_save_requires_nonempty_nodes(client):
    assert client.post("/api/sessions", json={}).status_code == 400
    assert client.post("/api/sessions", json={"nodes": []}).status_code == 400
    assert client.post("/api/sessions", json={"nodes": "not-a-list"}).status_code == 400


def test_store_failure_returns_a_canned_500(client, monkeypatch):
    def boom(payload, session_id=None):
        raise RuntimeError("disk full at /very/private/path")

    monkeypatch.setattr(sessions_routes.sessions_service, "save_session", boom)
    response = client.post("/api/sessions", json=BLOB)
    assert response.status_code == 500
    assert "/very/private/path" not in response.json["error"]  # details stay in the log


def test_get_unknown_session_is_404_and_delete_is_idempotent(client):
    assert client.get("/api/sessions/nope").status_code == 404
    assert client.delete("/api/sessions/nope").json == {"deleted": False}


def test_rename_changes_the_name_without_touching_the_snapshot(client):
    """A name is metadata. Editing it used to mean re-saving the whole blob,
    which is only possible for the session you have open — not for the other
    twelve in a list."""
    saved = client.post("/api/sessions", json={"name": "First try", "nodes": [{"id": "a"}]}).json
    assert client.patch(f"/api/sessions/{saved['id']}", json={"name": "Attention map"}).json == {
        "renamed": True
    }
    reopened = client.get(f"/api/sessions/{saved['id']}").json
    assert reopened["name"] == "Attention map"
    # The snapshot itself is untouched...
    assert reopened["data"]["nodes"] == [{"id": "a"}]
    # ...and so is the copy of the name inside it, or the next save would put
    # the old one back.
    assert reopened["data"]["name"] == "Attention map"


def test_rename_does_not_reshuffle_the_list(client):
    """The list is ordered by `updated_at`, and renaming a session isn't
    working on it — a rename that jumped it to the top would lose you the
    thing you just labelled."""
    node = [{"id": "a"}]
    older = client.post("/api/sessions", json={"name": "Older", "nodes": node}).json
    client.post("/api/sessions", json={"name": "Newer", "nodes": node})
    before = [row["name"] for row in client.get("/api/sessions").json["sessions"]]
    client.patch(f"/api/sessions/{older['id']}", json={"name": "Older, renamed"})
    after = [row["name"] for row in client.get("/api/sessions").json["sessions"]]
    assert before.index("Older") == after.index("Older, renamed")


def test_rename_validation_and_missing_session(client):
    saved = client.post("/api/sessions", json={"name": "Kept", "nodes": [{"id": "a"}]}).json
    assert client.patch(f"/api/sessions/{saved['id']}", json={}).status_code == 400
    assert client.patch(f"/api/sessions/{saved['id']}", json={"name": 7}).status_code == 400
    # A blank name is allowed — it falls back, like saving does.
    client.patch(f"/api/sessions/{saved['id']}", json={"name": "   "})
    assert client.get(f"/api/sessions/{saved['id']}").json["name"] == "Untitled session"
    # Absence isn't a 404, matching delete.
    assert client.patch("/api/sessions/nope", json={"name": "x"}).json == {"renamed": False}
