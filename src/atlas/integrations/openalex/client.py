"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
HTTP transport for OpenAlex: throttling, retries, URL building, and the one
error type this whole package raises.

Rate-limit / pricing strategy (verified against the live API, 2026-07-09):
  * OpenAlex meters usage — a free ``api_key`` grants $1/day, the keyless
    ``mailto`` "polite pool" $0.10/day. **Id/DOI lookups are free**;
    search/filter costs ~$1 per 1,000 calls. A per-seed citation build is a
    handful of filter calls, so the free tier is ample.
  * Both ``mailto`` and ``api_key`` ride as query params (OpenAlex has no auth
    header) — :func:`works_url` / :func:`entity_url` add them centrally.
  * 429 (over budget/rate) and 5xx are retried with exponential backoff; every
    call is paced to at most one per ``openalex.min_interval``, serialized across
    threads (graph build and agent expansion can burst concurrently).

Like the ``semantic_scholar`` client, nothing here uses a third-party HTTP
dependency — stdlib ``urllib`` keeps the client tiny and the deploy simple.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
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

# Purely internal to throttle() — nothing else ever touches this state. A
# separate lock from the S2 client's: OpenAlex has its own rate/credit budget.
_throttle_lock = threading.Lock()
_last_request = 0.0


class OpenAlexError(RuntimeError):
    """An OpenAlex request failed (network, HTTP error, or exhausted retries).
    Routes surface this as a 502.

    ``status`` carries the HTTP status code when the failure was an HTTP error
    (None for network failures / exhausted retries) — so a caller can treat an
    endpoint's meaningful status as data (e.g. a 404 from an id lookup meaning
    "no such work").
    """

    def __init__(self, message: str, *, status: int | None = None):
        """Wrap the failure message, keeping the HTTP status as data.

        Args:
            message: Human-readable description of what failed.
            status: The HTTP status code, or None for non-HTTP failures.
        """
        super().__init__(message)
        self.status = status


def throttle() -> None:
    """Block until at least ``openalex.min_interval`` has passed since the last
    call.

    Serialized across threads via a lock so concurrent callers (graph build,
    agent expansion) queue instead of bursting. A no-op when
    ``openalex.min_interval`` is 0 (tests set it there).

    Returns:
        None.
    """
    global _last_request
    if config.providers.openalex.min_interval <= 0:
        return
    with _throttle_lock:
        wait = config.providers.openalex.min_interval - (time.monotonic() - _last_request)
        if wait > 0:
            time.sleep(wait)
        _last_request = time.monotonic()


def _with_credentials(params: dict[str, str]) -> dict[str, str]:
    """Add the polite-pool ``mailto`` and (when set) ``api_key`` query params.

    OpenAlex authenticates purely by query param — there is no auth header — so
    every URL this package builds funnels through here. Empty config values are
    omitted (keyless still works, just on the smaller $0.10/day pool).
    """
    merged = dict(params)
    if config.providers.openalex.mailto:
        merged["mailto"] = config.providers.openalex.mailto
    if config.providers.openalex.api_key:
        merged["api_key"] = config.providers.openalex.api_key
    return merged


def works_url(params: dict[str, str]) -> str:
    """Build a ``/works`` list URL (a filter/search query) with credentials.

    Args:
        params: OpenAlex query params — e.g. ``filter``, ``sort``, ``per-page``,
            ``cursor``, ``select``. ``mailto``/``api_key`` are added here.

    Returns:
        The fully-encoded ``{base_url}/works?...`` URL.
    """
    query = urllib.parse.urlencode(_with_credentials(params))
    return f"{config.providers.openalex.base_url}/works?{query}"


def entity_url(entity_id: str, params: dict[str, str] | None = None) -> str:
    """Build a single-work lookup URL, ``/works/{id}`` — the FREE (unmetered)
    id/DOI path.

    Args:
        entity_id: An OpenAlex work id (``W…``), a full/short DOI
            (``doi:10.…`` or ``https://doi.org/10.…``), or another namespaced id
            OpenAlex resolves on the path (e.g. ``arxiv:2101.00001`` is *not*
            supported by OpenAlex — resolve arXiv via search/DOI instead).
        params: Extra query params (e.g. ``select``); credentials are added.

    Returns:
        The fully-encoded ``{base_url}/works/{quoted-id}?...`` URL.
    """
    quoted = urllib.parse.quote(entity_id, safe=":/")
    query = urllib.parse.urlencode(_with_credentials(params or {}))
    return f"{config.providers.openalex.base_url}/works/{quoted}?{query}"


def request(url: str, *, tries: int = 5) -> object:
    """Perform one throttled OpenAlex GET with 429/5xx backoff.

    Args:
        url: A fully-built OpenAlex URL (query string included), from
            :func:`works_url` or :func:`entity_url`.
        tries: Total attempts before giving up on repeated 429/5xx. Backoff is
            exponential (1, 2, 4, 8 seconds).

    Returns:
        The decoded JSON response (a dict, per OpenAlex).

    Raises:
        OpenAlexError: On a non-retryable HTTP error, a network failure, or when
            all ``tries`` attempts were consumed by 429/5xx.
    """
    headers = {"User-Agent": "atlas/1.0 (https://github.com/patrickjames0132/arxiv-digest)"}
    last_error: Exception | None = None
    for attempt in range(tries):
        throttle()
        http_request = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(http_request, timeout=config.providers.openalex.timeout) as response:
                return json.loads(response.read().decode())
        except urllib.error.HTTPError as exc:
            last_error = exc
            retryable = exc.code == 429 or 500 <= exc.code < 600
            if retryable and attempt < tries - 1:
                wait = 2**attempt  # 1, 2, 4, 8 seconds
                log.warning("OpenAlex %s on %s; backing off %ss", exc.code, url, wait)
                time.sleep(wait)
                continue
            raise OpenAlexError(f"OpenAlex GET {url} -> HTTP {exc.code}", status=exc.code) from exc
        except urllib.error.URLError as exc:
            raise OpenAlexError(f"OpenAlex GET {url} -> {exc.reason}") from exc
    raise OpenAlexError(f"OpenAlex GET {url} -> gave up after {tries} tries") from last_error
