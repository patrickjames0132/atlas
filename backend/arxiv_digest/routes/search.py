"""Seed-search routes: a live relevance search across arXiv (with optional
date/category filters), an instant search over the local snapshot cache, and
the arXiv category taxonomy that powers the category picker.

GET /api/arxiv_search?q=&limit=&year_from=&year_to=&categories=
                                 -> live seed search across arXiv
GET /api/local_search?q=&limit=&year_from=&year_to=
                                 -> instant seed search over the local cache
GET /api/taxonomy                -> the arXiv category taxonomy (for the picker)
"""

from __future__ import annotations

from typing import Optional

from flask import Blueprint, Response, current_app, jsonify, request
from flask.typing import ResponseReturnValue

from ..integrations import taxonomy
from ..services import search as search_service

bp = Blueprint("search", __name__)


def _opt_year(name: str) -> Optional[int]:
    """Parse an optional year query arg.

    Args:
        name: The query-arg name (``year_from`` / ``year_to``).

    Returns:
        The year as an int, or None when absent/blank/non-numeric — filters
        are strictly optional, so garbage degrades to "no filter" rather
        than erroring.
    """
    raw = (request.args.get(name) or "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _opt_categories() -> Optional[list[str]]:
    """Parse and validate the optional ``categories`` query arg.

    Returns:
        The comma-separated category codes that exist in the arXiv taxonomy
        (unknown codes are silently dropped — they can only come from a
        stale/forged client), or None when none survive.
    """
    raw = (request.args.get("categories") or "").strip()
    if not raw:
        return None
    valid = taxonomy.valid_codes()
    cats = [c.strip() for c in raw.split(",") if c.strip() in valid]
    return cats or None


@bp.get("/api/arxiv_search")
def arxiv_search_route() -> ResponseReturnValue:
    """Live relevance search across all of arXiv to find a seed paper.

    Query args:
        q: Keywords, a title, an author, or an arXiv id/URL. Blank returns an
            empty result rather than an error.
        limit: Maximum papers (default 25, clamped to 1–100).
        year_from: Earliest submission year (inclusive; optional).
        year_to: Latest submission year (inclusive; optional).
        categories: Comma-separated arXiv category codes (optional; a paper
            matches when it carries any of them). Filters never apply to an
            explicit id/URL lookup.

    Returns:
        JSON ``{q, count, papers}`` on success (each paper carries its
        ``published`` date); ``{ok: False, error}`` with HTTP 502 when the
        arXiv API fails. Saves nothing.
    """
    q = (request.args.get("q") or "").strip()
    try:
        limit = max(1, min(int(request.args.get("limit", "25")), 100))
    except ValueError:
        limit = 25
    if not q:
        return jsonify({"q": q, "count": 0, "papers": []})
    try:
        papers = search_service.arxiv_search(
            q, limit=limit,
            year_from=_opt_year("year_from"), year_to=_opt_year("year_to"),
            categories=_opt_categories(),
        )
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
        year_from: Earliest publication year (inclusive; optional).
        year_to: Latest publication year (inclusive; optional). No category
            filter — S2 nodes don't carry arXiv categories.

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
        papers = search_service.local_search(
            q, limit=limit,
            year_from=_opt_year("year_from"), year_to=_opt_year("year_to"),
        )
    except Exception:
        current_app.logger.exception("local search failed for %r", q)
        papers = []
    return jsonify({"q": q, "count": len(papers), "papers": papers})


@bp.get("/api/taxonomy")
def api_taxonomy() -> Response:
    """The arXiv category taxonomy, for the search filter's category picker.

    Returns:
        JSON ``{groups: [{group, categories: [{code, name}]}]}`` — the full
        taxonomy grouped by top-level area (8 areas, ~155 categories).
    """
    return jsonify({"groups": taxonomy.groups()})
