"""Seed-search routes: a live relevance search across Semantic Scholar (with
optional date/field filters), an instant search over the local snapshot
cache, and the subject vocabularies that power the search filter pickers.

GET /api/search?q=&limit=&year_from=&year_to=&fields=
                                 -> live seed search across Semantic Scholar
GET /api/local_search?q=&limit=&year_from=&year_to=
                                 -> instant seed search over the local cache
GET /api/taxonomy/<provider>     -> a provider's subject vocabulary
"""

from __future__ import annotations

from flask import Blueprint, Response, current_app, jsonify, request
from flask.typing import ResponseReturnValue

from ..integrations import arxiv, semantic_scholar
from ..services import search as search_service

bp = Blueprint("search", __name__)


def _opt_year(name: str) -> int | None:
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


def _opt_fields() -> list[str] | None:
    """Parse and validate the optional ``fields`` query arg.

    Returns:
        The comma-separated S2 fields of study that exist in the S2
        vocabulary (unknown values are silently dropped — they can only come
        from a stale/forged client), or None when none survive.
    """
    raw = (request.args.get("fields") or "").strip()
    if not raw:
        return None
    valid = semantic_scholar.vocab.valid_fields()
    fields = [field.strip() for field in raw.split(",") if field.strip() in valid]
    return fields or None


@bp.get("/api/search")
def api_search() -> ResponseReturnValue:
    """Live relevance search across Semantic Scholar to find a seed paper.

    Query args:
        q: Keywords, a title, an author, or an arXiv id/URL (a pasted id
            resolves to exactly that paper; filters don't apply to it).
            Blank returns an empty result rather than an error.
        limit: Maximum papers (default 25, clamped to 1–100).
        year_from: Earliest publication year (inclusive; optional).
        year_to: Latest publication year (inclusive; optional).
        fields: Comma-separated S2 fields of study (optional; a paper
            matches when it carries any of them).

    Returns:
        JSON ``{q, count, papers}`` on success (papers are S2 node dicts —
        the same shape as graph nodes); ``{error}`` with HTTP 502 when
        Semantic Scholar is unavailable. Saves nothing.
    """
    q = (request.args.get("q") or "").strip()
    try:
        limit = max(1, min(int(request.args.get("limit", "25")), 100))
    except ValueError:
        limit = 25
    if not q:
        return jsonify({"q": q, "count": 0, "papers": []})
    try:
        papers = search_service.live_search(
            q,
            limit=limit,
            year_from=_opt_year("year_from"),
            year_to=_opt_year("year_to"),
            fields_of_study=_opt_fields(),
        )
    except semantic_scholar.S2Error as exc:
        current_app.logger.warning("live search failed for %r: %s", q, exc)
        return jsonify({"error": "Semantic Scholar is unavailable — try again."}), 502
    return jsonify({"q": q, "count": len(papers), "papers": papers})


@bp.get("/api/local_search")
def local_search_route() -> Response:
    """Instant seed search over papers already in the local snapshot cache.

    Purely local (no S2 calls) — the cache-first results shown while the
    live search is still in flight, and the only results available when
    Semantic Scholar is rate-limiting us.

    Query args:
        q: The search text. Blank returns an empty result.
        limit: Maximum hits (default 10, clamped to 1–50).
        year_from: Earliest publication year (inclusive; optional).
        year_to: Latest publication year (inclusive; optional). No field
            filter — cached nodes are matched purely on text.

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
            q,
            limit=limit,
            year_from=_opt_year("year_from"),
            year_to=_opt_year("year_to"),
        )
    except Exception:
        current_app.logger.exception("local search failed for %r", q)
        papers = []
    return jsonify({"q": q, "count": len(papers), "papers": papers})


@bp.get("/api/taxonomy/<provider>")
def api_taxonomy(provider: str) -> ResponseReturnValue:
    """A provider's subject vocabulary, for the search filter pickers.

    Each provider returns its natural shape rather than a forced common
    envelope — the pickers they feed are different controls.

    Args:
        provider: ``s2`` (the ~20 fields of study filtering live search) or
            ``arxiv`` (the ~155 arXiv categories, grouped by area).

    Returns:
        ``{"fields": [...]}`` for s2; ``{"groups": [{group, categories}]}``
        for arxiv; ``{error}`` with HTTP 404 for an unknown provider.
    """
    if provider == "s2":
        return jsonify({"fields": semantic_scholar.vocab.fields()})
    if provider == "arxiv":
        return jsonify({"groups": arxiv.vocab.groups()})
    return jsonify({"error": f"unknown taxonomy provider {provider!r}"}), 404
