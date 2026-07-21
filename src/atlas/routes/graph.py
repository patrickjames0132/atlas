"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
Graph & paper routes: the neighborhood graph for a seed, single-paper
detail hydration, and a paper's figures (proxied from ar5iv).

GET /api/graph?seed=&refresh=      -> neighborhood graph for a seed paper
GET /api/graph/stream?seed=&refresh= -> same, as SSE with coarse build progress
GET /api/paper/<arxiv_id>          -> full details for one paper (panel hydrate)
POST /api/paper/tldr               -> generate (or recall) a paper's TL;DR
GET /api/paper/<ref>/figures       -> figures + captions (ar5iv, else mined OA PDF)
GET /api/paper/<arxiv_id>/code     -> code & artifact links (Hugging Face Papers)
GET /api/paper/<arxiv_id>/categories -> the paper's own arXiv category tags
GET /api/pdf_figure/<token>/<n>    -> one mined PDF float, rendered to PNG
GET /api/figure_proxy?src=         -> same-origin proxy for an ar5iv image

Two failure philosophies live here, on purpose: the *load-bearing* endpoints
(graph, paper) map failures to real HTTP errors (400/404/502), while the
panel *niceties* (figures, code) degrade to ``available: false`` — a missing
figure strip must never 500 the whole detail panel.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

import datetime
import logging
import queue
import threading
import urllib.parse
from typing import Iterator

from flask import Blueprint, Response, current_app, jsonify, request
from flask.typing import ResponseReturnValue

from ..agents import summarizer
from ..integrations import arxiv, caps, huggingface, openalex, semantic_scholar
from ..services import graph as graph_service
from ..services import pdf as pdf_service
from ..services.graph import Provider
from ..services.graph.shape import BuildShape
from ..storage import cache
from .sse import sse, sse_response

bp = Blueprint("graph", __name__)

# The stream generator runs after the request/app context is gone, so it (and
# its worker thread) must use a module logger, never ``current_app`` — see
# routes/sse.py.
log = logging.getLogger(__name__)

# A graph build now talks to exactly one academic-data backend; either provider's
# client can fail. Both surface to the client as a 502.
_BUILD_ERRORS = (semantic_scholar.S2Error, openalex.OpenAlexError)

#: Bounds for the user-supplied band shape. The year floor predates any paper
#: the providers index; the band ceiling keeps a hand-typed number from spawning
#: a hundred throttled per-year queries; the per-band ceiling is OpenAlex's page
#: cap, which neither provider can exceed in one query.
_MIN_BAND_YEAR = 1800
_MAX_BANDS = 50
_MAX_PER_BAND = 200


def _requested_provider() -> Provider:
    """The academic-data backend to build from, parsed from the request.

    Reads the ``provider`` query arg (the header dropdown's choice) and validates
    it through the shared ``graph_service.resolve_provider`` — a stale/forged
    value degrades to ``config.providers.default_provider`` rather than erroring.

    Returns:
        ``"s2"`` or ``"openalex"``.
    """
    return graph_service.resolve_provider(request.args.get("provider"))


def _bounded_int(arg: str, fallback: int, low: int, high: int) -> int:
    """One clamped integer query arg, for the build-shape parser.

    Args:
        arg: The query-arg name.
        fallback: The value to keep when the arg is absent or unparseable.
        low: Smallest accepted value.
        high: Largest accepted value.

    Returns:
        The parsed value clamped into ``[low, high]``, or ``fallback``.
    """
    raw = request.args.get(arg)
    if raw is None:
        return fallback
    try:
        return max(low, min(high, int(raw)))
    except ValueError:
        return fallback


