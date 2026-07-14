"""Graph & paper routes: the neighborhood graph for a seed, single-paper
detail hydration, and a paper's figures (proxied from ar5iv).

GET /api/graph?seed=&refresh=      -> neighborhood graph for a seed paper
GET /api/graph/stream?seed=&refresh= -> same, as SSE with coarse build progress
GET /api/paper/<arxiv_id>          -> full details for one paper (panel hydrate)
GET /api/paper/<arxiv_id>/figures  -> the paper's figures + captions (ar5iv)
GET /api/paper/<arxiv_id>/code     -> code & artifact links (Hugging Face Papers)
GET /api/paper/<arxiv_id>/categories -> the paper's own arXiv category tags
GET /api/figure_proxy?src=         -> same-origin proxy for an ar5iv image

Two failure philosophies live here, on purpose: the *load-bearing* endpoints
(graph, paper) map failures to real HTTP errors (400/404/502), while the
panel *niceties* (figures, code) degrade to ``available: false`` — a missing
figure strip must never 500 the whole detail panel.
"""

from __future__ import annotations

import logging
import queue
import threading
import urllib.parse
from typing import Iterator

from flask import Blueprint, Response, current_app, jsonify, request
from flask.typing import ResponseReturnValue

from ..integrations import arxiv, huggingface, openalex, semantic_scholar
from ..services import graph as graph_service
from ..services.graph import Provider
from .sse import sse, sse_response

bp = Blueprint("graph", __name__)

# The stream generator runs after the request/app context is gone, so it (and
# its worker thread) must use a module logger, never ``current_app`` — see
# routes/sse.py.
log = logging.getLogger(__name__)

# A graph build now talks to exactly one academic-data backend; either provider's
# client can fail. Both surface to the client as a 502.
_BUILD_ERRORS = (semantic_scholar.S2Error, openalex.OpenAlexError)


def _requested_provider() -> Provider:
    """The academic-data backend to build from, parsed from the request.

    Reads the ``provider`` query arg (the header dropdown's choice) and validates
    it through the shared ``graph_service.resolve_provider`` — a stale/forged
    value degrades to ``config.graph.default_provider`` rather than erroring.

    Returns:
        ``"s2"`` or ``"openalex"``.
    """
    return graph_service.resolve_provider(request.args.get("provider"))


def _provider_name(provider: Provider) -> str:
    """Human-readable provider name for user-facing error messages."""
    return "OpenAlex" if provider == "openalex" else "Semantic Scholar"


def normalize_arxiv_id(raw: str) -> str:
    """Pull a bare arXiv id out of a pasted id / abs-or-pdf URL.

    Args:
        raw: Whatever the client sent as a seed/paper reference.

    Returns:
        The bare, version-stripped id (via ``arxiv.extract_id``); falls back
        to the stripped input when it doesn't look like an arXiv id at all
        (it may be a raw S2 paperId).
    """
    return arxiv.extract_id(raw) or (raw or "").strip()


@bp.get("/api/graph")
def api_graph() -> ResponseReturnValue:
    """Build the neighborhood graph for a seed paper.

    Query args:
        seed: An arXiv id, a pasted abs/pdf URL, or a raw provider node id.
        provider: ``s2`` or ``openalex`` — which backend to build from (defaults
            to ``config.graph.default_provider``).
        refresh: Truthy (``1``/``true``/``yes``) bypasses the cached snapshot.

    Returns:
        JSON ``{seed, nodes, edges, counts}`` on success; ``{error}`` with
        HTTP 400 for a missing seed, 404 when the provider has no such paper, or
        502 when the provider is unavailable.
    """
    seed = normalize_arxiv_id(request.args.get("seed", ""))
    if not seed:
        return jsonify({"error": "missing 'seed' arXiv id"}), 400
    provider = _requested_provider()
    refresh = request.args.get("refresh", "").lower() in ("1", "true", "yes")
    try:
        result = graph_service.build_graph(seed, provider=provider, refresh=refresh)
    except _BUILD_ERRORS as exc:
        current_app.logger.warning("graph build failed for %s (%s): %s", seed, provider, exc)
        return jsonify({"error": f"{_provider_name(provider)} is unavailable — try again."}), 502
    if not result:
        return jsonify({"error": f"No paper found on {_provider_name(provider)} for {seed}."}), 404
    return jsonify(result.model_dump())


