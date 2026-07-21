"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
Config sanity: the example template, validation strictness, derived paths.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from atlas.config import PROJECT_ROOT, Config, config


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
    """A typo'd (or deleted — e.g. the retired count caps) key fails loudly
    instead of being silently ignored."""
    cfg = set_nested(example_config(), ("graph", "cache_ttll"), 10)
    with pytest.raises(ValidationError, match="cache_ttll"):
        Config.model_validate(cfg)


def test_legacy_budget_fields_must_go_through_extras():
    """Retired per-tool budgets (max_steps, etc.) aren't Agent fields anymore —
    extras is the only place unstructured settings can live."""
    cfg = set_nested(example_config(), ("llm", "agents", 0, "max_steps"), 12)
    with pytest.raises(ValidationError, match="max_steps"):
        Config.model_validate(cfg)


def test_agent_extras_are_typed_not_free_form():
    """extras stopped being a free-form escape hatch (v6.0.0): each agent's
    knobs are validated against its registered model, so junk is rejected at
    load instead of reaching the agent. See TestAgentExtras below."""
    cfg = set_nested(
        example_config(), ("llm", "agents", 0, "extras"), {"max_steps": 12, "nested": [1, 2]}
    )
    with pytest.raises(ValidationError):
        Config.model_validate(cfg)


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
        (("server", "port"), 70000),  # not a TCP port
        (("providers", "s2", "timeout"), -5),  # negative timeout is nonsense
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


def test_missing_user_chosen_config_file_errors(tmp_path):
    """A sidecar-named file that doesn't exist is an error (only the DEFAULT
    config.json is auto-created from the example — see load_settings)."""
    from atlas.config import load_settings

    with pytest.raises(FileNotFoundError, match="nope.json"):
        load_settings(tmp_path / "nope.json")


class TestAgentExtras:
    """Agent knobs are typed (config.AGENT_EXTRAS), not a free-form dict —
    so a nonsensical value fails at load rather than reaching the agent."""

    def _with_extras(self, agent_id: str, extras: dict):
        """The example config with one agent's extras replaced."""
        cfg = example_config()
        for entry in cfg["llm"]["agents"]:
            if entry["id"] == agent_id:
                entry["extras"] = extras
        return cfg

    def test_omitted_knobs_take_their_defaults(self):
        loaded = Config.model_validate(self._with_extras("lecturer", {}))
        lecturer = next(entry for entry in loaded.llm.agents if entry.id == "lecturer")
        assert lecturer.extras == {
            "frontier_window_months": 60,
            "min_beats": 7,
            "max_beats": 12,
        }

    def test_negative_knob_is_rejected(self):
        with pytest.raises(ValidationError, match="min_beats"):
            Config.model_validate(self._with_extras("lecturer", {"min_beats": -1}))

    def test_zero_is_rejected_where_it_makes_no_sense(self):
        with pytest.raises(ValidationError, match="max_steps"):
            Config.model_validate(self._with_extras("researcher", {"max_steps": 0}))

    def test_disabling_a_budget_with_zero_is_allowed(self):
        """0 figures means "no inline figures" — legitimate, unlike 0 steps."""
        loaded = Config.model_validate(self._with_extras("librarian", {"figures": 0}))
        librarian = next(entry for entry in loaded.llm.agents if entry.id == "librarian")
        assert librarian.extras["figures"] == 0

    def test_beat_bounds_must_be_ordered(self):
        with pytest.raises(ValidationError, match="min_beats"):
            Config.model_validate(
                self._with_extras("lecturer", {"min_beats": 9, "max_beats": 4})
            )

    def test_unknown_knob_is_rejected(self):
        with pytest.raises(ValidationError, match="beat_count"):
            Config.model_validate(self._with_extras("lecturer", {"beat_count": 5}))

    def test_knobs_on_an_agent_that_has_none_are_rejected(self):
        with pytest.raises(ValidationError, match="no tunable knobs"):
            Config.model_validate(self._with_extras("summarizer", {"max_steps": 3}))
