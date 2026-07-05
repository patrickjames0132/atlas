"""Normalize a paper's Hugging Face Papers record into the detail-panel envelope.

HF's ``/api/papers`` response is sprawling and loosely-typed — ``linkedModels``
/ ``linkedDatasets`` / ``linkedSpaces`` samples, their ``numTotal*`` counts,
upvotes, and (when someone linked one) ``githubRepo``. We flatten that into a
small ``{available, github, models, datasets, spaces, totals, …}`` envelope for
the "code & artifacts" section of the detail panel and cache it in SQLite (same
thin cache as graph snapshots and figures). Papers HF has never indexed 404 —
``client.fetch_paper`` returns None for those, and that miss is cached too, so
an unindexed paper costs one request a day, not one per panel open.
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
    """Coerce an HF count field (which may be absent or null) to an int.

    Args:
        value: The raw field value.

    Returns:
        The value as an int, or 0 when it isn't a number.
    """
    return value if isinstance(value, int) else 0


def _repo_items(raw: Any, kind: str) -> list[dict]:
    """Normalize an HF ``linked*`` list into detail-panel items.

    Args:
        raw: The raw ``linkedModels`` / ``linkedDatasets`` / ``linkedSpaces``
            value (defensively: may be missing or malformed).
        kind: ``"model"`` | ``"dataset"`` | ``"space"`` — decides the URL
            prefix and which metadata fields matter.

    Returns:
        Up to ``_MAX_ITEMS`` of ``{id, url, likes, downloads?, pipeline_tag?,
        emoji?}``, in HF's order (roughly most-relevant first).
    """
    prefix = {"model": "", "dataset": "datasets/", "space": "spaces/"}[kind]
    items: list[dict] = []
    for entry in raw if isinstance(raw, list) else []:
        if not isinstance(entry, dict) or not entry.get("id"):
            continue
        repo_id = str(entry["id"])
        item: dict = {
            "id": repo_id,
            "url": f"{client.BASE_URL}/{prefix}{repo_id}",
            "likes": _as_int(entry.get("likes")),
        }
        if kind in ("model", "dataset"):
            item["downloads"] = _as_int(entry.get("downloads"))
        if kind == "model":
            item["pipeline_tag"] = entry.get("pipeline_tag") or None
        if kind == "space":
            item["emoji"] = entry.get("emoji") or None
        items.append(item)
        if len(items) >= _MAX_ITEMS:
            break
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
        urllib.error.HTTPError: On non-404 HF HTTP failures.
        urllib.error.URLError: On network failures.
        ValueError: When HF returns malformed JSON.
    """
    arxiv_id = (arxiv_id or "").strip().split("v")[0]
    if not arxiv_id:
        return empty_result()

    key = f"hf_code:{arxiv_id}"
    if not refresh:
        cached = cache.get(key, client.CODE_TTL)
        if cached is not None:
            return cached

    raw = client.fetch_paper(arxiv_id)
    if raw is None:
        result = empty_result()
        cache.set(key, result)
        return result

    result = empty_result(available=True)
    result["paper_url"] = f"{client.BASE_URL}/papers/{urllib.parse.quote(arxiv_id, safe='')}"
    result["upvotes"] = _as_int(raw.get("upvotes"))
    github = raw.get("githubRepo")
    if isinstance(github, str) and github.startswith("https://github.com/"):
        result["github"] = {"url": github, "stars": _as_int(raw.get("githubStars"))}
    result["models"] = _repo_items(raw.get("linkedModels"), "model")
    result["datasets"] = _repo_items(raw.get("linkedDatasets"), "dataset")
    result["spaces"] = _repo_items(raw.get("linkedSpaces"), "space")
    result["totals"] = {
        "models": max(_as_int(raw.get("numTotalModels")), len(result["models"])),
        "datasets": max(_as_int(raw.get("numTotalDatasets")), len(result["datasets"])),
        "spaces": max(_as_int(raw.get("numTotalSpaces")), len(result["spaces"])),
    }
    cache.set(key, result)
    return result
