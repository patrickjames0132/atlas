"""HTTP transport for Semantic Scholar: throttling, retries, and the one
error type this whole package raises.

Rate-limit strategy (learned from a spike against the live API):
  * An optional ``S2_API_KEY`` (sent as ``x-api-key``) lifts the limits.
  * 429s are retried with exponential backoff.
  * Every call is paced to at most one per ``s2.min_interval`` — serialized
    across threads via a lock, since graph building, lecture history
    backfill, and agent expansion can all burst concurrently, and even an
    authenticated key gets ~1 req/sec on the graph endpoints.

Nothing here uses a third-party HTTP dependency — stdlib ``urllib`` keeps
the client tiny and the deploy simple.
"""

from __future__ import annotations

import json
import logging
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from ...config import config

log = logging.getLogger(__name__)

# Purely internal to throttle() — nothing else ever touches this state.
_throttle_lock = threading.Lock()
_last_request = 0.0


class S2Error(RuntimeError):
    """A Semantic Scholar request failed (network, HTTP error, or exhausted
    retries). Routes surface this as a 502.

    ``status`` carries the HTTP status code when the failure was an HTTP
    error (None for network failures / exhausted retries) — so a caller can
    treat an endpoint's meaningful status as data, e.g. the title-match
    endpoint's 404-means-no-close-match.
    """

    def __init__(self, message: str, *, status: int | None = None):
        super().__init__(message)
        self.status = status


def throttle() -> None:
    """Block until at least ``s2.min_interval`` has passed since the last call.

    Serialized across threads via a lock so concurrent callers (graph build,
    history backfill, agent expansion) queue instead of bursting. A no-op when
    ``s2.min_interval`` is 0.

    Returns:
        None.
    """
    global _last_request
    if config.s2.min_interval <= 0:
        return
    with _throttle_lock:
        wait = config.s2.min_interval - (time.monotonic() - _last_request)
        if wait > 0:
            time.sleep(wait)
        _last_request = time.monotonic()


def headers() -> dict:
    """Build the request headers for an S2 call.

    Returns:
        A header dict with the client User-Agent and JSON content type, plus
        ``x-api-key`` when ``s2.api_key`` is configured.
    """
    request_headers = {"User-Agent": "arxiv-atlas/1.0", "Content-Type": "application/json"}
    if config.s2.api_key:
        request_headers["x-api-key"] = config.s2.api_key
    return request_headers


def request(url: str, *, method: str = "GET", body: dict | None = None, tries: int = 4) -> object:
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
    last_error: Exception | None = None
    for attempt in range(tries):
        throttle()
        http_request = urllib.request.Request(url, data=data, headers=headers(), method=method)
        try:
            with urllib.request.urlopen(http_request, timeout=config.s2.timeout) as response:
                return json.loads(response.read().decode())
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code == 429 and attempt < tries - 1:
                wait = 2**attempt  # 1, 2, 4 seconds
                log.warning("S2 429 on %s; backing off %ss", url, wait)
                time.sleep(wait)
                continue
            raise S2Error(f"S2 {method} {url} -> HTTP {exc.code}", status=exc.code) from exc
        except urllib.error.URLError as exc:
            raise S2Error(f"S2 {method} {url} -> {exc.reason}") from exc
    raise S2Error(f"S2 {method} {url} -> gave up after {tries} tries") from last_error


def quote(paper_id: str) -> str:
    """URL-quote a paper id for use in an S2 path.

    Args:
        paper_id: An S2 paperId or a prefixed id like ``ARXIV:1706.03762``.

    Returns:
        The quoted id, with ``:`` and ``/`` kept literal so prefixed ids and
        old-style arXiv ids (``hep-th/9901001``) survive.
    """
    return urllib.parse.quote(paper_id, safe=":/")
