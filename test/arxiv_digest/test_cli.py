"""The arxiv-atlas CLI: ingest dispatch + clean SourceError messages, and
the list/forget library commands. (`serve` is untested — it blocks on a
real server.)"""

from __future__ import annotations

from click.testing import CliRunner

from arxiv_digest.cli import cli
from arxiv_digest.services import sources

RECORD = {"id": "src01", "title": "Deep Learning", "kind": "pdf", "pages": 800, "n_chunks": 1200}


def test_ingest_dispatches_urls_and_paths(monkeypatch):
    seen = []
    monkeypatch.setattr(sources, "ingest_url", lambda t, title=None: seen.append(("url", t)) or RECORD)
    monkeypatch.setattr(sources, "ingest_pdf", lambda t, title=None: seen.append(("pdf", t)) or RECORD)

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
