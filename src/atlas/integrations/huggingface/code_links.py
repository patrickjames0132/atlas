"""Normalize a paper's Hugging Face ``PaperInfo`` into the detail-panel envelope.

``client.fetch_paper`` hands back a typed ``PaperInfo`` (or None for a miss); we
flatten it into a small ``{available, github, models, datasets, spaces, totals,
…}`` envelope for the "code & artifacts" section of the detail panel and cache
it in SQLite (same thin cache as graph snapshots and figures). A miss (None) is
cached too, so an unindexed paper costs one request a day, not one per panel
open.

Because ``PaperInfo`` and its ``ModelInfo`` / ``DatasetInfo`` / ``SpaceInfo``
items are typed, the normalization here is plain attribute access — no
defensive dict-digging. The only rough edge is ``num_total_spaces``: the
library normalizes the models/datasets totals but leaves the spaces total under
the raw ``numTotalSpaces`` key, so we look under both names.
"""

from __future__ import annotations

import urllib.parse
from typing import Any

from ...storage import cache
from . import client

_MAX_ITEMS = 5


def empty_result(available: bool = False) -> dict:
    """The full response envelope with nothing in it.

    Also the fallback a caller can reach for directly when a lookup fails
    unexpectedly and still needs a well-shaped "no data" response to return.

    Args:
        available: Whether HF knows the paper at all.

    Returns:
        An envelope with every key present (null github, empty lists, zero
        totals) so the frontend type never deals with missing fields.
    """
    return {
        "available": available,
        "paper_url": None,
        "upvotes": 0,
        "github": None,
        "models": [],
        "datasets": [],
        "spaces": [],
        "totals": {"models": 0, "datasets": 0, "spaces": 0},
    }


def _as_int(value: Any) -> int:
    """Coerce an optional HF count (``likes``/``downloads``/a total) to an int.

    Args:
        value: The attribute value — an int, or None when HF didn't report it.

    Returns:
        The value as an int, or 0 when it isn't one.
    """
    return value if isinstance(value, int) else 0


def _repo_items(linked: Any, kind: str) -> list[dict]:
    """Normalize an HF ``linked_*`` list into detail-panel items.

    Args:
        linked: The ``PaperInfo.linked_models`` / ``linked_datasets`` /
            ``linked_spaces`` value (a list of typed items, or None).
        kind: ``"model"`` | ``"dataset"`` | ``"space"`` — decides the URL
            prefix and which metadata fields matter.

    Returns:
        Up to ``_MAX_ITEMS`` of ``{id, url, likes, downloads?, pipeline_tag?,
        emoji?}``, in HF's order (roughly most-relevant first).
    """
    prefix = {"model": "", "dataset": "datasets/", "space": "spaces/"}[kind]
    items: list[dict] = []
    for entry in (linked or [])[:_MAX_ITEMS]:
        repo_id = getattr(entry, "id", None)
        if not repo_id:
            continue
        item: dict = {
            "id": repo_id,
            "url": f"{client.BASE_URL}/{prefix}{repo_id}",
            "likes": _as_int(getattr(entry, "likes", None)),
        }
        if kind in ("model", "dataset"):
            item["downloads"] = _as_int(getattr(entry, "downloads", None))
        if kind == "model":
            item["pipeline_tag"] = getattr(entry, "pipeline_tag", None) or None
        if kind == "space":
            item["emoji"] = getattr(entry, "emoji", None) or None
        items.append(item)
    return items


def get_code_links(arxiv_id: str, *, refresh: bool = False) -> dict:
    """Look up a paper's implementations on Hugging Face Papers, cached.

    Args:
        arxiv_id: The paper's arXiv id (a version suffix is stripped).
        refresh: When True, bypass the cache and re-fetch from HF.

    Returns:
        ``{"available", "paper_url", "upvotes", "github": {url, stars}|None,
        "models", "datasets", "spaces", "totals"}``. ``available`` is False
        when HF has never indexed the paper; that miss is cached too.

    Raises:
        HfHubHTTPError: On non-404 HF HTTP failures.
    """
    arxiv_id = (arxiv_id or "").strip().split("v")[0]
    if not arxiv_id:
        return empty_result()

    key = f"hf_code:{arxiv_id}"
    if not refresh:
        cached = cache.get(key, client.CODE_TTL)
        if cached is not None:
            return cached

    paper = client.fetch_paper(arxiv_id)
    if paper is None:
        result = empty_result()
        cache.set(key, result)
        return result

    result = empty_result(available=True)
    result["paper_url"] = f"{client.BASE_URL}/papers/{urllib.parse.quote(arxiv_id, safe='')}"
    result["upvotes"] = _as_int(paper.upvotes)
    github = paper.github_repo
    if isinstance(github, str) and github.startswith("https://github.com/"):
        result["github"] = {"url": github, "stars": _as_int(paper.github_stars)}
    result["models"] = _repo_items(paper.linked_models, "model")
    result["datasets"] = _repo_items(paper.linked_datasets, "dataset")
    result["spaces"] = _repo_items(paper.linked_spaces, "space")
    # The library normalizes the models/datasets totals but not spaces, which
    # only survives under the raw camelCase key — hence the two-name lookup.
    spaces_total = getattr(paper, "num_total_spaces", None)
    if spaces_total is None:
        spaces_total = getattr(paper, "numTotalSpaces", None)
    result["totals"] = {
        "models": max(_as_int(getattr(paper, "num_total_models", None)), len(result["models"])),
        "datasets": max(_as_int(getattr(paper, "num_total_datasets", None)), len(result["datasets"])),
        "spaces": max(_as_int(spaces_total), len(result["spaces"])),
    }
    cache.set(key, result)
    return result
