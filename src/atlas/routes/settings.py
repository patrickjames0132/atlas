"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
Read and write the app's settings — the settings modal's backend.

The modal is a **config-file editor**: it displays the active config file's
values and writes edits back to that same file, so the file stays the single
source of truth (hand-edits and modal edits are the same thing). Endpoints:

* ``GET  /api/settings`` — the active config file's path and parsed
  contents. A missing default ``config.json`` is created from the example on
  first load, so there is always a real, writable file.
* ``PUT  /api/settings`` — replace the file's contents. The body is validated
  as a complete ``Config`` **before** anything is written; on success the
  file is rewritten (keys in the template's canonical order, so saves are
  stable and diffs stay readable) and the running app's shared ``config``
  object is updated in place (``reload_config``) — no restart. On failure
  nothing changes and the 400 body carries a per-field error list
  (``{"error": <summary>, "fields": [{"path", "message"}]}``), so the modal
  can show exactly which setting is wrong without dumping raw Pydantic text.
* ``PUT  /api/settings/location`` — repoint the app at a different config
  file (the modal's "config file location" setting, persisted in the
  ``.config-location`` sidecar). The target must exist and validate before
  the sidecar is written; an empty path clears the sidecar, returning to
  the default ``config.json``.
* ``POST /api/settings/drop_cache`` — empty the derived-data cache (graph
  snapshots, search results, paper hydration). Safe by construction: every
  entry can be refetched, and saved sessions live in a different store
  entirely.
* ``GET  /api/settings/models`` — the model ids the configured
  API key can see (the Models API, ``client.models.list()``), so the modal's
  agent-model fields offer a real dropdown instead of a free-typed string.
  Degrades to an empty list keyless or on any failure — the input stays a
  plain text field then.
* ``POST /api/settings/pick`` — open the **native** file chooser on the
  machine running the server and return the chosen path. Exists because a
  browser's own file picker never reveals an absolute path (sandboxing), and
  the sidecar needs one; the server and the browser are the same machine in
  this app's model, so the OS dialog is the honest picker.

The raw file JSON (not ``model_dump``) is what GET returns and PUT accepts,
so values round-trip byte-for-byte and the modal never has to understand
Pydantic's serialized forms.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
from pathlib import Path

from flask import Blueprint, current_app, request
from flask.typing import ResponseReturnValue
from pydantic import ValidationError

from .. import config as config_module
from ..config import EXAMPLE_CONFIG_PATH, Config
from ..storage import cache

bp = Blueprint("settings", __name__)

log = logging.getLogger(__name__)

#: How long the native file dialog may sit open before the request gives up.
_PICK_TIMEOUT_SECONDS = 300


def _ordered_like(reference: object, value: object) -> object:
    """The payload with its dict keys reordered to match the reference's.

    The canonical order is the example template's — "the template leads" —
    so every save writes the same stable structure regardless of what order
    the browser's JSON happened to carry. Keys the reference doesn't know
    are appended in the payload's own order; list items are each ordered
    like the reference list's first item (the agents list: same fields, many
    entries).

    Args:
        reference: The template value at this position (dict/list/leaf).
        value: The payload value to reorder.

    Returns:
        ``value`` with dicts recursively reordered; leaves unchanged.
    """
    if isinstance(reference, dict) and isinstance(value, dict):
        ordered = {
            key: _ordered_like(reference[key], value[key]) for key in reference if key in value
        }
        ordered.update({key: item for key, item in value.items() if key not in reference})
        return ordered
    if isinstance(reference, list) and isinstance(value, list) and reference:
        return [_ordered_like(reference[0], item) for item in value]
    return value


def _field_errors(error: ValidationError) -> dict:
    """A Pydantic error rendered for humans, not for a traceback.

    Pydantic's ``str(error)`` is one long blob — the header line, the dotted
    path, the message, a bracketed type/input dump, and a docs URL, per
    failure. In a modal footer that reads as noise. This keeps the two parts
    a person acts on: **where** (dotted path) and **what** (message).

    Args:
        error: The validation error raised while checking the posted config.

    Returns:
        ``{"error": <one-line summary>, "fields": [{"path", "message"}, ...]}``.
    """
    fields = [
        {
            "path": ".".join(str(part) for part in item["loc"]),
            "message": item["msg"],
        }
        for item in error.errors()
    ]
    count = len(fields)
    summary = f"{count} invalid setting{'' if count == 1 else 's'}"
    return {"error": summary, "fields": fields}


