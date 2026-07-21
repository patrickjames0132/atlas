"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
Graph & paper routes: id normalization at the door, the error taxonomy
(400/404/502 vs degrade-to-unavailable), proxy rewriting, and the SSRF lock.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

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

    def fake_build(seed, provider="s2", refresh=False, shape=None):
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
    """A missing / bogus provider degrades to config.providers.default_provider."""
    seen = {}

    def fake_build(seed, provider="s2", refresh=False, shape=None):
        seen["provider"] = provider
        return make_graph()

    monkeypatch.setattr(graph_routes.graph_service, "build_graph", fake_build)
    monkeypatch.setattr(config.providers, "default_provider", "s2")
    client.get("/api/graph?seed=1312.5602&provider=bogus")
    assert seen["provider"] == "s2"


def test_graph_error_taxonomy(client, monkeypatch):
    assert client.get("/api/graph").status_code == 400  # missing seed

    monkeypatch.setattr(
        graph_routes.graph_service, "build_graph", lambda seed, provider="s2", refresh=False, shape=None: None
    )
    assert client.get("/api/graph?seed=1312.5602").status_code == 404  # unknown paper

    def s2_down(seed, provider="s2", refresh=False, shape=None):
        raise semantic_scholar.S2Error("rate limited")

    monkeypatch.setattr(graph_routes.graph_service, "build_graph", s2_down)
    assert client.get("/api/graph?seed=1312.5602").status_code == 502  # S2 down

    def openalex_down(seed, provider="s2", refresh=False, shape=None):
        raise openalex.OpenAlexError("over budget")

    monkeypatch.setattr(graph_routes.graph_service, "build_graph", openalex_down)
    # An OpenAlex failure on the OpenAlex path is a 502 too, named for the provider.
    response = client.get("/api/graph?seed=1312.5602&provider=openalex")
    assert response.status_code == 502
    assert "OpenAlex" in response.json["error"]


def test_graph_stream_reports_progress_then_the_graph(client, monkeypatch):
    def fake_build(seed, provider="s2", refresh=False, shape=None, on_progress=None):
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
        lambda seed, provider="s2", refresh=False, shape=None, on_progress=None: None,
    )
    events = frames(client.get("/api/graph/stream?seed=1312.5602"))
    assert events[-1][0] == "error"  # unknown paper -> error frame, not 404

    def s2_down(seed, provider="s2", refresh=False, shape=None, on_progress=None):
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


def test_paper_hydrates_from_openalex_when_provider_is_openalex(client, monkeypatch):
    """Under provider=openalex the detail route hydrates via openalex.get_paper
    (by the node id, not an ARXIV: prefix), not S2."""
    seen = {}

    def fake_oa_get(ref):
        seen["ref"] = ref
        return {"id": ref, "title": "From OpenAlex", "fields_of_study": ["Topic Modeling"]}

    def s2_forbidden(ref):
        raise AssertionError("S2 must not be called under the OpenAlex provider")

    monkeypatch.setattr(graph_routes.openalex, "get_paper", fake_oa_get)
    monkeypatch.setattr(graph_routes.semantic_scholar, "get_paper", s2_forbidden)
    response = client.get("/api/paper/DOI:10.65/abc?provider=openalex")
    assert response.status_code == 200
    assert seen["ref"] == "DOI:10.65/abc"  # node id passed through untouched
    assert response.json["title"] == "From OpenAlex"


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
    # The ar5iv failure falls through to OA-PDF mining — keep THAT offline
    # too, and unavailable, so the route's final degrade shape is exercised.
    monkeypatch.setattr(
        graph_routes.pdf_service,
        "get_pdf_floats",
        lambda url: {"available": False, "token": "t0", "floats": []},
    )
    response = client.get("/api/paper/1312.5602/figures")
    assert response.status_code == 200  # degrade, never 500 the panel
    assert response.json == {"available": False, "figures": []}


