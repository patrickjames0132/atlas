"""Bring-your-own sources routes: the user's local semantic library.

GET  /api/sources       -> list the user's local semantic library
POST /api/sources       -> ingest a PDF upload or a {url}, streaming progress
DEL  /api/sources/<id>  -> remove a source from the library
GET  /api/sources/<id>/figure/<n> -> one mined source figure, rendered to PNG

Ingestion streams SSE: ``progress`` frames (``{done, total}`` chunks
embedded — embedding is where the time goes) and then ``done`` (the stored
source record) or ``error``. Two tiers of error, on purpose: ``SourceError``
text is written for users by the ingestion layer ("no extractable text — is
it scanned?") and goes to the client verbatim; anything unexpected is a
canned message with details in the log only.
"""

from __future__ import annotations

import logging
import os
import queue
import tempfile
import threading
from pathlib import Path
from typing import Callable, Iterator

from flask import Blueprint, Response, current_app, jsonify, request
from flask.typing import ResponseReturnValue

from ..services import sources as sources_service
from .sse import sse, sse_response

bp = Blueprint("sources", __name__)

# Module logger for the ingest generator/worker — the request context is gone
# by the time they run (see routes/sse.py).
log = logging.getLogger(__name__)


@bp.get("/api/sources")
def api_sources_list() -> Response:
    """List the user's uploaded sources.

    Returns:
        JSON ``{available, sources}``. ``available`` reports whether local
        embeddings + sqlite-vec loaded (so the UI can explain a disabled
        state); an availability-check failure degrades to False rather than
        erroring.
    """
    try:
        available = sources_service.available()
    except Exception:
        current_app.logger.exception("sources availability check failed")
        available = False
    return jsonify({"available": available, "sources": sources_service.list_sources()})


def _ingest_stream(work: Callable[[sources_service.ProgressFn], dict]) -> Iterator[str]:
    """Run one ingestion in a worker thread, streaming its progress as SSE.

    The ingest pipeline is synchronous (chunk → embed → store) and reports
    through a callback; a queue bridges those callbacks into this generator,
    which the response streams. The worker owns all error mapping so a
    failure always ends the stream with an ``error`` frame.

    Args:
        work: Runs the actual ingestion (already bound to its file/URL —
            everything request-scoped was parsed before streaming started)
            and returns the stored source record.

    Yields:
        ``progress`` frames, then exactly one ``done`` (the source record)
        or ``error`` frame.
    """
    frames: queue.Queue[tuple[str, object]] = queue.Queue()

    def worker() -> None:
        try:
            record = work(lambda done, total: frames.put(("progress", {"done": done, "total": total})))
            frames.put(("done", record))
        except sources_service.SourceError as exc:
            frames.put(("error", {"message": str(exc)}))  # user-facing by design
        except Exception:
            log.exception("source ingest failed")
            frames.put(("error", {"message": "Could not ingest that source."}))

    threading.Thread(target=worker, daemon=True).start()
    while True:
        kind, data = frames.get()
        yield sse(kind, data)
        if kind in ("done", "error"):
            return


@bp.post("/api/sources")
def api_sources_add() -> ResponseReturnValue:
    """Ingest a source into the library, streaming embedding progress.

    Body:
        Either a multipart PDF upload (field ``file``, optional ``title``
        form field) or a JSON body ``{"url": ..., "title"?: ...}``.

    Returns:
        An SSE stream: ``progress`` frames (``{done, total}`` chunks
        embedded), then ``done`` carrying the stored source record — or
        ``error`` (``{message}``; a ``SourceError``'s text verbatim, else
        canned). HTTP 400 (JSON) when neither a file nor a url was sent.
    """
    # Everything request-scoped happens HERE — the stream generator runs
    # after the request context is gone, so the upload must already be on
    # disk and the URL already parsed.
    upload = request.files.get("file")
    if upload and upload.filename:
        title = (request.form.get("title") or "").strip() or Path(upload.filename).stem
        suffix = Path(upload.filename).suffix or ".pdf"
        # NB: on Windows an open NamedTemporaryFile holds an exclusive lock,
        # so we must close our handle before save()/ingest can reopen it.
        fd, tmp_path = tempfile.mkstemp(suffix=suffix)
        os.close(fd)
        upload.save(tmp_path)

        def ingest_upload(on_progress: sources_service.ProgressFn) -> dict:
            try:
                return sources_service.ingest_pdf(tmp_path, title=title, on_progress=on_progress)
            finally:
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass

        return sse_response(_ingest_stream(ingest_upload))

    payload = request.get_json(silent=True) or {}
    url = (payload.get("url") or "").strip()
    url_title = (payload.get("title") or "").strip() or None
    if not url:
        return jsonify({"error": "provide a PDF file or a url"}), 400
    return sse_response(
        _ingest_stream(
            lambda on_progress: sources_service.ingest_url(
                url, title=url_title, on_progress=on_progress
            )
        )
    )


@bp.get("/api/sources/<source_id>/figure/<int:figure_index>")
def api_source_figure(source_id: str, figure_index: int) -> ResponseReturnValue:
    """Serve one figure mined from a source's stored PDF, rendered to PNG.

    The image URLs the researcher's ``show_source_figure`` attaches to
    answers point here — the library twin of ``/api/pdf_figure``.

    Args:
        source_id: The source's id.
        figure_index: 0-based index into the source's figure manifest.

    Returns:
        PNG bytes with a day-long cache header; 404 for an unknown source,
        an out-of-range index, or a source with no stored PDF (URL sources,
        pre-v5.28 uploads).
    """
    try:
        payload = sources_service.render_source_figure(source_id, figure_index)
    except Exception:
        log.warning(
            "source figure render failed for %s/%d", source_id, figure_index, exc_info=True
        )
        return Response(status=404)
    return Response(
        payload,
        mimetype="image/png",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@bp.delete("/api/sources/<source_id>")
def api_sources_delete(source_id: str) -> Response:
    """Remove a source and its chunks/vectors from the library.

    Args:
        source_id: The source's id.

    Returns:
        JSON ``{deleted: bool}`` — False when no such source existed
        (delete is idempotent, not a 404).
    """
    return jsonify({"deleted": sources_service.delete_source(source_id)})