def _settings_payload() -> dict:
    """The GET shape: the active config file's path and parsed contents.

    Returns:
        ``{"path": <absolute path str>, "config": <parsed file JSON>}``.
    """
    path = config_module.active_config_path()
    if not path.exists():
        # A missing default config.json is created from the example (a fresh
        # checkout's first GET); load_settings owns that copy step.
        config_module.load_settings()
    return {"path": str(path), "config": json.loads(path.read_text(encoding="utf-8"))}


@bp.get("/api/settings")
def get_settings() -> ResponseReturnValue:
    """The active config file's location and contents.

    Returns:
        The settings payload (see ``_settings_payload``).
    """
    return _settings_payload()


@bp.put("/api/settings")
def put_settings() -> ResponseReturnValue:
    """Replace the active config file's contents and apply them live.

    Returns:
        The fresh settings payload on success; ``({"error": ...}, 400)`` when
        the body isn't a valid complete config — nothing is written then.
    """
    body = request.get_json(silent=True) or {}
    payload = body.get("config")
    if not isinstance(payload, dict):
        return {"error": "body must be {\"config\": {...}}"}, 400
    path = config_module.active_config_path()
    try:
        Config.model_validate(payload)
    except ValidationError as error:
        return _field_errors(error), 400
    template = json.loads(EXAMPLE_CONFIG_PATH.read_text(encoding="utf-8"))
    ordered = _ordered_like(template, payload)
    path.write_text(json.dumps(ordered, indent=2) + "\n", encoding="utf-8")
    config_module.reload_config()
    return _settings_payload()


@bp.put("/api/settings/location")
def put_settings_location() -> ResponseReturnValue:
    """Repoint the app at a different config file (or back to the default chain).

    Returns:
        The fresh settings payload on success; ``({"error": ...}, 400)`` when
        the named file is missing or invalid — the sidecar is untouched then.
    """
    body = request.get_json(silent=True) or {}
    raw_path = body.get("path")
    if not isinstance(raw_path, str):
        return {"error": "body must be {\"path\": \"...\"}"}, 400
    if not raw_path.strip():
        config_module.CONFIG_LOCATION_FILE.unlink(missing_ok=True)
        config_module.reload_config()
        return _settings_payload()
    target = Path(raw_path).expanduser()
    try:
        config_module.load_settings(target)  # must exist and validate first
    except FileNotFoundError:
        return {"error": f"{target} not found"}, 400
    except ValidationError as error:
        return _field_errors(error), 400
    config_module.CONFIG_LOCATION_FILE.write_text(str(target) + "\n", encoding="utf-8")
    config_module.reload_config()
    return _settings_payload()


#: Model ids offered for vendors with no listing API worth calling. Google
#: publishes a list endpoint but it needs the key and returns dozens of tuned
#: variants; OpenAI's is key-scoped and enormous. A short curated list of the
#: models actually worth running an agent on beats both, and the modal lets the
#: user type anything anyway — so a stale entry here costs nothing.
KNOWN_MODELS: dict[str, list[str]] = {
    "google": ["gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.5-flash-lite"],
    "openai": ["gpt-5", "gpt-5-mini", "gpt-4.1", "gpt-4.1-mini", "o4-mini"],
}


def _fetch_ollama_models(base_url: str) -> list[str]:
    """The model names a local Ollama server has actually pulled.

    The one vendor whose listing is both free and exactly right: it reports
    what is on this machine, so the modal can only offer models that will
    really run. ``/api/tags`` lives at the server root while the chat surface
    is under ``/v1``, hence the trim.

    Args:
        base_url: The configured Ollama endpoint, normally ending in ``/v1``.

    Returns:
        The installed model names (``"qwen3:8b"``, ...), server order.
    """
    import requests

    root = base_url.rstrip("/").removesuffix("/v1")
    response = requests.get(f"{root}/api/tags", timeout=3)
    response.raise_for_status()
    return [model["name"] for model in response.json().get("models", [])]