def test_figures_fall_back_to_mined_pdf_floats(client, monkeypatch):
    """No ar5iv render → the paper's OA PDF is mined; mined floats come back
    as /api/pdf_figure image URLs. For an arXiv ref the PDF URL needs no
    provider lookup (arxiv.org/pdf is always OA)."""
    monkeypatch.setattr(
        graph_routes.arxiv, "get_figures", lambda ref: {"available": False, "figures": []}
    )
    seen = {}

    def fake_floats(url):
        seen["url"] = url
        return {
            "available": True,
            "token": "abc123",
            "floats": [
                {"kind": "figure", "page": 3, "caption": "Figure 1: The model.", "region": [0, 0, 1, 1]},
                {"kind": "table", "page": 5, "caption": "Table 2: Results.", "region": [0, 0, 1, 1]},
            ],
        }

    monkeypatch.setattr(graph_routes.pdf_service, "get_pdf_floats", fake_floats)
    response = client.get("/api/paper/1312.5602/figures")
    assert seen["url"] == "https://arxiv.org/pdf/1312.5602"
    assert response.json == {
        "available": True,
        "figures": [
            {"image": "/api/pdf_figure/abc123/0", "caption": "Figure 1: The model."},
            {"image": "/api/pdf_figure/abc123/1", "caption": "Table 2: Results."},
        ],
    }


def test_figures_for_non_arxiv_ref_resolve_via_provider(client, monkeypatch):
    """A non-arXiv ref (a node id) skips ar5iv entirely and asks the OA-PDF
    resolver, honoring the provider param; no OA PDF → unavailable."""
    calls = {}

    def fake_resolve(node_id, provider):
        calls["args"] = (node_id, provider)
        return None

    monkeypatch.setattr(graph_routes.pdf_service, "resolve_oa_pdf", fake_resolve)
    response = client.get("/api/paper/DOI:10.1038/x/figures?provider=openalex")
    assert calls["args"] == ("DOI:10.1038/x", "openalex")
    assert response.json == {"available": False, "figures": []}


def test_pdf_figure_route_serves_png_and_404s_unknown(client, monkeypatch):
    """The mined-float image route: PNG bytes on success, 404 (not 500) for
    unknown tokens/indices."""
    monkeypatch.setattr(
        graph_routes.pdf_service, "render_figure", lambda token, index: b"\x89PNG fake"
    )
    response = client.get("/api/pdf_figure/abc123/0")
    assert response.status_code == 200
    assert response.mimetype == "image/png"
    assert response.data == b"\x89PNG fake"

    def unknown(token, index):
        raise graph_routes.pdf_service.PdfError("unknown token")

    monkeypatch.setattr(graph_routes.pdf_service, "render_figure", unknown)
    assert client.get("/api/pdf_figure/nope/0").status_code == 404


def test_tldr_generates_once_then_serves_from_cache(client, monkeypatch):
    """The first toggle generates and caches; every later request — including
    after a reload — answers from the cache without touching the model. The
    permanent cache is the whole 'each paper bills at most once' contract."""
    calls = []

    def fake_summarize(title, abstract):
        calls.append((title, abstract))
        return "Introduces DQN, which learns Atari from pixels."

    monkeypatch.setattr(graph_routes.summarizer, "summarize", fake_summarize)
    body = {"id": "W123", "title": "Playing Atari", "abstract": "We present DQN."}
    first = client.post("/api/paper/tldr", json=body)
    second = client.post("/api/paper/tldr", json=body)
    assert first.status_code == second.status_code == 200
    assert first.json == second.json == {"tldr": "Introduces DQN, which learns Atari from pixels."}
    assert len(calls) == 1  # the second answer came from the cache


def test_tldr_validates_its_input(client):
    assert client.post("/api/paper/tldr", json={"abstract": "text"}).status_code == 400
    response = client.post("/api/paper/tldr", json={"id": "W123", "abstract": "  "})
    assert response.status_code == 400
    assert "no abstract" in response.json["error"]


def test_tldr_generation_failure_maps_to_502(client, monkeypatch):
    monkeypatch.setattr(graph_routes.summarizer, "summarize", lambda title, abstract: None)
    response = client.post(
        "/api/paper/tldr", json={"id": "W123", "title": "T", "abstract": "A."}
    )
    assert response.status_code == 502
    assert "Anthropic" in response.json["error"]


