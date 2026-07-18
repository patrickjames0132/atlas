"""Seed-search routes: a live relevance search across the selected provider (with
optional date/field filters), an instant search over the local snapshot
cache, and the field vocabularies that power the search filter picker.

GET /api/search?q=&provider=&limit=&year_from=&year_to=&fields=&analyst=
                                 -> live seed search (s2 / openalex)
GET /api/local_search?q=&provider=&limit=&year_from=&year_to=
                                 -> instant seed search over the local cache
GET /api/taxonomy/<provider>     -> a provider's field vocabulary (s2 / openalex)
"""

from __future__ import annotations

from flask import Blueprint, Response, current_app, jsonify, request
from flask.typing import ResponseReturnValue

from ..integrations import openalex, semantic_scholar
from ..services import search as search_service
from ..services.graph import resolve_provider

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


def _opt_fields(provider: str) -> list[str] | None:
    """Parse and validate the optional ``fields`` query arg for a provider.

    The field-filter values are provider-specific: S2 fields are their own
    names, OpenAlex fields are numeric ids (``topics.field.id``). Each is
    validated against that provider's vocabulary; unknown values are silently
    dropped (they can only come from a stale/forged client — e.g. S2 field names
    left over after switching to OpenAlex).

    Args:
        provider: ``s2`` or ``openalex`` — which vocabulary to validate against.

    Returns:
        The surviving field values, or None when none survive.
    """
    raw = (request.args.get("fields") or "").strip()
    if not raw:
        return None
    if provider == "openalex":
        valid: frozenset[str] = openalex.vocab.valid_field_ids()
    else:
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
        provider: ``s2`` or ``openalex`` — which backend to search (matches the
            graph provider; defaults to ``config.graph.default_provider``).
        limit: Maximum papers (default 25, clamped to 1–100).
        year_from: Earliest publication year (inclusive; optional).
        year_to: Latest publication year (inclusive; optional).
        fields: Comma-separated S2 fields of study (optional; a paper matches
            when it carries any of them). Applied only on the S2 path.
        analyst: ``0``/``false``/``no`` skips the query-analyst agent — the
            lexical search runs on the words as typed, with no LLM call.
            Anything else (including absent) keeps the analyst on.

    Returns:
        JSON ``{q, count, papers}`` on success (papers are node dicts — the
        same shape as graph nodes); ``{error}`` with HTTP 502 when the provider
        is unavailable. Saves nothing.
    """
    query = (request.args.get("q") or "").strip()
    provider = resolve_provider(request.args.get("provider"))
    try:
        limit = max(1, min(int(request.args.get("limit", "25")), 100))
    except ValueError:
        limit = 25
    if not query:
        return jsonify({"q": query, "count": 0, "papers": []})
    analyst = (request.args.get("analyst") or "").strip().lower() not in ("0", "false", "no")
    try:
        papers = search_service.live_search(
            query,
            limit=limit,
            year_from=_opt_year("year_from"),
            year_to=_opt_year("year_to"),
            fields_of_study=_opt_fields(provider),
            provider=provider,
            analyst=analyst,
        )
    except (semantic_scholar.S2Error, openalex.OpenAlexError) as exc:
        name = "OpenAlex" if provider == "openalex" else "Semantic Scholar"
        current_app.logger.warning("live search failed for %r (%s): %s", query, provider, exc)
        return jsonify({"error": f"{name} is unavailable — try again."}), 502
    return jsonify({"q": query, "count": len(papers), "papers": papers})


@bp.get("/api/local_search")
def local_search_route() -> Response:
    """Instant seed search over papers already in the local snapshot cache.

    Purely local (no S2 calls) — the cache-first results shown while the
    live search is still in flight, and the only results available when
    Semantic Scholar is rate-limiting us.

    Query args:
        q: The search text. Blank returns an empty result.
        limit: Maximum hits (default 10, clamped to 1–50).
        provider: ``s2`` or ``openalex`` — only that backend's cached snapshots
            are searched (defaults to ``config.graph.default_provider``), so a
            hit's "instant" badge reflects the provider actually selected.
        year_from: Earliest publication year (inclusive; optional).
        year_to: Latest publication year (inclusive; optional). No field
            filter — cached nodes are matched purely on text.

    Returns:
        JSON ``{q, count, papers}``. Never errors — a failure is logged and
        degrades to zero local hits, since this must not block the live
        search running alongside it.
    """
    query = (request.args.get("q") or "").strip()
    try:
        limit = max(1, min(int(request.args.get("limit", "10")), 50))
    except ValueError:
        limit = 10
    if not query:
        return jsonify({"q": query, "count": 0, "papers": []})
    try:
        papers = search_service.local_search(
            query,
            limit=limit,
            year_from=_opt_year("year_from"),
            year_to=_opt_year("year_to"),
            provider=resolve_provider(request.args.get("provider")),
        )
    except Exception:
        current_app.logger.exception("local search failed for %r", query)
        papers = []
    return jsonify({"q": query, "count": len(papers), "papers": papers})


@bp.get("/api/taxonomy/<provider>")
def api_taxonomy(provider: str) -> ResponseReturnValue:
    """A search provider's field vocabulary, for the seed-search filter picker.

    Both graph providers return the **same** shape — ``{"fields": [{id, name}]}``
    — so the frontend picker is provider-agnostic: it shows ``name`` and sends
    ``id`` as the filter value. For S2 the id *is* the field name (S2 filters on
    the name itself); for OpenAlex the id is the numeric field id
    (``topics.field.id``) and the name its label.

    Args:
        provider: ``s2`` (the ~20 fields of study) or ``openalex`` (the 26
            top-level fields).

    Returns:
        ``{"fields": [{"id": ..., "name": ...}]}``; ``{error}`` with HTTP 404
        for an unknown provider.
    """
    if provider == "s2":
        return jsonify(
            {"fields": [{"id": name, "name": name} for name in semantic_scholar.vocab.fields()]}
        )
    if provider == "openalex":
        return jsonify({"fields": openalex.vocab.fields()})
    return jsonify({"error": f"unknown taxonomy provider {provider!r}"}), 404
