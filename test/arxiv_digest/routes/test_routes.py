"""The Flask API surface (routes/): validation, error mapping, and payload
envelopes, via the test client. Services are monkeypatched at each route
module's import site; the sessions routes run against the real (temp) store.
"""

from __future__ import annotations

from arxiv_digest.integrations import semantic_scholar as s2
from arxiv_digest.routes import graph as graph_routes
from arxiv_digest.routes import search as search_routes
from arxiv_digest.routes import sources as sources_routes

# --- /api/graph ----------------------------------------------------------------

def test_graph_requires_seed(flask_client):
    resp = flask_client.get("/api/graph")
    assert resp.status_code == 400
    assert "seed" in resp.get_json()["error"]


def test_graph_404_when_unknown(flask_client, monkeypatch):
    monkeypatch.setattr(graph_routes.graph_service, "build_graph",
                        lambda seed, refresh=False: None)
    resp = flask_client.get("/api/graph?seed=0000.00000")
    assert resp.status_code == 404


def test_graph_502_on_s2_failure(flask_client, monkeypatch):
    def boom(seed, refresh=False):
        raise s2.S2Error("throttled")
    monkeypatch.setattr(graph_routes.graph_service, "build_graph", boom)
    resp = flask_client.get("/api/graph?seed=1706.03762")
    assert resp.status_code == 502
    assert "unavailable" in resp.get_json()["error"]


def test_graph_success_and_url_seed_normalization(flask_client, monkeypatch):
    seen = {}

    def fake_build(seed, refresh=False):
        seen["seed"], seen["refresh"] = seed, refresh
        return {"seed": {"id": "x"}, "nodes": [], "edges": [], "counts": {}}
    monkeypatch.setattr(graph_routes.graph_service, "build_graph", fake_build)
    resp = flask_client.get(
        "/api/graph?seed=https://arxiv.org/abs/1706.03762v5&refresh=1")
    assert resp.status_code == 200
    assert seen == {"seed": "1706.03762", "refresh": True}  # URL + version stripped


def test_figure_proxy_locked_to_ar5iv(flask_client):
    resp = flask_client.get("/api/figure_proxy?src=https://evil.example/x.png")
    assert resp.status_code == 400  # SSRF lock: only ar5iv images pass


def test_code_links_success(flask_client, monkeypatch):
    seen = {}

    def fake(arxiv_id, refresh=False):
        seen["id"] = arxiv_id
        return {"available": True, "github": None, "models": [], "datasets": [],
                "spaces": [], "totals": {"models": 0, "datasets": 0, "spaces": 0},
                "paper_url": "https://huggingface.co/papers/1706.03762", "upvotes": 1}
    monkeypatch.setattr(graph_routes.huggingface, "get_code_links", fake)
    resp = flask_client.get("/api/paper/https%3A%2F%2Farxiv.org%2Fabs%2F1706.03762v5/code")
    assert resp.status_code == 200
    assert resp.get_json()["available"] is True
    assert seen["id"] == "1706.03762"  # URL + version stripped


def test_code_links_degrade_on_hf_failure(flask_client, monkeypatch):
    def boom(arxiv_id, refresh=False):
        raise OSError("hf down")
    monkeypatch.setattr(graph_routes.huggingface, "get_code_links", boom)
    resp = flask_client.get("/api/paper/1706.03762/code")
    assert resp.status_code == 200  # degrades, never 500s the panel
    assert resp.get_json()["available"] is False


# --- /api/arxiv_search + /api/local_search ---------------------------------------

def test_arxiv_search_maps_failure_to_502(flask_client, monkeypatch):
    def boom(q, **kw):
        raise RuntimeError("arxiv down")
    monkeypatch.setattr(search_routes.search_service, "arxiv_search", boom)
    resp = flask_client.get("/api/arxiv_search?q=attention")
    assert resp.status_code == 502
    assert resp.get_json()["ok"] is False