def _build_stream(seed: str, provider: Provider, refresh: bool) -> Iterator[str]:
    """Build a seed's graph in a worker thread, streaming progress as SSE.

    ``build_graph`` is synchronous and reports coarse stages through a
    callback; a queue bridges those callbacks into this generator (the same
    shape as source ingestion in ``routes/sources.py``). The worker owns all
    error mapping so a failure always ends the stream with an ``error`` frame
    rather than a dropped connection.

    A cache hit fires no ``progress`` frames — ``build_graph`` returns before
    the first stage — so the stream jumps straight to ``done`` and the overlay
    barely flickers.

    Args:
        seed: The normalized seed reference (arXiv id / provider node id).
        provider: Which backend to build from (``s2`` / ``openalex``).
        refresh: Bypass the cached snapshot and rebuild from the provider.

    Yields:
        ``progress`` frames (``{done, total, label}``), then exactly one
        ``done`` (the serialized graph) or ``error`` (``{message}``) frame.
    """
    frames: queue.Queue[tuple[str, object]] = queue.Queue()
    provider_name = _provider_name(provider)

    def worker() -> None:
        try:
            result = graph_service.build_graph(
                seed,
                provider=provider,
                refresh=refresh,
                on_progress=lambda done, total, label: frames.put(
                    ("progress", {"done": done, "total": total, "label": label})
                ),
            )
            if not result:
                frames.put(
                    ("error", {"message": f"No paper found on {provider_name} for {seed}."})
                )
            else:
                frames.put(("done", result.model_dump()))
        except _BUILD_ERRORS as exc:
            log.warning("graph build failed for %s (%s): %s", seed, provider, exc)
            frames.put(("error", {"message": f"{provider_name} is unavailable — try again."}))
        except Exception:
            log.exception("graph build failed for %s", seed)
            frames.put(("error", {"message": "Could not build that graph."}))

    threading.Thread(target=worker, daemon=True).start()
    while True:
        kind, data = frames.get()
        yield sse(kind, data)
        if kind in ("done", "error"):
            return


@bp.get("/api/graph/stream")
def api_graph_stream() -> ResponseReturnValue:
    """Build a seed's neighborhood graph, streaming coarse build progress.

    The determinate-progress twin of ``/api/graph``: identical result, but
    delivered as an SSE stream so the frontend's "Building graph…" overlay can
    show a real percent bar (stage / total) instead of a bare spinner.

    Query args:
        seed: An arXiv id, a pasted abs/pdf URL, or a raw provider node id.
        provider: ``s2`` or ``openalex`` — which backend to build from (defaults
            to ``config.graph.default_provider``).
        refresh: Truthy (``1``/``true``/``yes``) bypasses the cached snapshot.

    Returns:
        HTTP 400 (JSON) for a missing seed; otherwise an SSE stream of
        ``progress`` frames then ``done`` (the graph) or ``error``. Build
        failures surface as ``error`` frames, not HTTP status — the connection
        is already streaming by then.
    """
    seed = normalize_arxiv_id(request.args.get("seed", ""))
    if not seed:
        return jsonify({"error": "missing 'seed' arXiv id"}), 400
    provider = _requested_provider()
    refresh = request.args.get("refresh", "").lower() in ("1", "true", "yes")
    return sse_response(_build_stream(seed, provider, refresh))


@bp.get("/api/paper/<path:paper_ref>")
def api_paper(paper_ref: str) -> ResponseReturnValue:
    """Fetch full details for one paper.

    Used to hydrate a node's detail panel on click — graph neighbors arrive
    without abstract/tldr.

    Args:
        paper_ref: The paper's arXiv id, a pasted abs/pdf URL, or a raw S2
            paperId (papers without an arXiv id hydrate by paperId).

    Returns:
        The JSON node details on success; ``{error}`` with HTTP 404 when S2
        has no such paper, or 502 when Semantic Scholar is unavailable.
    """
    ref = normalize_arxiv_id(paper_ref)
    # Same discrimination as build_graph's seed lookup: only an actual arXiv
    # id gets the ARXIV: prefix — a raw S2 paperId passes through untouched.
    # (The old route prefixed unconditionally, which broke hydration for
    # papers that exist on S2 but not on arXiv.)
    lookup = f"ARXIV:{ref}" if arxiv.looks_arxiv(ref) else ref
    try:
        node = semantic_scholar.get_paper(lookup)
    except semantic_scholar.S2Error as exc:
        current_app.logger.warning("paper fetch failed for %s: %s", ref, exc)
        return jsonify({"error": "Semantic Scholar is unavailable — try again."}), 502
    if not node:
        return jsonify({"error": f"No paper found for {ref}."}), 404
    return jsonify(node)


