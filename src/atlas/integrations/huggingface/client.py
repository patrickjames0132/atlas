"""Thin wrapper over the official ``huggingface_hub`` client for one call.

We only need ``HfApi.paper_info(arxiv_id)`` — HF's ``/api/papers/{id}`` endpoint
wrapped in a typed ``PaperInfo`` (linked models/datasets/Spaces, their totals,
upvotes, GitHub repo). The library owns the HTTP, retries, and user-agent, so
this module is just: hold one ``HfApi`` instance, and translate a 404 into a
"no such paper" miss (None) the way ``code_links`` expects.

``huggingface_hub`` is already in the dependency tree via ``sentence-transformers``;
we depend on it explicitly rather than leaning on that transitively.
"""

from __future__ import annotations

from huggingface_hub import HfApi
from huggingface_hub.hf_api import PaperInfo
from huggingface_hub.utils import HfHubHTTPError

BASE_URL = "https://huggingface.co"
# Fresh papers accrete repos/models quickly, so re-check daily (matches the
# graph snapshot TTL). Misses (paper not on HF) share the same TTL. Bump
# `refresh` on the caller to force a re-fetch.
CODE_TTL = 60 * 60 * 24

# HfApi is a cheap, stateless handle (no connection held); one per process is
# plenty. Papers are public, so no token is needed.
_api = HfApi()


def fetch_paper(arxiv_id: str) -> PaperInfo | None:
    """Fetch the HF Papers record for an arXiv id.

    Args:
        arxiv_id: A bare arXiv id (version already stripped).

    Returns:
        The ``PaperInfo``, or None when HF has no page for the paper (HTTP 404 —
        most pre-2023 or niche papers), which the caller caches as a miss.

    Raises:
        HfHubHTTPError: On non-404 HTTP failures.
    """
    try:
        return _api.paper_info(arxiv_id)
    except HfHubHTTPError as exc:
        if exc.response is not None and exc.response.status_code == 404:
            return None
        raise
