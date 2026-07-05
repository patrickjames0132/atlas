"""Config sanity: the example template, validation strictness, derived paths."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from arxiv_digest.config import PROJECT_ROOT, Config, config


def example_config() -> dict:
    """A fresh, fully-valid config dict to mutate per test."""
    return json.loads((PROJECT_ROOT / "config.example.json").read_text())


def set_nested(cfg: dict, path: tuple, value: object) -> dict:
    """Set cfg[path[0]][path[1]]...[path[-1]] = value; returns cfg for chaining.

    Path elements can be dict keys or list indices (e.g. ("llm", "agents", 0, "model")).
    """
    node = cfg
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    return cfg


def test_example_config_is_valid():
    """config.example.json must always parse — it's the template users copy."""
    Config.model_validate(example_config())


def test_db_paths_follow_data_dir(tmp_path, monkeypatch):
    """All three databases live under data_dir — one override moves them all."""
    monkeypatch.setattr(config.storage, "data_dir", tmp_path)
    assert config.storage.digest_db == tmp_path / "digest.db"
    assert config.storage.sources_db == tmp_path / "sources.db"
    assert config.storage.sessions_db == tmp_path / "sessions.db"


def test_ensure_dirs_creates_data_dir(tmp_path, monkeypatch):
    """A fresh checkout gets its data directory made on demand."""
    target = tmp_path / "nested" / "data"
    monkeypatch.setattr(config.storage, "data_dir", target)
    config.storage.ensure_dirs()
    assert target.is_dir()


def test_relative_data_dir_is_anchored_to_repo_root():
    """"data" in config.json means <repo>/data regardless of the cwd."""
    cfg = set_nested(example_config(), ("storage", "data_dir"), "data")
    loaded = Config.model_validate(cfg)
    assert loaded.storage.data_dir == PROJECT_ROOT / "data"


def test_unknown_keys_are_rejected():
    """A typo'd key fails loudly instead of being silently ignored."""
    cfg = set_nested(example_config(), ("graph", "ref_limitt"), 10)
    with pytest.raises(ValidationError, match="ref_limitt"):
        Config.model_validate(cfg)


def test_legacy_budget_fields_must_go_through_extras():
    """Retired per-tool budgets (max_steps, etc.) aren't Agent fields anymore —
    extras is the only place unstructured settings can live."""
    cfg = set_nested(example_config(), ("llm", "agents", 0, "max_steps"), 12)
    with pytest.raises(ValidationError, match="max_steps"):
        Config.model_validate(cfg)


def test_agent_extras_accepts_arbitrary_data():
    """extras is a free-form escape hatch — any JSON-serializable value is fine."""
    cfg = set_nested(
        example_config(), ("llm", "agents", 0, "extras"), {"max_steps": 12, "nested": [1, 2]}
    )
    loaded = Config.model_validate(cfg)
    assert loaded.llm.agents[0].extras == {"max_steps": 12, "nested": [1, 2]}


def test_agents_list_cannot_be_empty():
    """An app with zero configured agents can't do anything — reject it."""
    cfg = example_config()
    cfg["llm"]["agents"] = []
    with pytest.raises(ValidationError, match="agents"):
        Config.model_validate(cfg)


def test_duplicate_agent_ids_are_rejected():
    """Other code looks agents up by id — a duplicate would be ambiguous."""
    cfg = example_config()
    cfg["llm"]["agents"].append(dict(cfg["llm"]["agents"][0]))
    with pytest.raises(ValidationError, match="duplicate agent id"):
        Config.model_validate(cfg)


def test_agent_model_requires_provider_prefix():
    """A bare model name (no '<provider>:' prefix) isn't a valid PydanticAI id."""
    cfg = set_nested(example_config(), ("llm", "agents", 0, "model"), "claude-sonnet-4-6")
    with pytest.raises(ValidationError, match="provider"):
        Config.model_validate(cfg)


def test_agent_provider_property_parses_the_prefix():
    """AgentConfig.provider is the vendor name before the colon in `model`."""
    loaded = Config.model_validate(example_config())
    assert loaded.llm.agents[0].provider == "anthropic"


def test_agent_provider_must_be_configured():
    """An agent naming a vendor with no `providers` entry fails at load, not at
    its first request."""
    cfg = set_nested(example_config(), ("llm", "agents", 0, "model"), "openai:gpt-4o")
    with pytest.raises(ValidationError, match="openai"):
        Config.model_validate(cfg)


@pytest.mark.parametrize(
    ("path", "bad_value"),
    [
        (("graph", "recs_pool"), "trending"),  # not one of the two known pools
        (("server", "port"), 70000),  # not a TCP port
        (("s2", "timeout"), -5),  # negative timeout is nonsense
        (("llm", "agents", 0, "model"), ""),  # a blank model name can't be called
        (("llm", "agents", 0, "id"), ""),  # a blank id can't be looked up
    ],
)
def test_bad_values_are_rejected(path, bad_value):
    cfg = set_nested(example_config(), path, bad_value)
    with pytest.raises(ValidationError):
        Config.model_validate(cfg)


def test_overlap_must_be_smaller_than_chunk():
    """An overlap as big as the chunk would make chunking loop forever."""
    cfg = example_config()
    cfg["sources"]["chunking"]["overlap"] = cfg["sources"]["chunking"]["chars"]
    with pytest.raises(ValidationError, match="overlap"):
        Config.model_validate(cfg)


def test_missing_config_file_has_helpful_error(tmp_path):
    """A fresh clone without config.json gets told exactly what to do."""
    from arxiv_digest.config import load_settings

    with pytest.raises(FileNotFoundError, match="config.example.json"):
        load_settings(tmp_path / "nope.json")
