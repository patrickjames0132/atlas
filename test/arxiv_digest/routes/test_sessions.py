"""Saved-session routes: the save/list/get/delete round trip against the
real store (on the per-test temp DB), plus the validation and error edges."""

from __future__ import annotations

from arxiv_digest.routes import sessions as sessions_routes

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