def _requested_shape() -> BuildShape:
    """The build shape to size this request's graph with, parsed from the request.

    The shape is the user's, carried by the browser, so it arrives as query args
    rather than from config (see :mod:`atlas.services.graph.shape`). Parsed the
    same way as the provider: **every value degrades**, never errors — a forged
    or nonsensical arg falls back to the adaptive default or clamps into range,
    because a bad query string should cost the user a differently-sized graph,
    not a failed build.

    Query args:
        adaptive: Falsy (``0``/``false``/``no``) hands sizing to the user; any
            other value (including absent) keeps the app's adaptive sizing.
        cluster_start: The Latest bands' first year. Absent keeps the fixed span.
        bands: How many one-year bands the fixed span covers.
        per_band: The top-N citers each band keeps.

    Returns:
        The parsed shape. Non-adaptive args are ignored — and left at their
        defaults — while ``adaptive`` stays on.
    """
    adaptive = request.args.get("adaptive", "").lower() not in ("0", "false", "no")
    if adaptive:
        return BuildShape()
    # A cluster start outside the plausible publication era is a forged value,
    # not a preference — drop it and take the fixed span, the same fallback an
    # unplaceable tau rule lands on.
    cluster_start: int | None = None
    raw_start = request.args.get("cluster_start")
    if raw_start:
        try:
            year = int(raw_start)
        except ValueError:
            year = 0
        if _MIN_BAND_YEAR <= year <= datetime.date.today().year:
            cluster_start = year
    return BuildShape(
        adaptive=False,
        cluster_start=cluster_start,
        # The upper bound is OpenAlex's 200-row page cap: a larger per-band ask
        # can't be served by one provider, so it's clamped rather than honored
        # unevenly across the two.
        number_of_bands=_bounded_int("bands", caps.LATEST_NUMBER_OF_BANDS, 1, _MAX_BANDS),
        nodes_per_band=_bounded_int("per_band", caps.LATEST_NODES_PER_BAND, 1, _MAX_PER_BAND),
    )


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
            to ``config.providers.default_provider``).
        refresh: Truthy (``1``/``true``/``yes``) bypasses the cached snapshot.
        adaptive, cluster_start, bands, per_band: The build shape — how much of
            the neighborhood to ship (see :func:`_requested_shape`).

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
        result = graph_service.build_graph(
            seed, provider=provider, refresh=refresh, shape=_requested_shape()
        )
    except _BUILD_ERRORS as exc:
        current_app.logger.warning("graph build failed for %s (%s): %s", seed, provider, exc)
        return jsonify({"error": f"{_provider_name(provider)} is unavailable — try again."}), 502
    if not result:
        return jsonify({"error": f"No paper found on {_provider_name(provider)} for {seed}."}), 404
    return jsonify(result.model_dump())


def _build_stream(
    seed: str, provider: Provider, refresh: bool, shape: BuildShape
) -> Iterator[str]:
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
        shape: How much of the neighborhood to ship. Parsed by the *route* and
            handed in, because this generator and its worker thread run after
            the request context is gone — the same reason ``provider`` and
            ``refresh`` arrive as arguments rather than being read here.

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
                shape=shape,
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
            to ``config.providers.default_provider``).
        refresh: Truthy (``1``/``true``/``yes``) bypasses the cached snapshot.
        adaptive, cluster_start, bands, per_band: The build shape — how much of
            the neighborhood to ship (see :func:`_requested_shape`).

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
    return sse_response(_build_stream(seed, provider, refresh, _requested_shape()))