def _fetch_anthropic_models(api_key: str) -> list[str]:
    """The model ids the key can see, via the Anthropic Models API.

    Factored out of the route so tests can stub it — the suite is fully
    offline. Auto-paginates (the SDK's list iterator); the lazy import keeps
    the SDK off the app's import path.

    Args:
        api_key: The configured Anthropic API key.

    Returns:
        The available model ids, newest first (the API's own order).
    """
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    return [model.id for model in client.models.list()]


@bp.get("/api/settings/models")
def list_agent_models() -> ResponseReturnValue:
    """The model ids available, per configured vendor.

    Every listing path degrades to an empty list rather than an error: the
    modal's model field is free text with suggestions, so a vendor that can't
    be reached costs the user autocomplete, never the ability to configure.

    Returns:
        ``{"models": {"<vendor>": [...]}, "vendors": [...], "known": [...]}``.
        ``models`` holds one entry per *configured* vendor and ``vendors``
        names them; ``known`` names **every** vendor the factory can build,
        configured or not. That last one matters: the modal has to offer the
        free vendors to someone who has not set them up yet, so a list of only
        what is already working would hide exactly the options a newcomer
        needs to find.
    """
    vendors = config_module.config.llm.providers
    configured = vendors.configured_vendors()
    known = list(type(vendors).model_fields)
    models: dict[str, list[str]] = {}
    for vendor in configured:
        try:
            match vendor:
                case "anthropic":
                    models[vendor] = _fetch_anthropic_models(vendors.anthropic.api_key)
                case "ollama":
                    models[vendor] = _fetch_ollama_models(vendors.ollama.base_url)
                case _:
                    models[vendor] = KNOWN_MODELS.get(vendor, [])
        except Exception:
            log.warning("model listing failed for %s", vendor, exc_info=True)
            models[vendor] = []
    return {"models": models, "vendors": configured, "known": known}


def _native_pick() -> str | None:
    """Open the OS file chooser (JSON filter) and return the chosen path.

    One implementation per platform, each an external process so no GUI
    toolkit runs inside the server (tkinter on a Flask worker thread crashes
    on macOS): ``osascript`` on macOS, ``OpenFileDialog`` via PowerShell on
    Windows, ``zenity`` elsewhere. A cancelled dialog, a missing helper, or
    a timeout all mean "nothing chosen".

    Returns:
        The chosen file's absolute path, or None when nothing was chosen.
    """
    if sys.platform == "darwin":
        command = [
            "osascript",
            "-e",
            'POSIX path of (choose file of type {"public.json"} '
            'with prompt "Choose an Atlas config file")',
        ]
    elif sys.platform == "win32":
        command = [
            "powershell",
            "-NoProfile",
            "-Command",
            "Add-Type -AssemblyName System.Windows.Forms; "
            "$dialog = New-Object System.Windows.Forms.OpenFileDialog; "
            "$dialog.Filter = 'JSON files (*.json)|*.json'; "
            "if ($dialog.ShowDialog() -eq 'OK') { $dialog.FileName }",
        ]
    else:
        command = ["zenity", "--file-selection", "--file-filter=*.json"]
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=_PICK_TIMEOUT_SECONDS
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    chosen = result.stdout.strip()
    return chosen or None


@bp.post("/api/settings/pick")
def pick_settings_file() -> ResponseReturnValue:
    """Open the native file chooser and report what the user picked.

    Returns:
        ``{"path": <absolute path> | null}`` — null when the dialog was
        cancelled or no native chooser is available.
    """
    return {"path": _native_pick()}


@bp.post("/api/settings/drop_cache")
def drop_cache() -> ResponseReturnValue:
    """Empty the derived-data cache — graph snapshots, searches, hydration.

    Deliberately a settings action rather than a graph one, and deliberately
    separate from anything that deletes a *session*: everything in this table
    can be refetched, so the worst outcome is a slower next few minutes. A
    saved session is the only copy of something the reader made, and lives in
    its own store.

    The one thing it is genuinely for: a cache entry is keyed by what produced
    it, so a snapshot built under an older shape or a search cached before a
    prompt changed will sit there for its full day-long TTL. Dropping the
    cache is how you stop waiting for that.

    Returns:
        ``{"removed": <count>}`` — how many entries went, so the modal can
        report it rather than claiming success blankly.
    """
    removed = cache.clear()
    current_app.logger.info("cache dropped by request (%d entries)", removed)
    return {"removed": removed}