@bp.get("/api/paper/<path:paper_ref>/figures")
def api_figures(paper_ref: str) -> Response:
    """Fetch a paper's figures + captions (from ar5iv) for the detail panel.

    Image URLs are rewritten to the same-origin proxy below so the browser
    never hotlinks ar5iv directly.

    Args:
        paper_ref: The paper's arXiv id (path-encoded).

    Returns:
        JSON ``{available, figures: [{image, caption}]}``. ar5iv gaps (no
        LaTeX render) come back as ``available: false`` — not an error — and
        an ar5iv outage degrades the same way rather than 500-ing the panel.
    """
    ref = normalize_arxiv_id(paper_ref)
    try:
        result = arxiv.get_figures(ref)
    except Exception:  # ar5iv down/slow — degrade gracefully, don't 500 the panel
        current_app.logger.warning("figure fetch failed for %s", ref, exc_info=True)
        return jsonify({"available": False, "figures": []})
    for figure in result.get("figures", []):
        figure["image"] = "/api/figure_proxy?src=" + urllib.parse.quote(
            figure["image"], safe=""
        )
    return jsonify(result)


@bp.get("/api/paper/<path:paper_ref>/code")
def api_code(paper_ref: str) -> Response:
    """Fetch a paper's code & artifact links (Hugging Face Papers).

    Args:
        paper_ref: The paper's arXiv id (path-encoded).

    Returns:
        JSON ``{available, paper_url, upvotes, github, models, datasets,
        spaces, totals}``. Papers HF has never indexed come back as
        ``available: false`` — not an error — and an HF outage degrades the
        same way rather than 500-ing the panel.
    """
    ref = normalize_arxiv_id(paper_ref)
    try:
        result = huggingface.get_code_links(ref)
    except Exception:  # HF down/slow — degrade gracefully, don't 500 the panel
        current_app.logger.warning("code-links fetch failed for %s", ref, exc_info=True)
        result = huggingface.empty_result()
    return jsonify(result)


@bp.get("/api/paper/<path:paper_ref>/categories")
def api_categories(paper_ref: str) -> Response:
    """Fetch a paper's own arXiv category tags for the detail panel.

    Args:
        paper_ref: The paper's arXiv id (path-encoded). Non-arXiv papers (a
            raw S2 paperId) have none — arXiv's own metadata is the only
            source for this field.

    Returns:
        JSON ``{available, categories: [{code, name}]}``. A bad/withdrawn id
        comes back as ``available: false`` — not an error — and an arXiv
        outage degrades the same way rather than 500-ing the panel.
    """
    ref = normalize_arxiv_id(paper_ref)
    try:
        result = arxiv.get_categories(ref)
    except Exception:  # arXiv down/slow — degrade gracefully, don't 500 the panel
        current_app.logger.warning("category fetch failed for %s", ref, exc_info=True)
        return jsonify({"available": False, "categories": []})
    return jsonify(result)


@bp.get("/api/figure_proxy")
def figure_proxy() -> ResponseReturnValue:
    """Stream an ar5iv image through our origin (dodges hotlink/CORS).

    Locked to the ar5iv host so this can't be used as an open proxy (SSRF).

    Query args:
        src: The absolute ar5iv image URL to fetch.

    Returns:
        The image bytes with a day-long cache header on success; ``{error}``
        with HTTP 400 for a non-ar5iv URL, or an empty 502 when the upstream
        fetch fails.
    """
    src = request.args.get("src", "")
    if not arxiv.is_ar5iv_url(src):
        return jsonify({"error": "src must be an ar5iv image URL"}), 400
    try:
        data, content_type = arxiv.fetch_image(src)
    except Exception:
        current_app.logger.warning("figure proxy failed for %s", src, exc_info=True)
        return Response(status=502)
    return Response(
        data,
        mimetype=content_type,
        headers={"Cache-Control": "public, max-age=86400"},
    )