def test_paper_backfills_a_generated_tldr_but_never_overwrites_a_native_one(
    client, monkeypatch
):
    """Hydration reads the TL;DR cache (a generated summary rides along free on
    later opens) but only fills a HOLE — a provider's own TL;DR wins, and
    hydration never generates (that would bill on every open)."""
    from atlas.storage import cache

    cache.set("tldr:v1:W123", "Cached summary.")
    monkeypatch.setattr(
        graph_routes.openalex,
        "get_paper",
        lambda ref: {"id": "W123", "title": "From OpenAlex", "tldr": None},
    )
    response = client.get("/api/paper/W123?provider=openalex")
    assert response.json["tldr"] == "Cached summary."

    cache.set("tldr:v1:s2id01", "Must not appear.")
    monkeypatch.setattr(
        graph_routes.semantic_scholar,
        "get_paper",
        lambda ref: {"id": "s2id01", "title": "From S2", "tldr": "S2's own TLDR."},
    )
    response = client.get("/api/paper/1312.5602")
    assert response.json["tldr"] == "S2's own TLDR."


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


def _shape_for(client, monkeypatch, query: str):
    """Build the graph behind ``query`` and hand back the shape the route parsed."""
    seen = {}

    def fake_build(seed, provider="s2", refresh=False, shape=None):
        seen["shape"] = shape
        return make_graph()

    monkeypatch.setattr(graph_routes.graph_service, "build_graph", fake_build)
    client.get(f"/api/graph?seed=1312.5602&{query}")
    return seen["shape"]


def test_shape_defaults_to_adaptive(client, monkeypatch):
    """No shape args at all — the app sizes itself, as it always did."""
    assert _shape_for(client, monkeypatch, "").adaptive is True


def test_adaptive_off_carries_the_users_band_shape(client, monkeypatch):
    shape = _shape_for(
        client, monkeypatch, "adaptive=0&cluster_start=2015&bands=8&per_band=25"
    )
    assert shape.adaptive is False
    assert shape.cluster_start == 2015
    assert shape.number_of_bands == 8
    assert shape.nodes_per_band == 25


def test_band_args_are_ignored_while_adaptive_is_on(client, monkeypatch):
    """Adaptive wins outright — a stale band arg must not shape an adaptive build."""
    shape = _shape_for(client, monkeypatch, "cluster_start=2015&bands=8&per_band=25")
    assert shape.adaptive is True
    assert shape.cache_suffix() == ""


def test_garbage_shape_args_degrade_rather_than_error(client, monkeypatch):
    """A forged query string costs a differently-sized graph, never a failed build."""
    shape = _shape_for(
        client, monkeypatch, "adaptive=no&cluster_start=abc&bands=xyz&per_band="
    )
    assert shape.adaptive is False
    assert shape.cluster_start is None  # unparseable -> fixed span
    assert shape.number_of_bands == graph_routes.caps.LATEST_NUMBER_OF_BANDS
    assert shape.nodes_per_band == graph_routes.caps.LATEST_NODES_PER_BAND


def test_out_of_range_shape_args_are_clamped(client, monkeypatch):
    shape = _shape_for(
        client, monkeypatch, "adaptive=0&cluster_start=1200&bands=9999&per_band=9999"
    )
    assert shape.cluster_start is None  # before any indexed paper -> dropped
    assert shape.number_of_bands == graph_routes._MAX_BANDS
    assert shape.nodes_per_band == graph_routes._MAX_PER_BAND  # OpenAlex's page cap


def test_stream_parses_the_shape_in_the_request_context(client, monkeypatch):
    """The worker thread outlives the request, so the route must parse it first."""
    seen = {}

    def fake_build(seed, provider="s2", refresh=False, shape=None, on_progress=None):
        seen["shape"] = shape
        return make_graph()

    monkeypatch.setattr(graph_routes.graph_service, "build_graph", fake_build)
    frames(client.get("/api/graph/stream?seed=1312.5602&adaptive=0&per_band=30"))
    assert seen["shape"].adaptive is False
    assert seen["shape"].nodes_per_band == 30
