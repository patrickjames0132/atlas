"""Graph & paper routes: the neighborhood graph for a seed, single-paper
detail hydration, and a paper's figures (proxied from ar5iv).

GET /api/graph?seed=&refresh=      -> neighborhood graph for a seed paper
GET /api/paper/<arxiv_id>          -> full details for one paper (panel hydrate)
GET /api/paper/<arxiv_id>/figures  -> the paper's figures + captions (ar5iv)
GET /api/paper/<arxiv_id>/code     -> code & artifact links (Hugging Face Papers)
GET /api/figure_proxy?src=         -> same-origin proxy for an ar5iv image

Two failure philosophies live here, on purpose: the *load-bearing* endpoints
(graph, paper) map failures to real HTTP errors (400/404/502), while the
panel *niceties* (figures, code) degrade to ``available: false`` — a missing
figure strip must never 500 the whole detail panel.
"""

from __future__ import annotations

import urllib.parse

from flask import Blueprint, Response, current_app, jsonify, request
from flask.typing import ResponseReturnValue

from ..integrations import arxiv, huggingface, semantic_scholar
from ..services import graph as graph_service

bp = Blueprint("graph", __name__)


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
        seed: An arXiv id, a pasted abs/pdf URL, or a raw S2 paperId.
        refresh: Truthy (``1``/``true``/``yes``) bypasses the cached snapshot.

    Returns:
        JSON ``{seed, nodes, edges, counts}`` on success; ``{error}`` with
        HTTP 400 for a missing seed, 404 when S2 has no such paper, or 502
        when Semantic Scholar is unavailable.
    """
    seed = normalize_arxiv_id(request.args.get("seed", ""))
    if not seed:
        return jsonify({"error": "missing 'seed' arXiv id"}), 400
    refresh = request.args.get("refresh", "").lower() in ("1", "true", "yes")
    try:
        result = graph_service.build_graph(seed, refresh=refresh)
    except semantic_scholar.S2Error as exc:
        current_app.logger.warning("graph build failed for %s: %s", seed, exc)
        return jsonify({"error": "Semantic Scholar is unavailable — try again."}), 502
    if not result:
        return jsonify({"error": f"No paper found on Semantic Scholar for {seed}."}), 404
    return jsonify(result.model_dump())


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