@bp.get("/api/paper/<path:paper_ref>")
def api_paper(paper_ref: str) -> ResponseReturnValue:
    """Fetch full details for one paper, from the selected provider.

    Used to hydrate a node's detail panel on click — graph neighbors arrive
    without abstract/tldr. Hydration comes from the same backend the graph was
    built with, so an OpenAlex node fills in from OpenAlex (abstract + topic
    tags; no TL;DR) and an S2 node from S2.

    Args:
        paper_ref: The paper's arXiv id, a pasted abs/pdf URL, or a raw provider
            node id (papers without an arXiv id hydrate by that id).

    Query args:
        provider: ``s2`` or ``openalex`` (defaults to
            ``config.providers.default_provider``).

    Returns:
        The JSON node details on success; ``{error}`` with HTTP 404 when the
        provider has no such paper, or 502 when it's unavailable.
    """
    ref = normalize_arxiv_id(paper_ref)
    provider = _requested_provider()
    try:
        if provider == "openalex":
            node = openalex.get_paper(ref)
        else:
            # Same discrimination as build_graph's seed lookup: only an actual
            # arXiv id gets the ARXIV: prefix — a raw S2 paperId passes through.
            lookup = f"ARXIV:{ref}" if arxiv.looks_arxiv(ref) else ref
            node = semantic_scholar.get_paper(lookup)
    except _BUILD_ERRORS as exc:
        current_app.logger.warning("paper fetch failed for %s (%s): %s", ref, provider, exc)
        return jsonify({"error": f"{_provider_name(provider)} is unavailable — try again."}), 502
    if not node:
        return jsonify({"error": f"No paper found for {ref}."}), 404
    # Back-fill a previously GENERATED TL;DR (the summarizer's, cached
    # forever) so it rides hydration for free on later opens. Read-only:
    # hydration must never trigger a generation — see api_paper_tldr.
    if not node.get("tldr"):
        node["tldr"] = cache.get(_tldr_cache_key(str(node["id"])))
    # Prime the OA-PDF resolver from this hydration (the URL rode along for
    # free), so the figures fetch that follows a panel open — and any later
    # full read — doesn't re-ask the provider.
    oa_pdf = node.get("oa_pdf")
    pdf_service.prime(str(node["id"]), oa_pdf if isinstance(oa_pdf, str) and oa_pdf else None)
    return jsonify(node)


def _tldr_cache_key(node_id: str) -> str:
    """The cache key for a paper's generated TL;DR (permanent; ``v1`` is the
    invalidation lever if the summarizer's prompt materially changes).

    Args:
        node_id: The paper's provider node id.

    Returns:
        The cache key.
    """
    return f"tldr:v1:{node_id}"


@bp.post("/api/paper/tldr")
def api_paper_tldr() -> ResponseReturnValue:
    """Generate — or recall — the TL;DR for one paper.

    The detail panel's TL;DR toggle calls this for a paper that has no
    TL;DR of its own (every OpenAlex paper; the S2 papers S2 never
    summarized). **This endpoint is the only place a summary is ever
    generated**, and it runs only on that explicit user gesture — never
    during builds or hydration — so a paper nobody reads never bills
    (Patrick's rule). Results cache permanently by node id: each paper
    costs at most one model call, ever.

    The client sends the abstract it already holds (hydrated moments
    earlier) rather than this route re-fetching the paper — one fewer
    provider round trip, and the provider APIs stay off the hot path.

    JSON body:
        id: The paper's provider node id (the cache key).
        title: The paper's title.
        abstract: The abstract to summarize.

    Returns:
        ``{tldr}`` on success (cached or fresh); ``{error}`` with HTTP 400
        when the id or abstract is missing, or 502 when generation fails
        (no key, model unavailable) — the panel keeps the abstract either
        way.
    """
    payload = request.get_json(silent=True) or {}
    node_id = str(payload.get("id") or "").strip()
    title = str(payload.get("title") or "").strip()
    abstract = str(payload.get("abstract") or "").strip()
    if not node_id:
        return jsonify({"error": "missing 'id'"}), 400
    if not abstract:
        return jsonify({"error": "This paper has no abstract to summarize."}), 400
    key = _tldr_cache_key(node_id)
    cached = cache.get(key)
    if cached:
        return jsonify({"tldr": cached})
    tldr = summarizer.summarize(title, abstract)
    if tldr is None:
        current_app.logger.warning("TL;DR generation failed for %s", node_id)
        return jsonify({"error": "Couldn't generate a TL;DR — is the Anthropic key set?"}), 502
    cache.set(key, tldr)
    return jsonify({"tldr": tldr})


