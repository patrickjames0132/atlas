"""Client for the Semantic Scholar Academic Graph + Recommendations APIs.

arXiv Atlas connects to S2 dynamically rather than storing a paper corpus. S2 is
the backbone Connected Papers itself uses: it maps arXiv ids directly
(``ARXIV:<id>``) and exposes references, citations, SPECTER2 embeddings, ``tldr``
summaries, and related-paper recommendations.

Rate-limit strategy (learned from a spike against the live API):
  * The single-paper GET (``/paper/{id}``) is throttled hardest — it 429s almost
    immediately for unauthenticated callers — so we hydrate node details through
    ``POST /paper/batch`` instead, which is far more lenient and bulk-friendly.
  * An optional ``S2_API_KEY`` (sent as ``x-api-key``) lifts the limits.
  * 429s are retried with exponential backoff.

Nothing here uses a third-party HTTP dependency — stdlib ``urllib`` keeps the
client tiny and the deploy simple.
"""

from __future__ import annotations

import json
import logging
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

from .. import config

log = logging.getLogger(__name__)

# Pace S2 calls to at most one per S2_MIN_INTERVAL, serialized across threads —
# the graph build, the 3e backfill, and agent expansion all burst otherwise, and
# even an authenticated key gets ~1 req/sec on the graph endpoints.
_throttle_lock = threading.Lock()
_last_request = 0.0


def _throttle() -> None:
    """Block until at least ``S2_MIN_INTERVAL`` has passed since the last call.

    Serialized across threads via a lock so concurrent callers (graph build,
    history backfill, agent expansion) queue instead of bursting. A no-op when
    ``S2_MIN_INTERVAL`` is 0.

    Returns:
        None.
    """
    global _last_request
    if config.S2_MIN_INTERVAL <= 0:
        return
    with _throttle_lock:
        wait = config.S2_MIN_INTERVAL - (time.monotonic() - _last_request)
        if wait > 0:
            time.sleep(wait)
        _last_request = time.monotonic()

# Rich fields for a focused node (the seed, or a clicked node). Requested via the
# un-throttled batch endpoint.
_DETAIL_FIELDS = (
    "paperId,externalIds,title,abstract,tldr,year,publicationDate,"
    "citationCount,referenceCount,authors.name"
)
# Lighter fields for the many neighbors in a traversal — no abstract/tldr, which
# we hydrate lazily when a node is opened. publicationDate gives month granularity
# for the timeline layout.
_NEIGHBOR_FIELDS = "paperId,externalIds,title,year,publicationDate,citationCount"

_BATCH_MAX = 500  # S2 caps /paper/batch at 500 ids per call.


class S2Error(RuntimeError):
    """A Semantic Scholar request failed (network, HTTP error, or exhausted
    retries). Routes surface this as a 502."""


def _headers() -> dict:
    """Build the request headers for an S2 call.

    Returns:
        A header dict with the client User-Agent and JSON content type, plus
        ``x-api-key`` when ``S2_API_KEY`` is configured.
    """
    h = {"User-Agent": "arxiv-atlas/1.0", "Content-Type": "application/json"}
    if config.S2_API_KEY:
        h["x-api-key"] = config.S2_API_KEY
    return h


def _request(url: str, *, method: str = "GET", body: Optional[dict] = None,
             tries: int = 4) -> object:
    """Perform one throttled S2 HTTP request with 429 backoff.

    Args:
        url: The fully-built S2 endpoint URL (query string included).
        method: HTTP method, ``"GET"`` or ``"POST"``.
        body: JSON-serializable request body for POSTs, or None.
        tries: Total attempts before giving up on repeated 429s. Backoff
            between attempts is exponential (1, 2, 4 seconds).

    Returns:
        The decoded JSON response (a dict or list, per endpoint).

    Raises:
        S2Error: On a non-429 HTTP error, a network failure, or when all
            ``tries`` attempts were consumed by 429s.
    """
    data = json.dumps(body).encode() if body is not None else None
    last_err: Optional[Exception] = None
    for attempt in range(tries):
        _throttle()
        req = urllib.request.Request(
            url, data=data, headers=_headers(), method=method
        )
        try:
            with urllib.request.urlopen(req, timeout=config.S2_TIMEOUT) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code == 429 and attempt < tries - 1:
                wait = 2 ** attempt  # 1, 2, 4 seconds
                log.warning("S2 429 on %s; backing off %ss", url, wait)
                time.sleep(wait)
                continue
            raise S2Error(f"S2 {method} {url} -> HTTP {e.code}") from e
        except urllib.error.URLError as e:
            raise S2Error(f"S2 {method} {url} -> {e.reason}") from e
    raise S2Error(f"S2 {method} {url} -> gave up after {tries} tries") from last_err


