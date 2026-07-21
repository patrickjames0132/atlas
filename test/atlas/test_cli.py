"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
The atlas CLI: ingest dispatch + clean SourceError messages, the
list/forget library commands, and `serve`'s host/port override plumbing
(the actual serve blocks on a real server, so only the pass-through is
tested).

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

from click.testing import CliRunner

from atlas import app as app_module
from atlas.cli import cli
from atlas.services import sources

RECORD = {"id": "src01", "title": "Deep Learning", "kind": "pdf", "pages": 800, "n_chunks": 1200}


def test_ingest_dispatches_urls_and_paths(monkeypatch):
    seen = []
    monkeypatch.setattr(
        sources, "ingest_url", lambda target, title=None: seen.append(("url", target)) or RECORD
    )
    monkeypatch.setattr(
        sources, "ingest_pdf", lambda target, title=None: seen.append(("pdf", target)) or RECORD
    )

    runner = CliRunner()
    assert "Ingested [pdf]" in runner.invoke(cli, ["ingest", "https://example.org/x"]).output
    assert "1200 chunks" in runner.invoke(cli, ["ingest", "/tmp/book.pdf"]).output
    assert seen == [("url", "https://example.org/x"), ("pdf", "/tmp/book.pdf")]


def test_ingest_failure_is_a_clean_message_not_a_traceback(monkeypatch):
    def scanned(target, title=None):
        raise sources.SourceError("This PDF has no extractable text — is it scanned?")

    monkeypatch.setattr(sources, "ingest_pdf", scanned)
    result = CliRunner().invoke(cli, ["ingest", "/tmp/scan.pdf"])
    assert result.exit_code != 0
    assert "is it scanned?" in result.output
    assert "Traceback" not in result.output


def test_sources_lists_rows_and_the_empty_hint(monkeypatch):
    monkeypatch.setattr(sources, "list_sources", lambda: [RECORD])
    output = CliRunner().invoke(cli, ["sources"]).output
    assert "src01" in output and "Deep Learning" in output

    monkeypatch.setattr(sources, "list_sources", lambda: [])
    assert "No sources yet" in CliRunner().invoke(cli, ["sources"]).output


def test_forget(monkeypatch):
    monkeypatch.setattr(sources, "delete_source", lambda source_id: source_id == "src01")
    runner = CliRunner()
    assert "Deleted." in runner.invoke(cli, ["forget", "src01"]).output
    assert "No such source." in runner.invoke(cli, ["forget", "nope"]).output


def test_serve_threads_host_and_port_through(monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(
        app_module, "main", lambda host=None, port=None: captured.update(host=host, port=port)
    )
    runner = CliRunner()

    # No flags -> None overrides (app.main falls back to config).
    assert runner.invoke(cli, ["serve"]).exit_code == 0
    assert captured == {"host": None, "port": None}

    # Flags flow through, with --port coerced to int.
    assert runner.invoke(cli, ["serve", "--host", "0.0.0.0", "--port", "5050"]).exit_code == 0
    assert captured == {"host": "0.0.0.0", "port": 5050}
