"""Graph & paper routes: the neighborhood graph for a seed, single-paper detail
hydration, and a paper's figures (proxied from ar5iv).

GET /api/graph?seed=&refresh=      -> neighborhood graph for a seed paper
GET /api/paper/<arxiv_id>          -> full details for one paper (panel hydrate)
GET /api/paper/<arxiv_id>/figures  -> the paper's figures + captions (ar5iv)
GET /api/figure_proxy?src=         -> same-origin proxy for an ar5iv image
"""

from __future__ import annotations

import urllib.parse

from flask import Blueprint, Response, current_app, jsonify, request
from flask.typing import ResponseReturnValue

from ..integrations import arxiv_client, figures, semantic_scholar
from ..services import graph as graph_service

bp = Blueprint("graph", __name__)


def _normalize_arxiv_id(raw: str) -> str:
    """Pull a bare arXiv id out of a pasted id / abs-or-pdf URL.

    Reuses the id/URL pattern from arxiv_client so both
    ``https://arxiv.org/abs/1706.03762v5`` and ``1706.03762`` resolve to
    ``1706.03762``.

    Args:
        raw: Whatever the client sent as a seed/paper reference.

    Returns:
        The bare id with any version suffix stripped; falls back to the
        stripped input when it doesn't look like an arXiv id at all (it may
        be a raw S2 paperId).
    """
    match = arxiv_client._ID_RE.search(raw or "")
    if match:
        return match.group(1).split("v")[0]
    return (raw or "").strip()


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
    seed = _normalize_arxiv_id(request.args.get("seed", ""))
    if not seed:
        return jsonify({"error": "missing 'seed' arXiv id"}), 400
    refresh = request.args.get("refresh", "").lower() in ("1", "true", "yes")
    try:
        result = graph_service.build_graph(seed, refresh=refresh)
    except semantic_scholar.S2Error as e:
        current_app.logger.warning("graph build failed for %s: %s", seed, e)
        return jsonify({"error": "Semantic Scholar is unavailable — try again."}), 502
    if not result:
        return jsonify({"error": f"No paper found on Semantic Scholar for {seed}."}), 404
    return jsonify(result)


@bp.get("/api/paper/<path:arxiv_id>")
def api_paper(arxiv_id: str) -> ResponseReturnValue:
    """Fetch full details for one paper.

    Used to hydrate a node's detail panel on click — graph neighbors arrive
    without abstract/tldr.

    Args:
        arxiv_id: The paper's arXiv id or a pasted abs/pdf URL (path-encoded).

    Returns:
        The JSON node details on success; ``{error}`` with HTTP 404 when S2
        has no such paper, or 502 when Semantic Scholar is unavailable.
    """
    seed = _normalize_arxiv_id(arxiv_id)
    try:
        node = semantic_scholar.get_paper(f"ARXIV:{seed}")
    except semantic_scholar.S2Error as e:
        current_app.logger.warning("paper fetch failed for %s: %s", seed, e)
        return jsonify({"error": "Semantic Scholar is unavailable — try again."}), 502
    if not node:
        return jsonify({"error": f"No paper found for {seed}."}), 404
    return jsonify(node)


@bp.get("/api/paper/<path:arxiv_id>/figures")
def api_figures(arxiv_id: str) -> Response:
    """Fetch a paper's figures + captions (from ar5iv) for the detail panel.

    Image URLs are rewritten to the same-origin proxy below so the browser
    never hotlinks ar5iv directly.

    Args:
        arxiv_id: The paper's arXiv id (path-encoded).

    Returns:
        JSON ``{available, figures: [{image, caption}]}``. ar5iv gaps (no
        LaTeX render) come back as ``available: false`` — not an error — and
        an ar5iv outage degrades the same way rather than 500-ing the panel.
    """
    seed = _normalize_arxiv_id(arxiv_id)
    try:
        result = figures.get_figures(seed)
    except Exception:  # ar5iv down/slow — degrade gracefully, don't 500 the panel
        current_app.logger.warning("figure fetch failed for %s", seed, exc_info=True)
        return jsonify({"available": False, "figures": []})
    for fig in result.get("figures", []):
        fig["image"] = "/api/figure_proxy?src=" + urllib.parse.quote(fig["image"], safe="")
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
    if not figures.is_ar5iv_url(src):
        return jsonify({"error": "src must be an ar5iv image URL"}), 400
    try:
        data, content_type = figures.fetch_image(src)
    except Exception:
        current_app.logger.warning("figure proxy failed for %s", src, exc_info=True)
        return Response(status=502)
    return Response(
        data,
        mimetype=content_type,
        headers={"Cache-Control": "public, max-age=86400"},
    )
