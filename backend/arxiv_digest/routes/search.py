"""Seed-search routes: a live relevance search across arXiv, and an instant search
over the local snapshot cache.

GET /api/arxiv_search?q=&limit=  -> live seed search across arXiv
GET /api/local_search?q=&limit=  -> instant seed search over the local cache
"""

from __future__ import annotations

from flask import Blueprint, Response, current_app, jsonify, request

from ..services import search as search_service

bp = Blueprint("search", __name__)


@bp.get("/api/arxiv_search")
def arxiv_search_route() -> Response:
    """Live relevance search across all of arXiv to find a seed paper.

    Query args:
        q: Keywords, a title, an author, or an arXiv id/URL. Blank returns an
            empty result rather than an error.
        limit: Maximum papers (default 25, clamped to 1–100).

    Returns:
        JSON ``{q, count, papers}`` on success; ``{ok: False, error}`` with
        HTTP 502 when the arXiv API fails. Saves nothing.
    """
    q = (request.args.get("q") or "").strip()
    try:
        limit = max(1, min(int(request.args.get("limit", "25")), 100))
    except ValueError:
        limit = 25
    if not q:
        return jsonify({"q": q, "count": 0, "papers": []})
    try:
        papers = search_service.arxiv_search(q, limit=limit)
    except Exception as exc:
        current_app.logger.exception("arxiv search failed for %r", q)
        return jsonify({"ok": False, "error": str(exc)}), 502
    return jsonify({"q": q, "count": len(papers), "papers": papers})


@bp.get("/api/local_search")
def local_search_route() -> Response:
    """Instant seed search over papers already in the local snapshot cache.

    Purely local (no arXiv / S2 calls) — the cache-first results shown while
    the live arXiv search is still in flight, and the only results available
    when Semantic Scholar is rate-limiting us.

    Query args:
        q: The search text. Blank returns an empty result.
        limit: Maximum hits (default 10, clamped to 1–50).

    Returns:
        JSON ``{q, count, papers}``. Never errors — a failure is logged and
        degrades to zero local hits, since this must not block the live
        search running alongside it.
    """
    q = (request.args.get("q") or "").strip()
    try:
        limit = max(1, min(int(request.args.get("limit", "10")), 50))
    except ValueError:
        limit = 10
    if not q:
        return jsonify({"q": q, "count": 0, "papers": []})
    try:
        papers = search_service.local_search(q, limit=limit)
    except Exception:
        current_app.logger.exception("local search failed for %r", q)
        papers = []
    return jsonify({"q": q, "count": len(papers), "papers": papers})
