"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
Client for the Semantic Scholar **Datasets** API — the bulk-release index.

Distinct from the Academic Graph client (``..client``): the Datasets API is a
different host, needs the api key for the per-dataset file listing, and throttles
*far* harder (a bare listing 429s within a couple of calls). So it gets its own
tiny requester with a patient backoff rather than reusing the graph throttle.

Two endpoints matter:

* ``GET /release/latest`` — the newest release id plus a one-line description of
  each dataset. Cheap and unauthenticated.
* ``GET /release/{id}/dataset/{name}`` — the README plus the list of shard
  download URLs. The URLs are **pre-signed S3 links that expire** (hours), so
  they're fetched fresh at download time, never cached to disk — a multi-day
  pull re-requests them as it goes.

Nothing here downloads shard *bytes* (that's ``download.py``); this module only
talks to the JSON index.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse

from ....config import config

log = logging.getLogger(__name__)

#: Base URL of the Datasets API (its own host/version, unrelated to graph_url).
DATASETS_BASE = "https://api.semanticscholar.org/datasets/v1"


class CorpusError(RuntimeError):
    """A corpus operation failed — a Datasets-API request, a download, or an
    ingest step. Kept separate from ``S2Error`` because the corpus pipeline is
    an offline/operator concern (the CLI), not a per-request graph-build one.
    """


def _request(url: str, *, tries: int = 8) -> object:
    """One Datasets-API GET with a patient 429 backoff.

    The api key (``providers.s2.api_key``) is sent when configured — the
    per-dataset file listing requires it. Backoff is longer than the graph
    client's because this endpoint rate-limits aggressively.

    Args:
        url: The fully-built Datasets-API URL.
        tries: Total attempts before giving up on repeated 429s. Backoff is
            ``5 * 2**attempt`` seconds (5, 10, 20, …) — patient enough to ride
            out this endpoint's sustained throttling.

    Returns:
        The decoded JSON response.

    Raises:
        CorpusError: On a non-429 HTTP error, a network failure, or when every
            attempt was consumed by 429s.
    """
    request_headers = {"User-Agent": "atlas/1.0"}
    if config.providers.s2.api_key:
        request_headers["x-api-key"] = config.providers.s2.api_key
    last_error: Exception | None = None
    for attempt in range(tries):
        http_request = urllib.request.Request(url, headers=request_headers, method="GET")
        try:
            with urllib.request.urlopen(http_request, timeout=config.providers.s2.timeout) as response:
                return json.loads(response.read().decode())
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code == 429 and attempt < tries - 1:
                wait = 5 * 2**attempt  # 5, 10, 20, 40, … seconds
                log.warning("S2 datasets 429 on %s; backing off %ss", url, wait)
                time.sleep(wait)
                continue
            raise CorpusError(f"datasets GET {url} -> HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise CorpusError(f"datasets GET {url} -> {exc.reason}") from exc
    raise CorpusError(f"datasets GET {url} -> gave up after {tries} tries") from last_error


def latest_release_id() -> str:
    """The id of the newest Datasets release (e.g. ``"2026-07-07"``).

    Returns:
        The ``release_id`` string.

    Raises:
        CorpusError: When the request fails or the response lacks a release id.
    """
    data = _request(f"{DATASETS_BASE}/release/latest")
    release_id = data.get("release_id") if isinstance(data, dict) else None
    if not release_id:
        raise CorpusError("datasets /release/latest returned no release_id")
    return str(release_id)


def dataset_file_urls(release_id: str, dataset: str) -> list[str]:
    """The pre-signed download URLs for every shard of one dataset.

    These URLs expire, so callers fetch them just-in-time and never persist
    them — on expiry (a 403 mid-download) the downloader simply calls this
    again for a fresh batch.

    Args:
        release_id: The release to list (e.g. ``"2026-07-07"``).
        dataset: ``"papers"`` or ``"citations"``.

    Returns:
        The shard URLs, in the order the API returns them.

    Raises:
        CorpusError: When the request fails or returns no file list.
    """
    data = _request(f"{DATASETS_BASE}/release/{release_id}/dataset/{dataset}")
    files = data.get("files") if isinstance(data, dict) else None
    if not isinstance(files, list) or not files:
        raise CorpusError(f"datasets {dataset} listing for {release_id} had no files")
    return [str(url) for url in files]


def shard_filename(url: str) -> str:
    """The stable shard filename parsed from a (signed) download URL.

    The signature lives in the query string; the path's last segment is the
    stable name (e.g. ``20260710_071652_00151_….gz``), so it's what the shard
    is saved as and keyed by in the download checkpoint — the same shard keeps
    the same name across URL refreshes.

    Args:
        url: A shard download URL (signed or not).

    Returns:
        The final path segment, ``.gz`` filename.
    """
    return urlparse(url).path.rsplit("/", 1)[-1]