@bp.get("/api/paper/<path:paper_ref>/figures")
def api_figures(paper_ref: str) -> Response:
    """Fetch a paper's figures + captions for the detail panel.

    Two sources, best first: the ar5iv render (real ``<figcaption>``s) when
    the paper has one, else floats mined from its open-access PDF — figures,
    tables, and algorithm boxes with caption-anchored extraction (see
    ``services/pdf``). ar5iv image URLs are rewritten to the same-origin
    proxy; manifest entries are served as rendered PNGs by ``api_pdf_figure``.

    Args:
        paper_ref: The paper's arXiv id, or its provider node id for papers
            not on arXiv (the frontend sends ``arxiv_id ?? id``).

    Query args:
        provider: ``s2`` or ``openalex`` — who to ask for the OA-PDF URL on
            a cache miss (defaults to ``config.providers.default_provider``).

    Returns:
        JSON ``{available, figures: [{image, caption}]}``. Papers with
        neither an ar5iv render nor a minable OA PDF come back as
        ``available: false`` — not an error — and any outage degrades the
        same way rather than 500-ing the panel.
    """
    ref = normalize_arxiv_id(paper_ref)
    is_arxiv = arxiv.looks_arxiv(ref)
    if is_arxiv:
        try:
            result = arxiv.get_figures(ref)
        except Exception:  # ar5iv down/slow — try the PDF fallback instead
            current_app.logger.warning("figure fetch failed for %s", ref, exc_info=True)
            result = {"available": False, "figures": []}
        if result.get("figures"):
            for figure in result["figures"]:
                figure["image"] = "/api/figure_proxy?src=" + urllib.parse.quote(
                    figure["image"], safe=""
                )
            return jsonify(result)

    # No ar5iv render (or not an arXiv paper at all): mine the OA PDF.
    try:
        oa_url: str | None
        if is_arxiv:
            oa_url = pdf_service.arxiv_pdf_url(ref)
        else:
            oa_url = pdf_service.resolve_oa_pdf(ref, _requested_provider())
        if not oa_url:
            return jsonify({"available": False, "figures": []})
        mined = pdf_service.get_pdf_floats(oa_url)
    except Exception:  # download/mining trouble — degrade, don't 500 the panel
        current_app.logger.warning("PDF figure mining failed for %s", ref, exc_info=True)
        return jsonify({"available": False, "figures": []})
    token = mined.get("token")
    figures = [
        {"image": f"/api/pdf_figure/{token}/{position}", "caption": entry.get("caption") or ""}
        for position, entry in enumerate(mined.get("floats") or [])
    ]
    return jsonify({"available": bool(figures), "figures": figures})


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


@bp.get("/api/pdf_figure/<token>/<int:figure_index>")
def api_pdf_figure(token: str, figure_index: int) -> ResponseReturnValue:
    """Serve one mined PDF float as a rendered PNG.

    The image URLs ``api_figures`` (and the researcher's ``show_figure``)
    hand the browser point here. Tokens are minted server-side when a PDF is
    mined — an unknown token resolves to no URL and 404s, which is what keeps
    this from being an open proxy (the browser never supplies a URL).

    Args:
        token: The mined PDF's token (see ``services/pdf``).
        figure_index: 0-based index into that PDF's figure manifest.

    Returns:
        PNG bytes with a day-long cache header; 404 for an unknown
        token/index or when the PDF can't be re-fetched/rendered.
    """
    try:
        payload = pdf_service.render_figure(token, figure_index)
    except pdf_service.PdfError:
        current_app.logger.warning(
            "pdf figure render failed for %s/%d", token, figure_index, exc_info=True
        )
        return Response(status=404)
    return Response(
        payload,
        mimetype="image/png",
        headers={"Cache-Control": "public, max-age=86400"},
    )


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
