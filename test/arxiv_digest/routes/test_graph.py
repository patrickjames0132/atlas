"""Graph & paper routes: id normalization at the door, the error taxonomy
(400/404/502 vs degrade-to-unavailable), proxy rewriting, and the SSRF lock."""

from __future__ import annotations

from arxiv_digest.integrations import semantic_scholar
from arxiv_digest.routes import graph as graph_routes
from arxiv_digest.services.graph import Counts, Graph, Node, Seed


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
        counts=Counts(references=0, citations=0, similar=0, nodes=1),
    )


def test_graph_normalizes_pasted_urls_and_serializes_the_model(client, monkeypatch):
    seen = {}

    def fake_build(seed, refresh=False):
        seen["seed"], seen["refresh"] = seed, refresh
        return make_graph()

    monkeypatch.setattr(graph_routes.graph_service, "build_graph", fake_build)
    response = client.get("/api/graph?seed=https://arxiv.org/abs/1312.5602v2&refresh=1")
    assert response.status_code == 200
    assert seen == {"seed": "1312.5602", "refresh": True}  # URL + version stripped
    assert response.json["seed"]["id"] == "s2id01"
    assert response.json["counts"]["nodes"] == 1


def test_graph_error_taxonomy(client, monkeypatch):
    assert client.get("/api/graph").status_code == 400  # missing seed

    monkeypatch.setattr(
        graph_routes.graph_service, "build_graph", lambda seed, refresh=False: None
    )
    assert client.get("/api/graph?seed=1312.5602").status_code == 404  # unknown paper

    def s2_down(seed, refresh=False):
        raise semantic_scholar.S2Error("rate limited")

    monkeypatch.setattr(graph_routes.graph_service, "build_graph", s2_down)
    assert client.get("/api/graph?seed=1312.5602").status_code == 502  # S2 down


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
