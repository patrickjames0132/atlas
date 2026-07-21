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
    entry = make_entry()
    object.__setattr__(entry, "model", "openai:gpt-5")
    monkeypatch.setattr(config.llm, "agents", [entry])
    with pytest.raises(NotImplementedError, match="openai"):
        factory.build_model("probe")
