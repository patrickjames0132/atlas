"""Graph & paper routes: id normalization at the door, the error taxonomy
(400/404/502 vs degrade-to-unavailable), proxy rewriting, and the SSRF lock."""

from __future__ import annotations

import json

from atlas.config import config
from atlas.integrations import openalex, semantic_scholar
from atlas.routes import graph as graph_routes
from atlas.services.graph import Counts, Graph, Node, Seed


def frames(response) -> list[tuple[str, dict]]:
    """Parse an SSE response body into ``(event, data)`` tuples."""
    parsed = []
    for chunk in response.data.decode().strip().split("\n\n"):
        event_line, data_line = chunk.split("\n")
        parsed.append(
            (event_line.removeprefix("event: "), json.loads(data_line.removeprefix("data: ")))
        )
    return parsed


def make_graph() -> Graph:
    seed_node = Node(
        id="s2id01", arxiv_id="1312.5602", title="Playing Atari", abstract=None,
        tldr=None, year=2013, month=None, pub_date=None, citation_count=10000,
        authors=None, url="https://example.org/s2id01", rels=["seed"], is_seed=True,
    )
    return Graph(
        seed=Seed(arxiv_id="1312.5602", id="s2id01", title="Playing Atari"),
        nodes=[seed_node],
        edges=[],
        counts=Counts(references=0, citations=0, similar=0, latest=0, nodes=1),
    )


def test_graph_normalizes_pasted_urls_and_threads_the_provider(client, monkeypatch):
    seen = {}

    def fake_build(seed, provider="s2", refresh=False):
        seen["seed"], seen["provider"], seen["refresh"] = seed, provider, refresh
        return make_graph()

    monkeypatch.setattr(graph_routes.graph_service, "build_graph", fake_build)
    response = client.get(
        "/api/graph?seed=https://arxiv.org/abs/1312.5602v2&provider=openalex&refresh=1"
    )
    assert response.status_code == 200
    # URL + version stripped; the chosen provider is threaded through.
    assert seen == {"seed": "1312.5602", "provider": "openalex", "refresh": True}
    assert response.json["seed"]["id"] == "s2id01"
    assert response.json["counts"]["nodes"] == 1


def test_graph_invalid_provider_falls_back_to_default(client, monkeypatch):
    """A missing / bogus provider degrades to config.graph.default_provider."""
    seen = {}

    def fake_build(seed, provider="s2", refresh=False):
        seen["provider"] = provider
        return make_graph()

    monkeypatch.setattr(graph_routes.graph_service, "build_graph", fake_build)
    monkeypatch.setattr(config.graph, "default_provider", "s2")
    client.get("/api/graph?seed=1312.5602&provider=bogus")
    assert seen["provider"] == "s2"


def test_graph_error_taxonomy(client, monkeypatch):
    assert client.get("/api/graph").status_code == 400  # missing seed

    monkeypatch.setattr(
        graph_routes.graph_service, "build_graph", lambda seed, provider="s2", refresh=False: None
    )
    assert client.get("/api/graph?seed=1312.5602").status_code == 404  # unknown paper

    def s2_down(seed, provider="s2", refresh=False):
        raise semantic_scholar.S2Error("rate limited")

    monkeypatch.setattr(graph_routes.graph_service, "build_graph", s2_down)
    assert client.get("/api/graph?seed=1312.5602").status_code == 502  # S2 down

    def openalex_down(seed, provider="s2", refresh=False):
        raise openalex.OpenAlexError("over budget")

    monkeypatch.setattr(graph_routes.graph_service, "build_graph", openalex_down)
    # An OpenAlex failure on the OpenAlex path is a 502 too, named for the provider.
    response = client.get("/api/graph?seed=1312.5602&provider=openalex")
    assert response.status_code == 502
    assert "OpenAlex" in response.json["error"]


def test_graph_stream_reports_progress_then_the_graph(client, monkeypatch):
    def fake_build(seed, provider="s2", refresh=False, on_progress=None):
        # A real build fires coarse stages through on_progress before returning.
        if on_progress:
            on_progress(1, 4, "Resolving seed paper…")
            on_progress(3, 4, "Fetching citations…")
        return make_graph()

    monkeypatch.setattr(graph_routes.graph_service, "build_graph", fake_build)
    response = client.get("/api/graph/stream?seed=https://arxiv.org/abs/1312.5602v2")
    assert response.status_code == 200
    assert response.mimetype == "text/event-stream"
    events = frames(response)
    assert [event for event, _ in events] == ["progress", "progress", "done"]
    assert events[0][1] == {"done": 1, "total": 4, "label": "Resolving seed paper…"}
    assert events[-1][1]["seed"]["id"] == "s2id01"  # the serialized graph


