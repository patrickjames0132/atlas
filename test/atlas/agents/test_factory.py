"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
The config-entry -> PydanticAI-model factory: id lookup, model-string
parsing, and explicit (non-env-var) credentials.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

import pytest

from atlas.agents import factory
from atlas.config import AgentConfig, config


def make_entry(**overrides) -> AgentConfig:
    base = {"id": "probe", "model": "anthropic:claude-test-1", "extras": {}}
    base.update(overrides)
    return AgentConfig.model_validate(base)


def test_agent_entry_looks_up_by_id(monkeypatch):
    entry = make_entry()
    monkeypatch.setattr(config.llm, "agents", [make_entry(id="other"), entry])
    assert factory.agent_entry("probe") is entry


def test_unknown_id_raises_with_the_configured_ids(monkeypatch):
    monkeypatch.setattr(config.llm, "agents", [make_entry()])
    with pytest.raises(LookupError, match="probe"):
        factory.agent_entry("nope")


def test_build_model_parses_the_model_string(monkeypatch):
    monkeypatch.setattr(config.llm, "agents", [make_entry()])
    model = factory.build_model("probe")
    assert model.model_name == "claude-test-1"


def test_unwired_provider_fails_loudly(monkeypatch):
    # Config validation normally rejects unknown vendors; bypass it to prove
    # the factory's own guard would still catch a configured-but-unwired one.
    # 'mistral' has no config block and no case arm — 'openai' used to stand
    # in here and became a real vendor in v7.13.0.
    entry = make_entry()
    object.__setattr__(entry, "model", "mistral:mistral-large")
    monkeypatch.setattr(config.llm, "agents", [entry])
    with pytest.raises(NotImplementedError, match="mistral"):
        factory.build_model("probe")


@pytest.mark.parametrize(
    ("model_string", "vendor_field", "credential", "expected_class"),
    [
        ("anthropic:claude-test-1", "anthropic", "api_key", "AnthropicModel"),
        ("openai:gpt-5", "openai", "api_key", "OpenAIChatModel"),
        ("google:gemini-2.5-flash", "google", "api_key", "GoogleModel"),
        ("ollama:qwen3:8b", "ollama", "base_url", "OllamaModel"),
    ],
)
def test_each_vendor_builds_its_own_model_type(
    monkeypatch, model_string, vendor_field, credential, expected_class
):
    """The whole point of the seam: one config string picks the vendor SDK."""
    monkeypatch.setattr(config.llm, "agents", [make_entry(model=model_string)])
    vendor = getattr(config.llm.providers, vendor_field)
    monkeypatch.setattr(
        vendor, credential, "http://localhost:11434/v1" if credential == "base_url" else "k"
    )
    model = factory.build_model("probe")
    assert type(model).__name__ == expected_class
    # An ollama model name carries its own colon ("qwen3:8b") — only the first
    # separator is the vendor, which is why build_model splits with maxsplit=1.
    assert model.model_name == model_string.split(":", 1)[1]


def test_blank_vendor_is_a_request_time_error_naming_the_alternatives(monkeypatch):
    """Must not fail at load: the keyless graph explorer has to keep working.

    The message has to be actionable too — a bare "not configured" leaves the
    reader guessing which vendors they could switch to instead.
    """
    monkeypatch.setattr(config.llm, "agents", [make_entry(model="google:gemini-2.5-flash")])
    monkeypatch.setattr(config.llm.providers.google, "api_key", "")
    monkeypatch.setattr(config.llm.providers.anthropic, "api_key", "sk-test")
    with pytest.raises(ValueError, match="anthropic") as caught:
        factory.build_model("probe")
    assert "google" in str(caught.value)


@pytest.mark.parametrize(
    ("model_string", "expected"),
    [
        ("anthropic:claude-test-1", True),
        ("openai:gpt-5", True),
        ("google:gemini-2.5-flash", True),
        ("ollama:qwen3:8b", False),
    ],
)
def test_web_search_support_is_per_vendor(monkeypatch, model_string, expected):
    """A local model has no provider-side search; the scout must be able to ask."""
    monkeypatch.setattr(config.llm, "agents", [make_entry(model=model_string)])
    assert factory.supports_web_search("probe") is expected


def test_model_for_reuses_the_model_while_config_is_unchanged(monkeypatch):
    """Rebuilding per run would open a fresh HTTP client for every request."""
    monkeypatch.setattr(config.llm, "agents", [make_entry()])
    monkeypatch.setattr(factory, "_MODELS", {})
    assert factory.model_for("probe") is factory.model_for("probe")


def test_model_for_rebuilds_when_the_agent_changes_model(monkeypatch):
    """The settings modal edits config in place and promises no restart."""
    entry = make_entry()
    monkeypatch.setattr(config.llm, "agents", [entry])
    monkeypatch.setattr(factory, "_MODELS", {})
    first = factory.model_for("probe")
    entry.model = "anthropic:claude-test-2"
    second = factory.model_for("probe")
    assert first is not second
    assert second.model_name == "claude-test-2"


def test_model_for_rebuilds_when_only_the_credentials_change(monkeypatch):
    """The subtle half: same model name, different key, must not be reused."""
    monkeypatch.setattr(config.llm, "agents", [make_entry()])
    monkeypatch.setattr(config.llm.providers.anthropic, "api_key", "sk-first")
    monkeypatch.setattr(factory, "_MODELS", {})
    first = factory.model_for("probe")
    monkeypatch.setattr(config.llm.providers.anthropic, "api_key", "sk-second")
    assert factory.model_for("probe") is not first


def test_model_for_defers_the_blank_vendor_error_to_the_call(monkeypatch):
    """Same request-time failure as build_model — caching must not pre-empt it."""
    monkeypatch.setattr(config.llm, "agents", [make_entry(model="google:gemini-2.5-flash")])
    monkeypatch.setattr(config.llm.providers.google, "api_key", "")
    monkeypatch.setattr(factory, "_MODELS", {})
    with pytest.raises(ValueError, match="google"):
        factory.model_for("probe")
