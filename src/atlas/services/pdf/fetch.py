"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
Download an open-access PDF into the on-disk cache, once.

PDFs are orders of magnitude bigger than the JSON this app otherwise moves,
so they get their own cache: real files under ``data_dir/oa_pdfs`` (not rows
in the SQLite cache), named by a hash of their URL, pruned LRU beyond
``config.pdf.cache_files``. Everything downstream — text extraction, float
mining, on-demand figure rendering — works from the cached file, so a paper's
PDF is fetched at most once per prune cycle.

Downloads are defensive by design: the size cap aborts mid-stream (a
Content-Length header can lie or be absent), and the ``%PDF`` magic check
rejects the HTML login/consent pages some publishers serve where a PDF was
promised.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

import hashlib
import logging
import urllib.error
import urllib.request
from pathlib import Path

from ...config import config
from .errors import PdfError

log = logging.getLogger(__name__)

_USER_AGENT = {"User-Agent": "atlas/1.1 (https://github.com/patrickjames0132/atlas)"}
# Stream in 64 KiB chunks so the size cap can abort a huge download early.
_CHUNK_BYTES = 65536


def cache_dir() -> Path:
    """The directory holding cached OA PDFs (created on demand).

    Returns:
        ``config.storage.data_dir / "oa_pdfs"`` — inside the gitignored data
        directory, so cached PDFs are never committed.
    """
    directory = config.storage.data_dir / "oa_pdfs"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def url_token(url: str) -> str:
    """The stable, filesystem- and URL-safe token for one PDF URL.

    The token names the cached file and appears in ``/api/pdf_figure/<token>``
    image URLs — the browser never sees (or supplies) the underlying PDF URL,
    which is what keeps the figure route from being an open proxy.

    Args:
        url: The PDF's absolute URL.

    Returns:
        A 24-hex-char SHA-256 prefix of the URL.
    """
    return hashlib.sha256(url.encode()).hexdigest()[:24]


def cached_path(url: str) -> Path | None:
    """The cached file for a URL, when it exists (touched to refresh LRU).

    Args:
        url: The PDF's absolute URL.

    Returns:
        The path, or None when the file was never fetched or has been pruned.
    """
    path = cache_dir() / f"{url_token(url)}.pdf"
    if not path.exists():
        return None
    path.touch()  # LRU freshness — pruning evicts by mtime
    return path


def fetch_pdf(url: str) -> Path:
    """Return the cached PDF for a URL, downloading it on first use.

    Args:
        url: The PDF's absolute URL (an ``http(s)`` URL a provider reported
            as this paper's open-access PDF — never a client-supplied value).

    Returns:
        The path of the cached file.

    Raises:
        PdfError: When the URL isn't http(s), the download fails, the file
            exceeds ``config.pdf.max_bytes``, or the payload isn't a PDF.
    """
    if not url.startswith(("https://", "http://")):
        raise PdfError(f"Not an http(s) URL: {url!r}")
    existing = cached_path(url)
    if existing is not None:
        return existing

    max_bytes = config.pdf.max_bytes
    request = urllib.request.Request(url, headers=_USER_AGENT)
    chunks: list[bytes] = []
    received = 0
    try:
        with urllib.request.urlopen(request, timeout=config.pdf.timeout) as response:
            while True:
                chunk = response.read(_CHUNK_BYTES)
                if not chunk:
                    break
                received += len(chunk)
                if received > max_bytes:
                    raise PdfError(f"PDF at {url} exceeds the {max_bytes}-byte cap")
                chunks.append(chunk)
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as exc:
        raise PdfError(f"Couldn't download {url}: {exc}") from exc

    payload = b"".join(chunks)
    if not payload.startswith(b"%PDF"):
        # Publishers sometimes serve an HTML consent/login page on a "PDF" URL.
        raise PdfError(f"Payload at {url} is not a PDF")

    path = cache_dir() / f"{url_token(url)}.pdf"
    path.write_bytes(payload)
    log.info("cached OA PDF %s (%d bytes) from %s", path.name, received, url)
    _prune()
    return path


def _prune() -> None:
    """Evict least-recently-used PDFs beyond ``config.pdf.cache_files``."""
    files = sorted(cache_dir().glob("*.pdf"), key=lambda path: path.stat().st_mtime)
    excess = len(files) - config.pdf.cache_files
    for stale in files[:excess] if excess > 0 else []:
        try:
            stale.unlink()
        except OSError:  # a racing delete/open — pruning is best-effort
            log.warning("couldn't prune cached PDF %s", stale, exc_info=True)