def _quote(pid: str) -> str:
    """URL-quote a paper id for use in an S2 path.

    Args:
        pid: An S2 paperId or a prefixed id like ``ARXIV:1706.03762``.

    Returns:
        The quoted id, with ``:`` and ``/`` kept literal so prefixed ids and
        old-style arXiv ids (``hep-th/9901001``) survive.
    """
    return urllib.parse.quote(pid, safe=":/")


def _node(p: Optional[dict]) -> Optional[dict]:
    """Normalize a raw S2 paper object into the app's graph-node dict.

    This is the single place the node shape is defined — everything downstream
    (graph assembly, the teacher, the frontend) consumes this dict.

    Args:
        p: A paper object as returned by S2, or None (S2 uses null for ids it
            can't resolve).

    Returns:
        A node dict with keys ``id, arxiv_id, title, abstract, tldr, year,
        month, pub_date, citation_count, authors, url`` — or None when ``p``
        is empty or carries no ``paperId``. ``month`` (1–12) is parsed from
        S2's ``publicationDate`` so the timeline can place papers between year
        lines; it is None when only the year is known.
    """
    if not p or not p.get("paperId"):
        return None
    ext = p.get("externalIds") or {}
    arxiv_id = ext.get("ArXiv")
    tldr_obj = p.get("tldr")
    tldr = tldr_obj.get("text") if isinstance(tldr_obj, dict) else None
    pub_date = p.get("publicationDate")
    month: Optional[int] = None
    if isinstance(pub_date, str) and len(pub_date) >= 7:
        try:
            m = int(pub_date[5:7])
            month = m if 1 <= m <= 12 else None
        except ValueError:
            month = None
    authors = ", ".join(
        a.get("name", "") for a in (p.get("authors") or []) if a.get("name")
    )
    if arxiv_id:
        url = f"https://arxiv.org/abs/{arxiv_id}"
    else:
        url = f"https://www.semanticscholar.org/paper/{p['paperId']}"
    return {
        "id": p["paperId"],
        "arxiv_id": arxiv_id,
        "title": p.get("title") or "(untitled)",
        "abstract": p.get("abstract"),
        "tldr": tldr,
        "year": p.get("year"),
        "month": month,
        "pub_date": pub_date if isinstance(pub_date, str) and pub_date else None,
        "citation_count": p.get("citationCount"),
        "authors": authors or None,
        "url": url,
    }


def get_papers(ids: list[str], fields: str = _DETAIL_FIELDS) -> dict[str, dict]:
    """Hydrate paper details for many ids via ``POST /paper/batch``.

    The batch endpoint is used deliberately: the single-paper GET 429s almost
    immediately unauthenticated, while batch is lenient and bulk-friendly.

    Args:
        ids: S2 paperIds or prefixed ids like ``ARXIV:1706.03762``. Falsy
            entries are dropped. Chunked to respect the 500-id batch cap.
        fields: Comma-separated S2 field list to request.

    Returns:
        A map of the *requested* id to its normalized node dict. Ids S2 can't
        resolve are omitted.

    Raises:
        S2Error: When a batch request fails after retries.
    """
    ids = [i for i in ids if i]
    if not ids:
        return {}
    out: dict[str, dict] = {}
    url = f"{config.S2_GRAPH_URL}/paper/batch?fields={urllib.parse.quote(fields)}"
    for start in range(0, len(ids), _BATCH_MAX):
        chunk = ids[start:start + _BATCH_MAX]
        data = _request(url, method="POST", body={"ids": chunk})
        # S2 returns a list aligned to the input ids, with null for unknowns
        # (anything else — _request types its JSON as object — means no rows).
        papers = data if isinstance(data, list) else []
        for req_id, paper in zip(chunk, papers):
            node = _node(paper)
            if node:
                out[req_id] = node
    return out


def get_paper(paper_id: str) -> Optional[dict]:
    """Fetch details for a single paper.

    Args:
        paper_id: An S2 paperId or a prefixed id like ``ARXIV:1706.03762``.

    Returns:
        The normalized node dict, or None when S2 has no such paper.

    Raises:
        S2Error: When the underlying batch request fails after retries.
    """
    return get_papers([paper_id]).get(paper_id)