def test_arxiv_search_passes_filters(flask_client, monkeypatch):
    seen = {}

    def fake(q, limit, year_from, year_to, categories):
        seen.update(q=q, limit=limit, year_from=year_from, year_to=year_to,
                    categories=categories)
        return []
    monkeypatch.setattr(search_routes.search_service, "arxiv_search", fake)
    resp = flask_client.get(
        "/api/arxiv_search?q=ssm&limit=999&year_from=2020&categories=cs.LG,nope.XX")
    assert resp.status_code == 200
    assert seen["limit"] == 100  # clamped
    assert seen["year_from"] == 2020
    assert seen["categories"] == ["cs.LG"]  # invalid codes dropped server-side


def test_local_search_never_errors(flask_client, monkeypatch):
    def boom(q, **kw):
        raise RuntimeError("cache corrupt")
    monkeypatch.setattr(search_routes.search_service, "local_search", boom)
    resp = flask_client.get("/api/local_search?q=attention")
    assert resp.status_code == 200
    assert resp.get_json() == {"q": "attention", "count": 0, "papers": []}


# --- /api/sessions CRUD (real temp store) ----------------------------------------

SESSION = {"name": "my graph", "seed": {"id": "p1"}, "layout": "force",
           "nodes": [{"id": "p1"}], "edges": [], "chat": [], "beats": []}


def test_sessions_crud_round_trip(flask_client):
    # Save requires nodes.
    assert flask_client.post("/api/sessions", json={"name": "x"}).status_code == 400

    created = flask_client.post("/api/sessions", json=SESSION).get_json()
    assert created["id"] and created["name"] == "my graph"

    listed = flask_client.get("/api/sessions").get_json()["sessions"]
    assert [s["id"] for s in listed] == [created["id"]]

    full = flask_client.get(f"/api/sessions/{created['id']}").get_json()
    assert full["data"]["nodes"] == [{"id": "p1"}]  # payload nests under "data"

    # Overwrite in place by id.
    updated = dict(SESSION, id=created["id"], name="renamed")
    saved = flask_client.post("/api/sessions", json=updated).get_json()
    assert saved["id"] == created["id"] and saved["name"] == "renamed"
    assert len(flask_client.get("/api/sessions").get_json()["sessions"]) == 1

    assert flask_client.delete(f"/api/sessions/{created['id']}").get_json()["deleted"] is True
    assert flask_client.get(f"/api/sessions/{created['id']}").status_code == 404
    assert flask_client.delete(f"/api/sessions/{created['id']}").get_json()["deleted"] is False


# --- /api/sources ----------------------------------------------------------------

def test_sources_add_requires_file_or_url(flask_client):
    resp = flask_client.post("/api/sources", json={})
    assert resp.status_code == 400
    assert "PDF file or a url" in resp.get_json()["error"]


def test_sources_add_maps_source_error_to_400(flask_client, monkeypatch):
    def scanned(url, title=None):
        raise sources_routes.sources_service.SourceError("scanned/image-only")
    monkeypatch.setattr(sources_routes.sources_service, "ingest_url", scanned)
    resp = flask_client.post("/api/sources", json={"url": "https://x.test/doc"})
    assert resp.status_code == 400
    assert "scanned" in resp.get_json()["error"]


def test_sources_add_url_success(flask_client, monkeypatch):
    record = {"id": "s1", "title": "Doc", "kind": "url", "origin": "https://x.test/doc",
              "pages": None, "n_chunks": 3, "created_at": "now"}
    monkeypatch.setattr(sources_routes.sources_service, "ingest_url",
                        lambda url, title=None: record)
    resp = flask_client.post("/api/sources", json={"url": "https://x.test/doc"})
    assert resp.status_code == 200 and resp.get_json() == record


# --- SSE routes (teacher) ----------------------------------------------------------


def sse_events(resp) -> list[tuple[str, str]]:
    """Parse an SSE body into (event, data-json-string) pairs."""
    out = []
    for frame in resp.get_data(as_text=True).split("\n\n"):
        if not frame.strip():
            continue
        lines = dict(line.split(": ", 1) for line in frame.split("\n"))
        out.append((lines["event"], lines["data"]))
    return out


