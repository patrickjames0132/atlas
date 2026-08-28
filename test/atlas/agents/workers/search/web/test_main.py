"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
The web scout's degradation path: what happens when the configured vendor has
no provider-side web search at all (a local Ollama model, since v7.13.0).

Both the vendor check and the model are read per run (``factory``), so these
patch the factory rather than a module constant.

The behaviour under test is deliberately a *refusal to call the model*. An
agent instructed to search, holding no search tool, does not fail cleanly — it
invents sources — so "don't ask it" is the only honest answer, and these tests
pin that rather than the wording of the message.

``scout`` is a coroutine and this suite carries no async plugin, so each test
drives it with ``asyncio.run``. That is deliberate over adding pytest-asyncio
for two tests: nothing here needs the app's shared loop (see ``streams.py``),
only a coroutine run to completion.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

import asyncio

from atlas.agents.workers.search.web import main as web


def test_no_web_search_returns_empty_without_calling_the_model(monkeypatch):
    """The important half: an unsupported vendor costs a request, not a lie."""
    called = False

    async def must_not_run(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("the scout called the model with no search tool")

    monkeypatch.setattr(web.factory, "supports_web_search", lambda agent_id: False)
    monkeypatch.setattr(web.agent, "run", must_not_run)

    findings = asyncio.run(web.scout("who won the 2026 Turing award"))

    assert findings.sources == []
    assert not called
    # The summary is the researcher's only signal that the web was unreachable,
    # so it has to say so rather than coming back blank.
    assert "unavailable" in findings.summary.lower()


def test_supported_vendor_still_searches(monkeypatch):
    """The guard must not swallow the normal path."""

    class Result:
        output = web.WebFindings(
            summary="found it",
            sources=[
                web.WebSource(
                    title="T", url="https://example.org", note="what it said"
                )
            ],
        )

    async def fake_run(need, **kwargs):
        # The model and the search capability both ride the call now, not the
        # Agent — that is what lets a settings change take effect without a
        # restart, so assert they actually arrive.
        assert kwargs["model"] == "stub-model"
        assert kwargs["capabilities"]
        return Result()

    monkeypatch.setattr(web.factory, "supports_web_search", lambda agent_id: True)
    monkeypatch.setattr(web.factory, "model_for", lambda agent_id: "stub-model")
    monkeypatch.setattr(web.agent, "run", fake_run)

    findings = asyncio.run(web.scout("anything"))

    assert findings.summary == "found it"
    assert [source.url for source in findings.sources] == ["https://example.org"]