def _neighbors(path: str, key: str, limit: int) -> list[dict]:
    """Shared traversal for the references/citations endpoints.

    Args:
        path: The endpoint path under ``/paper/`` (quoted id + relation).
        key: The nested paper key in each result item — ``"citedPaper"`` for
            references, ``"citingPaper"`` for citations.
        limit: Maximum neighbors to request.

    Returns:
        A list of ``{"node": <node dict>, "influential": bool}`` entries,
        skipping papers S2 couldn't resolve.

    Raises:
        S2Error: When the request fails after retries.
    """
    url = (
        f"{config.S2_GRAPH_URL}/paper/{path}"
        f"?fields={urllib.parse.quote(_NEIGHBOR_FIELDS)}&limit={limit}"
    )
    data = _request(url)
    out = []
    for item in (data.get("data") or []) if isinstance(data, dict) else []:
        node = _node(item.get(key))
        if node:
            out.append({"node": node, "influential": bool(item.get("isInfluential"))})
    return out


def references(paper_id: str, limit: int) -> list[dict]:
    """Fetch the papers this one CITES (its intellectual ancestors).

    Args:
        paper_id: An S2 paperId or prefixed id.
        limit: Maximum references to return.

    Returns:
        A list of ``{"node": <node dict>, "influential": bool}`` entries.

    Raises:
        S2Error: When the request fails after retries.
    """
    return _neighbors(f"{_quote(paper_id)}/references", "citedPaper", limit)


def citations(paper_id: str, limit: int) -> list[dict]:
    """Fetch the papers that CITE this one (its descendants).

    Args:
        paper_id: An S2 paperId or prefixed id.
        limit: Maximum citations to return.

    Returns:
        A list of ``{"node": <node dict>, "influential": bool}`` entries.

    Raises:
        S2Error: When the request fails after retries.
    """
    return _neighbors(f"{_quote(paper_id)}/citations", "citingPaper", limit)


def recommendations(paper_id: str, limit: int,
                    pool: Optional[str] = None) -> list[dict]:
    """Fetch embedding-based related papers (similarity neighbors).

    Args:
        paper_id: An S2 paperId or prefixed id.
        limit: Maximum recommendations to return.
        pool: The candidate set — ``"all-cs"`` or ``"recent"``. Defaults to
            ``config.GRAPH_RECS_POOL`` (``all-cs``; the ``recent`` pool returns
            nothing for older seeds).

    Returns:
        A list of ``{"node": <node dict>}`` entries (no influence flag — the
        recommendations endpoint doesn't report one).

    Raises:
        S2Error: When the request fails after retries.
    """
    pool = pool or config.GRAPH_RECS_POOL
    url = (
        f"{config.S2_RECS_URL}/papers/forpaper/{_quote(paper_id)}"
        f"?fields={urllib.parse.quote(_NEIGHBOR_FIELDS)}&limit={limit}&from={pool}"
    )
    data = _request(url)
    out = []
    recs = data.get("recommendedPapers") if isinstance(data, dict) else None
    for paper in recs or []:
        node = _node(paper)
        if node:
            out.append({"node": node})
    return out


def _year_range(lo: Optional[int], hi: Optional[int]) -> Optional[str]:
    """Format a year window for S2's ``year`` search filter.

    Args:
        lo: Earliest year (inclusive), or None for no floor.
        hi: Latest year (inclusive), or None for no ceiling.

    Returns:
        One of ``"2016-2020"``, ``"2020-"``, ``"-2015"`` — or None when both
        bounds are absent.
    """
    if lo and hi:
        return f"{lo}-{hi}"
    if lo:
        return f"{lo}-"
    if hi:
        return f"-{hi}"
    return None


def search_papers(query: str, limit: int, year_from: Optional[int] = None,
                  year_to: Optional[int] = None) -> list[dict]:
    """Relevance-search S2's whole corpus for papers matching a free-text query.

    Unlike references/citations/recommendations this is UNGROUNDED — no source
    paper — so it reaches recent or topical work that citation & similarity
    hops (lineage- and embedding-biased) can't.

    Args:
        query: Free-text search terms.
        limit: Maximum hits to return.
        year_from: Earliest publication year (inclusive), or None.
        year_to: Latest publication year (inclusive), or None.

    Returns:
        A list of ``{"node": <node dict>}`` entries, in the same shape as the
        traversal helpers.

    Raises:
        S2Error: When the request fails after retries.
    """
    params = {"query": query, "fields": _NEIGHBOR_FIELDS, "limit": limit}
    year = _year_range(year_from, year_to)
    if year:
        params["year"] = year
    url = f"{config.S2_GRAPH_URL}/paper/search?{urllib.parse.urlencode(params)}"
    data = _request(url)
    out = []
    for paper in (data.get("data") or []) if isinstance(data, dict) else []:
        node = _node(paper)
        if node:
            out.append({"node": node})
    return out
