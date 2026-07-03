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

from .. import arxiv_client, figures
from .. import graph as graph_service
from .. import semantic_scholar

bp = Blueprint("graph", __name__)


def _normalize_arxiv_id(raw: str) -> str:
    """Pull a bare arXiv id out of a pasted id / abs-or-pdf URL, version stripped.

    Reuses the id/URL pattern from arxiv_client so "https://arxiv.org/abs/1706.03762v5"
    and "1706.03762" both resolve to "1706.03762".
    """
    match = arxiv_client._ID_RE.search(raw or "")
    if match:
        return match.group(1).split("v")[0]
    return (raw or "").strip()


@bp.get("/api/graph")
def api_graph() -> Response:
    """The neighborhood graph for a seed paper (references + citations + similar).

    `seed` is an arXiv id or a pasted abs/pdf URL. `refresh=1` bypasses the cache.
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
def api_paper(arxiv_id: str) -> Response:
    """Full details (abstract, tldr, authors) for one paper — used to hydrate a
    node's detail panel on click."""
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
    """A paper's figures + captions (from ar5iv) for the detail panel.

    Returns {available, figures: [{image, caption}]}. Image URLs are rewritten to
    the same-origin proxy below so the browser never hotlinks ar5iv directly.
    ar5iv gaps (no LaTeX render) come back as available:false — not an error."""
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
def figure_proxy() -> Response:
    """Stream an ar5iv image through our origin (dodges hotlink/CORS).

    Locked to the ar5iv host so this can't be used as an open proxy (SSRF)."""
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
