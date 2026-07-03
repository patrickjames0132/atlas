"""Bring-your-own sources routes (Phase 3d): the user's local semantic library.

GET  /api/sources       -> list the user's local semantic library
POST /api/sources       -> ingest a PDF upload or a {url} into the library
DEL  /api/sources/<id>  -> remove a source from the library
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from flask import Blueprint, Response, current_app, jsonify, request

from .. import sources as sources_service

bp = Blueprint("sources", __name__)


@bp.get("/api/sources")
def api_sources_list() -> Response:
    """List the user's uploaded sources. ``available`` reports whether local
    embeddings + sqlite-vec loaded (so the UI can explain a disabled state)."""
    try:
        available = sources_service.available()
    except Exception:
        current_app.logger.exception("sources availability check failed")
        available = False
    return jsonify({"available": available, "sources": sources_service.list_sources()})


@bp.post("/api/sources")
def api_sources_add() -> Response:
    """Ingest a source: either a multipart PDF upload (field ``file``) or a JSON
    body ``{"url": ...}``. Returns the created source record. Synchronous — a big
    book takes a bit while it chunks + embeds."""
    title = None
    try:
        upload = request.files.get("file")
        if upload and upload.filename:
            title = (request.form.get("title") or "").strip() or None
            suffix = Path(upload.filename).suffix or ".pdf"
            # NB: on Windows an open NamedTemporaryFile holds an exclusive lock,
            # so we must close our handle before save()/ingest can reopen it.
            fd, tmp_path = tempfile.mkstemp(suffix=suffix)
            os.close(fd)
            try:
                upload.save(tmp_path)
                src = sources_service.ingest_pdf(tmp_path, title=title or Path(upload.filename).stem)
            finally:
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
        else:
            payload = request.get_json(silent=True) or {}
            url = (payload.get("url") or "").strip()
            title = (payload.get("title") or "").strip() or None
            if not url:
                return jsonify({"error": "provide a PDF file or a url"}), 400
            src = sources_service.ingest_url(url, title=title)
    except sources_service.SourceError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        current_app.logger.exception("source ingest failed")
        return jsonify({"error": str(exc)}), 500
    return jsonify(src)


@bp.delete("/api/sources/<source_id>")
def api_sources_delete(source_id: str) -> Response:
    """Remove a source and its chunks/vectors from the library."""
    return jsonify({"deleted": sources_service.delete_source(source_id)})
