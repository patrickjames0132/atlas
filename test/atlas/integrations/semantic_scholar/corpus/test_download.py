"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
The shard downloader's completeness guard, resume, and verification (no network).

Every test drives a fake ``urlopen`` that can hang up mid-body on demand — the
one behaviour that matters here, because CPython's ``HTTPResponse.read(amt)``
reports a dropped connection as an ordinary empty read. The regression these
tests lock down: a truncated body must never be renamed to the final ``.gz``
nor checkpointed done (see ``download.py``'s module docstring and docs/bugs.md).

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

import gzip
import json
import urllib.error
import urllib.request

import pytest

from atlas.config import config
from atlas.integrations.semantic_scholar.corpus import download
from atlas.integrations.semantic_scholar.corpus.datasets import CorpusError
from atlas.integrations.semantic_scholar.corpus.paths import release_paths

RELEASE_ID = "2026-08-05"
SHARD_NAME = "20260807_073810_00079_q5mh4_bdf393a8.gz"
SHARD_URL = f"https://ai2-s2ag.s3.amazonaws.com/{RELEASE_ID}/citations/{SHARD_NAME}?sig=abc"


class FakeResponse:
    """A minimal stand-in for ``http.client.HTTPResponse``.

    Serves ``body`` in chunks and can stop early — returning ``b""`` partway
    through, exactly as the stdlib does when a socket dies mid-transfer —
    while still advertising the full ``Content-Length``.
    """

    def __init__(self, body: bytes, *, status: int = 200, serve_bytes: int | None = None,
                 content_length: int | None = None):
        """Set up one canned response.

        Args:
            body: The bytes this response would send in full.
            status: The HTTP status (206 for a range response).
            serve_bytes: Stop after this many bytes, simulating a dropped
                connection. None serves the whole body.
            content_length: Override the advertised length; defaults to the
                full body length. Pass None-via-``headers`` by using -1.
        """
        self._body = body
        self._served = 0
        self._limit = len(body) if serve_bytes is None else serve_bytes
        self.status = status
        advertised = len(body) if content_length is None else content_length
        self.headers = {} if advertised < 0 else {"Content-Length": str(advertised)}

    def __enter__(self) -> FakeResponse:
        """Enter the context manager (the response itself)."""
        return self

    def __exit__(self, *exc_info: object) -> bool:
        """Leave the context manager without suppressing anything."""
        return False

    def read(self, size: int) -> bytes:
        """Serve up to ``size`` bytes, or b"" once the (possibly early) limit is hit.

        Args:
            size: Maximum bytes to return.

        Returns:
            The next chunk, or empty bytes at the limit.
        """
        if self._served >= self._limit:
            return b""
        chunk = self._body[self._served : self._served + size]
        chunk = chunk[: self._limit - self._served]
        self._served += len(chunk)
        return chunk


class FakeHeaders(dict):
    """A headers mapping exposing the ``.get`` the code calls."""


def install_urlopen(monkeypatch, responses):
    """Point ``urllib.request.urlopen`` at a scripted list of responses.

    Args:
        monkeypatch: pytest's monkeypatch fixture.
        responses: Callables taking the ``Request`` and returning a response
            (or raising), consumed one per call.

    Returns:
        The list that records each ``Request`` the code made.
    """
    recorded = []
    remaining = list(responses)

    def fake_urlopen(request, timeout=None):
        recorded.append(request)
        if not remaining:
            raise AssertionError("more urlopen calls than the test scripted")
        outcome = remaining.pop(0)
        return outcome(request)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    return recorded


def make_body(rows: int = 50) -> bytes:
    """A gzipped JSONL payload standing in for a citations shard.

    Args:
        rows: How many edge records to write.

    Returns:
        The gzipped bytes.
    """
    lines = "".join(
        json.dumps({"citingcorpusid": index + 2, "citedcorpusid": 1}) + "\n"
        for index in range(rows)
    )
    return gzip.compress(lines.encode("utf-8"))


@pytest.fixture()
def corpus_tmp(monkeypatch, tmp_path):
    """Point the corpus root at a temp tree and return the release's paths."""
    monkeypatch.setattr(config.storage, "s2_corpus", tmp_path / "s2corpus")
    paths = release_paths(RELEASE_ID)
    assert paths.raw.is_relative_to(tmp_path), "test would write outside tmp"
    return paths


def test_complete_body_is_promoted(monkeypatch, corpus_tmp):
    """A whole body lands as the final .gz with no .part left behind."""
    body = make_body()
    install_urlopen(monkeypatch, [lambda request: FakeResponse(body)])
    target = corpus_tmp.raw_dataset("citations") / SHARD_NAME

    total = download._download_shard(SHARD_URL, target, lambda done, whole: None)

    assert total == len(body)
    assert target.read_bytes() == body
    assert not download._part_path(target).exists()


def test_short_body_is_not_promoted(monkeypatch, corpus_tmp):
    """The regression: a truncated body raises and leaves the .gz uncreated.

    Before the guard this renamed a half-shard into place, and the damage only
    surfaced ~36 minutes into a later ingest as a DuckDB malformed-JSON error.
    """
    body = make_body()
    cut = len(body) // 2
    install_urlopen(monkeypatch, [lambda request: FakeResponse(body, serve_bytes=cut)])
    target = corpus_tmp.raw_dataset("citations") / SHARD_NAME

    with pytest.raises(download._ShortRead) as caught:
        download._download_shard(SHARD_URL, target, lambda done, whole: None)

    assert caught.value.received == cut
    assert caught.value.expected == len(body)
    assert not target.exists(), "a truncated shard must never become the final .gz"
    # The prefix survives so the next attempt can resume it.
    assert download._part_path(target).stat().st_size == cut


def test_short_body_resumes_from_part(monkeypatch, corpus_tmp):
    """A retry sends a Range for the missing tail and completes the shard."""
    body = make_body()
    cut = len(body) // 2

    def truncated(request):
        return FakeResponse(body, serve_bytes=cut)

    def tail(request):
        # A 206 carrying only the remaining bytes, as S3 would answer.
        remainder = body[cut:]
        return FakeResponse(remainder, status=206)

    recorded = install_urlopen(monkeypatch, [truncated, tail])
    target = corpus_tmp.raw_dataset("citations") / SHARD_NAME

    download._fetch_shard(
        RELEASE_ID, "citations", SHARD_NAME, SHARD_URL, target, lambda done, whole: None
    )

    assert target.read_bytes() == body
    assert not download._part_path(target).exists()
    assert recorded[0].headers.get("Range") is None
    assert recorded[1].headers.get("Range") == f"bytes={cut}-"


def test_persistently_short_shard_fails_loudly(monkeypatch, corpus_tmp):
    """Endless truncation raises CorpusError rather than promoting a stub."""
    body = make_body()
    attempts = download._SHORT_READ_RETRIES + 1
    install_urlopen(
        monkeypatch, [lambda request: FakeResponse(body, serve_bytes=10)] * attempts
    )
    target = corpus_tmp.raw_dataset("citations") / SHARD_NAME

    with pytest.raises(CorpusError, match="ended short"):
        download._fetch_shard(
            RELEASE_ID, "citations", SHARD_NAME, SHARD_URL, target, lambda done, whole: None
        )
    assert not target.exists()


def test_missing_content_length_is_taken_at_face_value(monkeypatch, corpus_tmp):
    """With no Content-Length there's nothing to check, so the body is trusted."""
    body = make_body()
    install_urlopen(
        monkeypatch, [lambda request: FakeResponse(body, content_length=-1)]
    )
    target = corpus_tmp.raw_dataset("citations") / SHARD_NAME

    total = download._download_shard(SHARD_URL, target, lambda done, whole: None)

    assert total is None
    assert target.read_bytes() == body


def stub_listing(monkeypatch, url: str = SHARD_URL) -> None:
    """Make the Datasets listing return one shard, without touching the network.

    Args:
        monkeypatch: pytest's monkeypatch fixture.
        url: The signed URL the listing should hand back.
    """
    monkeypatch.setattr(
        download.datasets, "dataset_file_urls", lambda release, dataset: [url]
    )


def test_download_release_records_expected_size(monkeypatch, corpus_tmp):
    """The checkpoint stores the advertised size, so a later run can audit it."""
    body = make_body()
    stub_listing(monkeypatch)
    install_urlopen(monkeypatch, [lambda request: FakeResponse(body)])

    download.download_release(RELEASE_ID, datasets_wanted=("citations",))

    state = json.loads(corpus_tmp.download_state.read_text(encoding="utf-8"))
    entry = state["citations"][SHARD_NAME]
    assert entry == {"bytes": len(body), "expected": len(body), "done": True}


def test_download_release_refetches_wrong_sized_shard(monkeypatch, corpus_tmp):
    """A done-but-short shard from a pre-guard run is repaired, not trusted."""
    body = make_body()
    stub_listing(monkeypatch)
    target = corpus_tmp.raw_dataset("citations") / SHARD_NAME
    target.parent.mkdir(parents=True, exist_ok=True)
    cut = len(body) // 2
    target.write_bytes(body[:cut])
    corpus_tmp.download_state.parent.mkdir(parents=True, exist_ok=True)
    corpus_tmp.download_state.write_text(
        json.dumps({"citations": {SHARD_NAME: {"bytes": cut, "expected": len(body), "done": True}}}),
        encoding="utf-8",
    )
    # Only the tail should be requested — the prefix on disk is reusable.
    recorded = install_urlopen(
        monkeypatch, [lambda request: FakeResponse(body[cut:], status=206)]
    )

    download.download_release(RELEASE_ID, datasets_wanted=("citations",))

    assert recorded[0].headers.get("Range") == f"bytes={cut}-"
    assert target.read_bytes() == body


def test_verify_flags_short_shard(monkeypatch, corpus_tmp):
    """A shard smaller than the object the server holds is reported short."""
    body = make_body()
    stub_listing(monkeypatch)
    target = corpus_tmp.raw_dataset("citations") / SHARD_NAME
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(body[: len(body) // 2])
    # The size probe: a one-byte range response carrying the true total.
    probe = FakeResponse(body[:1], status=206)
    probe.headers = FakeHeaders({"Content-Range": f"bytes 0-0/{len(body)}"})
    install_urlopen(monkeypatch, [lambda request: probe])

    problems = download.verify_release(RELEASE_ID, datasets_wanted=("citations",))

    assert len(problems) == 1
    assert problems[0].kind == "short"
    assert problems[0].expected == len(body)


def test_verify_passes_intact_shard(monkeypatch, corpus_tmp):
    """A shard matching the advertised size (and decoding) reports no problem."""
    body = make_body()
    stub_listing(monkeypatch)
    target = corpus_tmp.raw_dataset("citations") / SHARD_NAME
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(body)
    probe = FakeResponse(body[:1], status=206)
    probe.headers = FakeHeaders({"Content-Range": f"bytes 0-0/{len(body)}"})
    install_urlopen(monkeypatch, [lambda request: probe])

    assert download.verify_release(RELEASE_ID, datasets_wanted=("citations",), deep=True) == []


def test_verify_deep_catches_undecodable_shard(monkeypatch, corpus_tmp):
    """Right size, broken stream — only the deep pass can see it."""
    body = make_body()
    damaged = body[:-8] + b"\x00" * 8  # same length, mangled trailer/data
    stub_listing(monkeypatch)
    target = corpus_tmp.raw_dataset("citations") / SHARD_NAME
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(damaged)
    probe = FakeResponse(body[:1], status=206)
    probe.headers = FakeHeaders({"Content-Range": f"bytes 0-0/{len(body)}"})
    install_urlopen(monkeypatch, [lambda request: probe])

    problems = download.verify_release(RELEASE_ID, datasets_wanted=("citations",), deep=True)

    assert len(problems) == 1
    assert problems[0].kind == "corrupt"


def test_verify_reports_missing_shard(monkeypatch, corpus_tmp):
    """A listed shard absent from disk is reported rather than skipped."""
    stub_listing(monkeypatch)
    install_urlopen(monkeypatch, [])

    problems = download.verify_release(RELEASE_ID, datasets_wanted=("citations",))

    assert [problem.kind for problem in problems] == ["missing"]


def test_verify_refreshes_an_expired_url(monkeypatch, corpus_tmp):
    """A verify long enough to outlive its signatures re-lists and carries on."""
    body = make_body()
    fresh_url = SHARD_URL.replace("sig=abc", "sig=fresh")
    stub_listing(monkeypatch, fresh_url)
    target = corpus_tmp.raw_dataset("citations") / SHARD_NAME
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(body)

    def expired(request):
        raise urllib.error.HTTPError(SHARD_URL, 403, "Forbidden", FakeHeaders(), None)

    probe = FakeResponse(body[:1], status=206)
    probe.headers = FakeHeaders({"Content-Range": f"bytes 0-0/{len(body)}"})
    recorded = install_urlopen(monkeypatch, [expired, lambda request: probe])

    # The listing hands back a fresh URL, the re-probe succeeds, shard is intact.
    assert download.verify_release(RELEASE_ID, datasets_wanted=("citations",)) == []
    assert recorded[1].full_url == fresh_url


def test_gzip_is_readable_detects_truncation(tmp_path):
    """The local deep check catches a tail-cut gzip stream."""
    body = make_body()
    whole = tmp_path / "whole.gz"
    whole.write_bytes(body)
    assert download._gzip_is_readable(whole) is None

    truncated = tmp_path / "truncated.gz"
    truncated.write_bytes(body[: len(body) // 2])
    assert download._gzip_is_readable(truncated) is not None


def test_range_past_eof_promotes_a_complete_part(monkeypatch, corpus_tmp):
    """A 416 over an already-complete .part promotes it instead of restarting."""
    body = make_body()
    target = corpus_tmp.raw_dataset("citations") / SHARD_NAME
    part = download._part_path(target)
    part.parent.mkdir(parents=True, exist_ok=True)
    part.write_bytes(body)
    probe = FakeResponse(body[:1], status=206)
    probe.headers = FakeHeaders({"Content-Range": f"bytes 0-0/{len(body)}"})
    install_urlopen(monkeypatch, [lambda request: probe])

    assert download._settle_range_past_eof(SHARD_URL, target) is True
    assert target.read_bytes() == body
    assert not part.exists()


def test_range_past_eof_discards_an_overlong_part(monkeypatch, corpus_tmp):
    """A .part longer than the object is garbage and gets dropped."""
    body = make_body()
    target = corpus_tmp.raw_dataset("citations") / SHARD_NAME
    part = download._part_path(target)
    part.parent.mkdir(parents=True, exist_ok=True)
    part.write_bytes(body + b"junk")
    probe = FakeResponse(body[:1], status=206)
    probe.headers = FakeHeaders({"Content-Range": f"bytes 0-0/{len(body)}"})
    install_urlopen(monkeypatch, [lambda request: probe])

    assert download._settle_range_past_eof(SHARD_URL, target) is False
    assert not part.exists()
    assert not target.exists()


def test_expired_url_is_refreshed_and_retried(monkeypatch, corpus_tmp):
    """A 403 mid-pull re-lists the dataset and finishes on the fresh URL."""
    body = make_body()
    fresh_url = SHARD_URL.replace("sig=abc", "sig=fresh")
    stub_listing(monkeypatch, fresh_url)

    def expired(request):
        raise urllib.error.HTTPError(SHARD_URL, 403, "Forbidden", FakeHeaders(), None)

    recorded = install_urlopen(monkeypatch, [expired, lambda request: FakeResponse(body)])
    target = corpus_tmp.raw_dataset("citations") / SHARD_NAME

    download._fetch_shard(
        RELEASE_ID, "citations", SHARD_NAME, SHARD_URL, target, lambda done, whole: None
    )

    assert target.read_bytes() == body
    assert recorded[1].full_url == fresh_url
