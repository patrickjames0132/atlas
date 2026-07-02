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
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

from . import config

log = logging.getLogger(__name__)

# Rich fields for a focused node (the seed, or a clicked node). Requested via the
# un-throttled batch endpoint.
_DETAIL_FIELDS = (
    "paperId,externalIds,title,abstract,tldr,year,"
    "citationCount,referenceCount,authors.name"
)
# Lighter fields for the many neighbors in a traversal — no abstract/tldr, which
# we hydrate lazily when a node is opened.
_NEIGHBOR_FIELDS = "paperId,externalIds,title,year,citationCount"

_BATCH_MAX = 500  # S2 caps /paper/batch at 500 ids per call.


class S2Error(RuntimeError):
    """A Semantic Scholar request failed (network, HTTP error, or exhausted
    retries). Routes surface this as a 502."""


def _headers() -> dict:
    h = {"User-Agent": "arxiv-atlas/1.0", "Content-Type": "application/json"}
    if config.S2_API_KEY:
        h["x-api-key"] = config.S2_API_KEY
    return h


def _request(url: str, *, method: str = "GET", body: Optional[dict] = None,
             tries: int = 4) -> object:
    data = json.dumps(body).encode() if body is not None else None
    last_err: Optional[Exception] = None
    for attempt in range(tries):
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
    # Keep ':' and '/' literal so "ARXIV:1706.03762" and old-style ids survive.
    return urllib.parse.quote(pid, safe=":/")


def _node(p: Optional[dict]) -> Optional[dict]:
    """Normalize an S2 paper object into our graph-node dict, or None."""
    if not p or not p.get("paperId"):
        return None
    ext = p.get("externalIds") or {}
    arxiv_id = ext.get("ArXiv")
    tldr_obj = p.get("tldr")
    tldr = tldr_obj.get("text") if isinstance(tldr_obj, dict) else None
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
        "citation_count": p.get("citationCount"),
        "authors": authors or None,
        "url": url,
    }


def get_papers(ids: list[str], fields: str = _DETAIL_FIELDS) -> dict[str, dict]:
    """Hydrate paper details for `ids` via POST /paper/batch.

    `ids` may be S2 paperIds or prefixed ids like ``ARXIV:1706.03762``. Returns a
    map of the *requested* id -> normalized node (ids S2 can't resolve are
    omitted). Chunks to respect the 500-id batch cap.
    """
    ids = [i for i in ids if i]
    if not ids:
        return {}
    out: dict[str, dict] = {}
    url = f"{config.S2_GRAPH_URL}/paper/batch?fields={urllib.parse.quote(fields)}"
    for start in range(0, len(ids), _BATCH_MAX):
        chunk = ids[start:start + _BATCH_MAX]
        data = _request(url, method="POST", body={"ids": chunk})
        # S2 returns a list aligned to the input ids, with null for unknowns.
        for req_id, paper in zip(chunk, data or []):
            node = _node(paper)
            if node:
                out[req_id] = node
    return out


def get_paper(paper_id: str) -> Optional[dict]:
    """Details for a single paper (by paperId or ``ARXIV:<id>``), or None."""
    return get_papers([paper_id]).get(paper_id)


def _neighbors(path: str, key: str, limit: int) -> list[dict]:
    """Shared traversal for references/citations. `key` is the nested paper key
    ('citedPaper' or 'citingPaper'). Returns [{node, influential}]."""
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
    """Papers this one CITES (its intellectual ancestors)."""
    return _neighbors(f"{_quote(paper_id)}/references", "citedPaper", limit)


def citations(paper_id: str, limit: int) -> list[dict]:
    """Papers that CITE this one (its descendants)."""
    return _neighbors(f"{_quote(paper_id)}/citations", "citingPaper", limit)


def recommendations(paper_id: str, limit: int,
                    pool: Optional[str] = None) -> list[dict]:
    """Embedding-based related papers (similarity neighbors). `pool` is the
    candidate set: 'all-cs' (default here) or 'recent'."""
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
