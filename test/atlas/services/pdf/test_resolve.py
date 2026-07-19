"""OA-PDF URL resolution: provider lookup, month-long caching, priming.

Provider clients are monkeypatched — resolution must never touch the live
APIs from tests.
"""

from __future__ import annotations

from atlas.services.pdf import resolve


def test_resolve_asks_provider_once_then_caches(monkeypatch):
    calls = []

    def fake_get_paper(node_id):
        calls.append(node_id)
        return {"id": node_id, "oa_pdf": "https://jmlr.org/x.pdf"}

    monkeypatch.setattr(resolve.s2, "get_paper", fake_get_paper)
    assert resolve.resolve_oa_pdf("abc", "s2") == "https://jmlr.org/x.pdf"
    assert resolve.resolve_oa_pdf("abc", "s2") == "https://jmlr.org/x.pdf"
    assert calls == ["abc"]  # second answer came from the cache


def test_resolve_caches_no_pdf_answers_too(monkeypatch):
    calls = []

    def fake_get_paper(node_id):
        calls.append(node_id)
        return {"id": node_id, "oa_pdf": None}

    monkeypatch.setattr(resolve.openalex, "get_paper", fake_get_paper)
    assert resolve.resolve_oa_pdf("W1", "openalex") is None
    assert resolve.resolve_oa_pdf("W1", "openalex") is None
    assert calls == ["W1"]


def test_resolve_does_not_cache_provider_failures(monkeypatch):
    calls = []

    def flaky_get_paper(node_id):
        calls.append(node_id)
        raise resolve.s2.S2Error("down")

    monkeypatch.setattr(resolve.s2, "get_paper", flaky_get_paper)
    assert resolve.resolve_oa_pdf("abc", "s2") is None
    assert resolve.resolve_oa_pdf("abc", "s2") is None
    assert calls == ["abc", "abc"]  # a transient outage isn't pinned for a month


def test_prime_preempts_the_provider_lookup(monkeypatch):
    monkeypatch.setattr(
        resolve.s2, "get_paper", lambda node_id: (_ for _ in ()).throw(AssertionError)
    )
    resolve.prime("abc", "https://host/p.pdf")
    assert resolve.resolve_oa_pdf("abc", "s2") == "https://host/p.pdf"
    resolve.prime("def", None)
    assert resolve.resolve_oa_pdf("def", "s2") is None


def test_arxiv_pdf_url():
    assert resolve.arxiv_pdf_url("1706.03762") == "https://arxiv.org/pdf/1706.03762"