def test_ask_validation(flask_client):
    assert flask_client.post("/api/ask", json={}).status_code == 400
    assert flask_client.post("/api/ask", json={"question": "why?"}).status_code == 400


def test_ask_streams_tokens_then_cited_then_done(flask_client, monkeypatch):
    import json

    from arxiv_digest.routes import teacher as teacher_routes

    def fake_stream(question, seed, nodes, history):
        yield ("token", "Half ")
        yield ("token", "answer.")
        yield ("cited", ["p1"])
    monkeypatch.setattr(teacher_routes.teacher_service, "agentic_available", lambda: False)
    monkeypatch.setattr(teacher_routes.teacher_service, "answer_stream", fake_stream)

    resp = flask_client.post("/api/ask", json={
        "question": "why?", "seed": {"id": "p1"}, "nodes": [{"id": "p1"}],
        "session_id": "sess-1",
    })
    assert resp.mimetype == "text/event-stream"
    events = sse_events(resp)
    kinds = [k for k, _ in events]
    assert kinds == ["token", "token", "cited", "done"]
    assert json.loads(events[2][1]) == {"node_ids": ["p1"]}

    # The turn persisted into the session store (user + assistant).
    convo = teacher_routes._QA_SESSIONS["sess-1"]
    assert convo[-1] == {"role": "assistant", "content": "Half answer."}


def test_ask_persists_history_without_figure_markers(flask_client, monkeypatch):
    """<<FIG n>> markers are render directives — they stream to the frontend
    but must NOT be persisted into the model's conversation history (a model
    that sees an old marker skips placing the fresh one next turn)."""
    from arxiv_digest.routes import teacher as teacher_routes

    def fake_stream(question, seed, nodes, history):
        yield ("token", "See the architecture:\n")
        yield ("token", "<<FIG 1>>\n")
        yield ("token", "as shown above.")
        yield ("cited", ["p1"])
    monkeypatch.setattr(teacher_routes.teacher_service, "agentic_available", lambda: False)
    monkeypatch.setattr(teacher_routes.teacher_service, "answer_stream", fake_stream)

    resp = flask_client.post("/api/ask", json={
        "question": "show me", "seed": {}, "nodes": [{"id": "p1"}], "session_id": "sess-fig",
    })
    # The marker reaches the frontend intact (it splits the bubble on it)...
    assert "<<FIG 1>>" in resp.get_data(as_text=True)
    # ...but the persisted turn is marker-free prose.
    persisted = teacher_routes._QA_SESSIONS["sess-fig"][-1]["content"]
    assert persisted == "See the architecture:\nas shown above."


def test_ask_stream_failure_emits_error_and_skips_persist(flask_client, monkeypatch):
    from arxiv_digest.routes import teacher as teacher_routes

    def broken(question, seed, nodes, history):
        yield ("token", "par")
        raise RuntimeError("model fell over")
    monkeypatch.setattr(teacher_routes.teacher_service, "agentic_available", lambda: False)
    monkeypatch.setattr(teacher_routes.teacher_service, "answer_stream", broken)

    resp = flask_client.post("/api/ask", json={
        "question": "q", "seed": {}, "nodes": [{"id": "p1"}], "session_id": "sess-err",
    })
    kinds = [k for k, _ in sse_events(resp)]
    assert kinds == ["token", "error"]
    assert "sess-err" not in teacher_routes._QA_SESSIONS  # nothing persisted


def test_lecture_requires_nodes(flask_client):
    assert flask_client.post("/api/lecture", json={}).status_code == 400


def test_ask_sources_400_when_library_unavailable(flask_client, monkeypatch):
    from arxiv_digest.routes import teacher as teacher_routes

    monkeypatch.setattr(teacher_routes.sources, "available", lambda: False)
    resp = flask_client.post("/api/ask_sources", json={"question": "q"})
    assert resp.status_code == 400
    assert "unavailable" in resp.get_json()["error"]
