"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
Resumable downloader for the bulk Datasets shards.

The full corpus is ~300 GB across ~450 gzipped shards (citations ≈ 390 files,
papers ≈ 60), so a download runs for hours-to-days and *will* be interrupted.
This module makes that survivable:

* **Per-shard checkpoint** (``download.json``) records the byte count and done
  flag for each shard, so a rerun skips finished shards and resumes a partial
  one from where it stopped (HTTP ``Range``).
* **Partial shards** land in a ``.part`` file and are only renamed to the final
  ``.gz`` once complete — a query/ingest never sees a truncated shard.
* **Signed-URL expiry** (a mid-download 403/416) triggers a fresh listing from
  :mod:`datasets` and a retry, so a days-long pull rides out expiring links.

Deliberately stdlib-only (``urllib``), matching the rest of the S2 client — no
new HTTP dependency for a job that's just streamed GETs with a ``Range`` header.
Invoked by the ``atlas corpus download`` CLI; not on any request path.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable

from . import datasets
from .datasets import CorpusError
from .paths import DATASETS, ReleasePaths, corpus_root, release_paths

log = logging.getLogger(__name__)

#: Read size for streaming a shard to disk — 4 MiB keeps the syscall count low
#: on multi-hundred-MB shards without a large memory footprint.
_CHUNK_BYTES = 4 * 1024 * 1024

#: Progress callback: ``(dataset, filename, bytes_done, total_bytes)``. Fired as
#: each shard streams so the CLI can render a live per-shard bar; ``total_bytes``
#: is None when the server sends no ``Content-Length``.
ProgressFn = Callable[[str, str, int, int | None], None]


def _load_state(paths: ReleasePaths) -> dict:
    """The download checkpoint, or a fresh empty one when none exists yet."""
    state_file = paths.download_state
    if not state_file.exists():
        return {}
    try:
        loaded = json.loads(state_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        log.warning("download checkpoint %s unreadable; starting fresh", state_file)
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _save_state(paths: ReleasePaths, state: dict) -> None:
    """Persist the checkpoint atomically (write-temp-then-rename)."""
    paths.download_state.parent.mkdir(parents=True, exist_ok=True)
    tmp = paths.download_state.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    tmp.replace(paths.download_state)


def _download_shard(url: str, target: Path, on_progress: Callable[[int, int | None], None]) -> None:
    """Stream one shard to ``target``, resuming a partial ``.part`` if present.

    Args:
        url: The (signed) shard URL.
        target: The final ``.gz`` path; bytes accumulate in ``<target>.part``
            and it's renamed here on completion.
        on_progress: Called with ``(bytes_done, total_bytes)`` as data streams.

    Raises:
        urllib.error.HTTPError: Propagated so the caller can detect an expired
            URL (403/416) and refresh the listing. A 416 (range past EOF) means
            the ``.part`` is already complete for a stale length — the caller
            re-verifies against a fresh URL.
        CorpusError: On a non-recoverable network failure.
    """
    part = target.with_suffix(target.suffix + ".part")
    part.parent.mkdir(parents=True, exist_ok=True)
    have = part.stat().st_size if part.exists() else 0

    request_headers = {"User-Agent": "atlas/1.0"}
    if have:
        request_headers["Range"] = f"bytes={have}-"  # resume from where we stopped
    http_request = urllib.request.Request(url, headers=request_headers, method="GET")
    try:
        with urllib.request.urlopen(http_request, timeout=300) as response:
            # Content-Length is the *remaining* bytes on a 206 range response;
            # add what we already have for a true total.
            remaining = response.headers.get("Content-Length")
            total = (have + int(remaining)) if remaining is not None else None
            mode = "ab" if have and response.status == 206 else "wb"
            if mode == "wb":
                have = 0  # server ignored our Range — restart the file cleanly
            with part.open(mode) as sink:
                while True:
                    block = response.read(_CHUNK_BYTES)
                    if not block:
                        break
                    sink.write(block)
                    have += len(block)
                    on_progress(have, total)
    except urllib.error.URLError as exc:
        if isinstance(exc, urllib.error.HTTPError):
            raise
        raise CorpusError(f"download {url} -> {exc.reason}") from exc
    part.replace(target)


def download_release(
    release_id: str,
    *,
    datasets_wanted: tuple[str, ...] = DATASETS,
    shards: int | None = None,
    on_progress: ProgressFn | None = None,
) -> None:
    """Download (or resume) a release's shards into its ``raw/`` tree.

    Idempotent: shards the checkpoint marks done are skipped, a partial shard
    resumes, and a fresh signed URL is fetched automatically when one expires.

    Args:
        release_id: The release to download (see :func:`datasets.latest_release_id`).
        datasets_wanted: Which datasets to pull — defaults to both. Pass a
            single-element tuple to grab only ``papers`` or ``citations``.
        shards: Cap the number of shards **per dataset** (for a quick sample —
            e.g. ``shards=1`` pulls ~1 GB to prove the pipeline before the full
            300 GB). None downloads every shard.
        on_progress: Optional per-shard streaming callback (see :data:`ProgressFn`).

    Raises:
        CorpusError: When the corpus root is unconfigured, or a shard fails even
            after refreshing its URL.
    """
    if corpus_root() is None:
        raise CorpusError("config.storage.s2_corpus is not set — nowhere to download to")
    paths = release_paths(release_id)
    state = _load_state(paths)

    for dataset in datasets_wanted:
        urls = datasets.dataset_file_urls(release_id, dataset)
        if shards is not None:
            urls = urls[:shards]
        # Map stable filename -> latest signed URL, so a refresh re-keys cleanly.
        by_name = {datasets.shard_filename(url): url for url in urls}
        dataset_state = state.setdefault(dataset, {})
        target_dir = paths.raw_dataset(dataset)

        for index, (filename, url) in enumerate(by_name.items(), start=1):
            target = target_dir / filename
            if dataset_state.get(filename, {}).get("done") and target.exists():
                continue  # already have this shard whole

            def report(done: int, total: int | None) -> None:
                if on_progress:
                    on_progress(dataset, filename, done, total)

            log.info("downloading %s shard %d/%d: %s", dataset, index, len(by_name), filename)
            try:
                _download_shard(url, target, report)
            except urllib.error.HTTPError as exc:
                if exc.code not in (403, 416):
                    raise CorpusError(f"download {filename} -> HTTP {exc.code}") from exc
                # Signed URL expired mid-pull: refresh the listing and retry once.
                log.info("URL for %s expired (HTTP %d); refreshing listing", filename, exc.code)
                fresh = {
                    datasets.shard_filename(candidate): candidate
                    for candidate in datasets.dataset_file_urls(release_id, dataset)
                }
                refreshed_url = fresh.get(filename)
                if not refreshed_url:
                    raise CorpusError(f"shard {filename} vanished from refreshed listing") from exc
                _download_shard(refreshed_url, target, report)

            dataset_state[filename] = {"bytes": target.stat().st_size, "done": True}
            _save_state(paths, state)