def test_graph_stream_error_frames(client, monkeypatch):
    # Missing seed is a pre-stream 400 (JSON), never an SSE frame.
    assert client.get("/api/graph/stream").status_code == 400

    monkeypatch.setattr(
        graph_routes.graph_service,
        "build_graph",
        lambda seed, provider="s2", refresh=False, on_progress=None: None,
    )
    events = frames(client.get("/api/graph/stream?seed=1312.5602"))
    assert events[-1][0] == "error"  # unknown paper -> error frame, not 404

    def s2_down(seed, provider="s2", refresh=False, on_progress=None):
        raise semantic_scholar.S2Error("rate limited")

    monkeypatch.setattr(graph_routes.graph_service, "build_graph", s2_down)
    events = frames(client.get("/api/graph/stream?seed=1312.5602"))
    assert events == [("error", {"message": "Semantic Scholar is unavailable — try again."})]


def test_paper_prefixes_arxiv_ids_but_not_raw_paperids(client, monkeypatch):
    lookups = []

    def fake_get_paper(ref):
        lookups.append(ref)
        return {"id": "s2id01", "title": "Playing Atari"}

    monkeypatch.setattr(graph_routes.semantic_scholar, "get_paper", fake_get_paper)
    assert client.get("/api/paper/1312.5602").status_code == 200
    assert client.get("/api/paper/649def34f8be52c8b66281af98ae884c09aef38b").status_code == 200
    assert lookups == [
        "ARXIV:1312.5602",  # a real arXiv id gets the prefix
        "649def34f8be52c8b66281af98ae884c09aef38b",  # a raw S2 paperId doesn't
    ]


def test_figures_rewrites_images_to_the_proxy_and_degrades(client, monkeypatch):
    figures = {"available": True, "figures": [{"image": "https://ar5iv.org/f1.png", "caption": "c"}]}
    monkeypatch.setattr(graph_routes.arxiv, "get_figures", lambda ref: figures)
    response = client.get("/api/paper/1312.5602/figures")
    assert response.json["figures"][0]["image"] == (
        "/api/figure_proxy?src=https%3A%2F%2Far5iv.org%2Ff1.png"
    )

    def boom(ref):
        raise TimeoutError("ar5iv slow")

    monkeypatch.setattr(graph_routes.arxiv, "get_figures", boom)
    response = client.get("/api/paper/1312.5602/figures")
    assert response.status_code == 200  # degrade, never 500 the panel
    assert response.json == {"available": False, "figures": []}


def test_code_links_degrade_to_the_empty_envelope(client, monkeypatch):
    def boom(ref):
        raise TimeoutError("hf slow")

    monkeypatch.setattr(graph_routes.huggingface, "get_code_links", boom)
    response = client.get("/api/paper/1312.5602/code")
    assert response.status_code == 200
    assert response.json["available"] is False


def test_categories_degrades_on_failure(client, monkeypatch):
    tags = {"available": True, "categories": [{"code": "cs.LG", "name": "Machine Learning"}]}
    monkeypatch.setattr(graph_routes.arxiv, "get_categories", lambda ref: tags)
    response = client.get("/api/paper/1706.03762/categories")
    assert response.json == tags

    def boom(ref):
        raise TimeoutError("arxiv slow")

    monkeypatch.setattr(graph_routes.arxiv, "get_categories", boom)
    response = client.get("/api/paper/1706.03762/categories")
    assert response.status_code == 200  # degrade, never 500 the panel
    assert response.json == {"available": False, "categories": []}


def test_figure_proxy_is_locked_to_ar5iv(client, monkeypatch):
    assert client.get("/api/figure_proxy?src=https://evil.example/x.png").status_code == 400

    monkeypatch.setattr(
        graph_routes.arxiv, "fetch_image", lambda src: (b"\x89PNG", "image/png")
    )
    response = client.get(
        "/api/figure_proxy?src=https://ar5iv.labs.arxiv.org/html/1312.5602/x.png"
    )
    assert response.status_code == 200
    assert response.data == b"\x89PNG"
    assert response.headers["Cache-Control"] == "public, max-age=86400"
