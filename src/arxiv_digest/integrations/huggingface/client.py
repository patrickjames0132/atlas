"""Shared HTTP transport for Hugging Face Papers.

The one raw call this package makes — ``GET /api/papers/{arxiv_id}`` — lives
here, along with the host, base URL, and cache TTL, so ``code_links.py`` can
stay pure normalization. One external service, one transport layer (same
shape as the ar5iv package's ``client``).
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

from ...config import config

HF_HOST = "huggingface.co"
BASE_URL = f"https://{HF_HOST}"
_USER_AGENT = {"User-Agent": "arxiv-atlas/1.1 (https://github.com/patrickjames0132/arxiv-digest)"}
# Fresh papers accrete repos/models quickly, so re-check daily (matches the
# graph snapshot TTL). Misses (paper not on HF) share the same TTL. Bump
# `refresh` on the caller to force a re-fetch.
CODE_TTL = 60 * 60 * 24


def fetch_paper(arxiv_id: str) -> dict | None:
    """Fetch the raw HF Papers record for an arXiv id.

    Args:
        arxiv_id: A bare arXiv id (version already stripped).

    Returns:
        The parsed JSON record, or None when HF has no page for the paper
        (HTTP 404 — most pre-2023 or niche papers).

    Raises:
        urllib.error.HTTPError: On non-404 HTTP failures.
        urllib.error.URLError: On network failures.
        ValueError: When the response isn't valid JSON.
    """
    url = f"{BASE_URL}/api/papers/{urllib.parse.quote(arxiv_id, safe='')}"
    request = urllib.request.Request(url, headers=_USER_AGENT)
    try:
        with urllib.request.urlopen(request, timeout=config.s2.timeout) as response:
            data = json.loads(response.read().decode("utf-8", "replace"))
            return data if isinstance(data, dict) else None
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise
