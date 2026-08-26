"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
The settings routes: read the active config file, write it back validated,
and repoint the app at a different file — the settings modal's backend.

Every test runs against a temp config file (the module-level ``CONFIG_PATH`` /
``CONFIG_LOCATION_FILE`` are monkeypatched into ``tmp_path``), and the shared
``config`` object's fields are snapshotted and restored around each test —
``reload_config`` mutates it in place, which would otherwise bleed one test's
written values into the next (and clobber ``_isolate``'s temp ``data_dir``).

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from atlas import config as config_module
from atlas.config import PROJECT_ROOT, Config, config
from atlas.storage import cache


def example_payload(tmp_path: Path) -> dict:
    """The tracked example config as a dict, storage isolated into ``tmp_path``.

    Args:
        tmp_path: The test's temp dir — ``data_dir`` is pointed inside it so a
            reload can't aim the app at the real ``data/``.

    Returns:
        A complete, valid config payload.
    """
    payload = json.loads((PROJECT_ROOT / "config.example.json").read_text())
    payload["storage"]["data_dir"] = str(tmp_path / "data")
    return payload


@pytest.fixture(autouse=True)
def _config_file(monkeypatch, tmp_path):
    """A temp active config file, and restoration of the shared ``config``.

    Yields:
        The temp config file's path (the active config for the test).
    """
    snapshot = {name: getattr(config, name) for name in Config.model_fields}
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(example_payload(tmp_path)) + "\n")
    monkeypatch.setattr(config_module, "CONFIG_PATH", config_path)
    monkeypatch.setattr(config_module, "CONFIG_LOCATION_FILE", tmp_path / ".config-location")
    yield config_path
    for name, value in snapshot.items():
        setattr(config, name, value)


def test_get_returns_path_and_raw_file(client, _config_file):
    response = client.get("/api/settings")
    assert response.status_code == 200
    assert response.json["path"] == str(_config_file)
    assert response.json["config"]["graph"] == {"cache_ttl": 86400}


def test_put_writes_the_file_and_applies_live(client, _config_file):
    payload = json.loads(_config_file.read_text())
    payload["graph"]["cache_ttl"] = 123
    payload["providers"]["default_provider"] = "openalex"
    response = client.put("/api/settings", json={"config": payload})
    assert response.status_code == 200
    # The file was rewritten...
    assert json.loads(_config_file.read_text())["graph"]["cache_ttl"] == 123
    # ...and the running app sees the new values without a restart.
    assert config.graph.cache_ttl == 123
    assert config.providers.default_provider == "openalex"


def test_put_invalid_config_writes_nothing(client, _config_file):
    """A rejected save reports the offending field by path, and touches nothing."""
    before = _config_file.read_text()
    payload = json.loads(before)
    payload["graph"]["cache_ttl"] = -5  # NonNegativeInt says no
    response = client.put("/api/settings", json={"config": payload})
    assert response.status_code == 400
    assert response.json["error"] == "1 invalid setting"
    assert response.json["fields"][0]["path"] == "graph.cache_ttl"
    assert "greater than or equal to 0" in response.json["fields"][0]["message"]
    assert _config_file.read_text() == before  # untouched
    assert config.graph.cache_ttl != -5


def test_put_reports_every_invalid_field(client, _config_file):
    """Several bad values come back as several entries, not one blob."""
    payload = json.loads(_config_file.read_text())
    payload["graph"]["cache_ttl"] = -5
    payload["providers"]["s2"]["timeout"] = 0  # PositiveInt says no
    response = client.put("/api/settings", json={"config": payload})
    assert response.status_code == 400
    assert response.json["error"] == "2 invalid settings"
    assert {field["path"] for field in response.json["fields"]} == {
        "graph.cache_ttl",
        "providers.s2.timeout",
    }


def test_put_unknown_key_is_rejected_with_its_name(client, _config_file):
    payload = json.loads(_config_file.read_text())
    payload["graph"]["cache_ttll"] = 1
    response = client.put("/api/settings", json={"config": payload})
    assert response.status_code == 400
    assert response.json["fields"][0]["path"] == "graph.cache_ttll"


def test_put_rejects_a_nonsensical_agent_knob(client, _config_file):
    """Agent extras are typed now: a negative beat count is caught at save,
    where it used to sail through (extras was a free-form dict)."""
    payload = json.loads(_config_file.read_text())
    lecturer = next(entry for entry in payload["llm"]["agents"] if entry["id"] == "lecturer")
    lecturer["extras"]["min_beats"] = -1
    response = client.put("/api/settings", json={"config": payload})
    assert response.status_code == 400
    field = response.json["fields"][0]
    assert field["path"].endswith(".extras")
    assert "min_beats" in field["message"]


def test_put_malformed_body_is_a_400(client, _config_file):
    assert client.put("/api/settings", json={"nope": 1}).status_code == 400
    assert client.put("/api/settings", data="not json").status_code == 400


def test_location_switch_and_clear(client, _config_file, tmp_path):
    other = tmp_path / "elsewhere" / "config.json"
    other.parent.mkdir()
    payload = example_payload(tmp_path)
    payload["graph"]["cache_ttl"] = 777
    other.write_text(json.dumps(payload) + "\n")

    response = client.put("/api/settings/location", json={"path": str(other)})
    assert response.status_code == 200
    assert response.json["path"] == str(other)
    assert config.graph.cache_ttl == 777  # switched live

    # Clearing the location returns to the default config file.
    response = client.put("/api/settings/location", json={"path": ""})
    assert response.status_code == 200
    assert response.json["path"] == str(_config_file)
    assert config.graph.cache_ttl == 86400


def test_write_uses_the_templates_key_order(client, _config_file):
    """Saves are structurally stable: whatever order the browser's JSON
    carries, the file is written in the example template's canonical order."""
    payload = json.loads(_config_file.read_text())
    scrambled = dict(reversed(list(payload.items())))  # e.g. llm first, storage last
    response = client.put("/api/settings", json={"config": scrambled})
    assert response.status_code == 200
    template_order = list(json.loads((PROJECT_ROOT / "config.example.json").read_text()))
    assert list(json.loads(_config_file.read_text())) == template_order


def test_missing_default_config_is_created_from_example(client, _config_file):
    """A fresh checkout: no config.json yet — the first GET creates it from
    the tracked example instead of erroring."""
    _config_file.unlink()
    response = client.get("/api/settings")
    assert response.status_code == 200
    assert _config_file.exists()
    example = json.loads((PROJECT_ROOT / "config.example.json").read_text())
    assert response.json["config"]["providers"]["default_provider"] == (
        example["providers"]["default_provider"]
    )


def test_pick_returns_the_native_choosers_answer(client, _config_file, monkeypatch):
    """The pick endpoint relays the OS dialog's choice (mocked — no real GUI)."""
    from atlas.routes import settings as settings_routes

    monkeypatch.setattr(settings_routes, "_native_pick", lambda: "/somewhere/config.json")
    assert client.post("/api/settings/pick").json == {"path": "/somewhere/config.json"}
    monkeypatch.setattr(settings_routes, "_native_pick", lambda: None)
    assert client.post("/api/settings/pick").json == {"path": None}


def test_location_rejects_missing_or_invalid_targets(client, _config_file, tmp_path):
    response = client.put("/api/settings/location", json={"path": str(tmp_path / "ghost.json")})
    assert response.status_code == 400 and "not found" in response.json["error"]

    broken = tmp_path / "broken.json"
    broken.write_text('{"graph": {}}')
    response = client.put("/api/settings/location", json={"path": str(broken)})
    assert response.status_code == 400
    # Neither attempt switched the app away from the test's config file.
    assert client.get("/api/settings").json["path"] == str(_config_file)


def _only_vendor(monkeypatch, vendor: str) -> None:
    """Blank every LLM vendor but one, so a listing assertion is unambiguous."""
    providers = config.llm.providers
    for name in ("anthropic", "openai", "google"):
        monkeypatch.setattr(getattr(providers, name), "api_key", "")
    monkeypatch.setattr(providers.ollama, "base_url", "")
    if vendor == "ollama":
        monkeypatch.setattr(providers.ollama, "base_url", "http://localhost:11434/v1")
    else:
        monkeypatch.setattr(getattr(providers, vendor), "api_key", "sk-test")


def test_models_endpoint_relays_the_sdk_listing(client, _config_file, monkeypatch):
    """With a key configured, the endpoint relays the (stubbed) Models API."""
    from atlas.routes import settings as settings_routes

    _only_vendor(monkeypatch, "anthropic")
    monkeypatch.setattr(
        settings_routes, "_fetch_anthropic_models",
        lambda api_key: ["claude-opus-4-8", "claude-sonnet-5"],
    )
    payload = client.get("/api/settings/models").json
    assert payload["models"] == {"anthropic": ["claude-opus-4-8", "claude-sonnet-5"]}
    assert payload["vendors"] == ["anthropic"]


def test_models_endpoint_empty_without_a_key(client, _config_file, monkeypatch):
    """Keyless: nothing configured, so nothing to list and nothing to offer."""
    providers = config.llm.providers
    for name in ("anthropic", "openai", "google"):
        monkeypatch.setattr(getattr(providers, name), "api_key", "")
    monkeypatch.setattr(providers.ollama, "base_url", "")
    payload = client.get("/api/settings/models").json
    assert payload["models"] == {}
    assert payload["vendors"] == []
    # `known` still lists everything — the modal has to offer the free vendors
    # to exactly this user, who has configured none of them.
    assert "ollama" in payload["known"]


def test_models_endpoint_degrades_on_failure(client, _config_file, monkeypatch):
    """A Models API failure degrades to empty rather than erroring the modal.

    The vendor still appears in `vendors` — it IS configured, it just could not
    be listed, and dropping it would wrongly tell the modal it is unusable.
    """
    from atlas.routes import settings as settings_routes

    def boom(api_key):
        raise RuntimeError("network down")

    _only_vendor(monkeypatch, "anthropic")
    monkeypatch.setattr(settings_routes, "_fetch_anthropic_models", boom)
    payload = client.get("/api/settings/models").json
    assert payload["models"] == {"anthropic": []}
    assert payload["vendors"] == ["anthropic"]


def test_models_endpoint_lists_a_local_ollama_server(client, _config_file, monkeypatch):
    """Ollama's listing is the honest one: what this machine has actually pulled."""
    from atlas.routes import settings as settings_routes

    _only_vendor(monkeypatch, "ollama")
    monkeypatch.setattr(
        settings_routes, "_fetch_ollama_models", lambda base_url: ["qwen3:8b"]
    )
    payload = client.get("/api/settings/models").json
    assert payload["models"] == {"ollama": ["qwen3:8b"]}
    assert payload["vendors"] == ["ollama"]


def test_models_endpoint_uses_a_curated_list_where_there_is_no_listing_api(
    client, _config_file, monkeypatch
):
    """Google and OpenAI get a short static list rather than a key-scoped dump."""
    from atlas.routes import settings as settings_routes

    _only_vendor(monkeypatch, "google")
    payload = client.get("/api/settings/models").json
    assert payload["vendors"] == ["google"]
    assert payload["models"]["google"] == settings_routes.KNOWN_MODELS["google"]


def test_drop_cache_empties_the_table_and_reports_the_count(client):
    """Everything in this table is derived, so dropping it costs nothing but a
    refetch — which is exactly what makes a one-click button safe to offer."""
    cache.set("graph:v2:s2:seed", {"nodes": []})
    cache.set("search:s2:dqn::10:", [])
    assert client.post("/api/settings/drop_cache").json == {"removed": 2}
    assert cache.get("graph:v2:s2:seed") is None
    # Idempotent: dropping an empty cache is a no-op, not an error.
    assert client.post("/api/settings/drop_cache").json == {"removed": 0}


def test_drop_cache_leaves_saved_sessions_alone(client):
    """The distinction the confirmation promises. A cache entry can be
    refetched; a saved session is the only copy of something the reader made,
    and it lives in a different store entirely."""
    from atlas.storage import sessions

    saved = sessions.save_session({"title": "A session", "data": {"nodes": []}})
    cache.set("graph:v2:s2:seed", {"nodes": []})
    client.post("/api/settings/drop_cache")
    assert sessions.get_session(saved["id"]) is not None


def test_models_endpoint_names_every_vendor_not_just_the_configured_ones(
    client, _config_file, monkeypatch
):
    """`known` is what makes the free vendors discoverable.

    A newcomer has configured nothing; offering only working vendors would hide
    precisely the two (Ollama, Google) that cost nothing to adopt.
    """
    _only_vendor(monkeypatch, "anthropic")
    payload = client.get("/api/settings/models").json
    assert payload["known"] == ["anthropic", "openai", "google", "ollama"]
    assert payload["vendors"] == ["anthropic"]
