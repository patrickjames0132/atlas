"""Central configuration, loaded from environment / .env file.

Everything tunable lives here so you never have to hunt through the code to
change a path, a model, or the arXiv categories you follow.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Load a .env file sitting at the project root (two levels up from this file:
# backend/arxiv_digest/config.py -> arxiv-digest/).
PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")


def _path(env_name: str, default: Path) -> Path:
    raw = os.getenv(env_name)
    return Path(raw).expanduser() if raw else default


# --- Storage -----------------------------------------------------------------
DATA_DIR = _path("ARXIV_DATA_DIR", PROJECT_ROOT / "data")
DB_PATH = DATA_DIR / "digest.db"

# --- arXiv -------------------------------------------------------------------
# The subject categories you follow — your "subscription". Comma-separated in
# the environment; see https://arxiv.org/category_taxonomy for the full list.
ARXIV_CATEGORIES = [
    c.strip()
    for c in os.getenv("ARXIV_CATEGORIES", "cs.LG,cs.AI,cs.CL,cs.CV").split(",")
    if c.strip()
]

# Upper bound on how many papers to pull per run (safety valve).
ARXIV_MAX_RESULTS = int(os.getenv("ARXIV_MAX_RESULTS", "100"))

# --- Summaries ---------------------------------------------------------------
# Backends:
#   "api"        — call the Anthropic API directly (pay-as-you-go, needs a key).
#   "claude_cli" — shell out to the `claude` CLI under your Claude Pro/Max
#                  subscription (no API billing; local-only).
# The primary backend is tried first; if it fails (e.g. API credits exhausted),
# the fallback backend takes over for the rest of the run. Set the fallback to
# an empty string to disable fallback.
SUMMARY_BACKEND = os.getenv("SUMMARY_BACKEND", "api")
SUMMARY_FALLBACK_BACKEND = os.getenv("SUMMARY_FALLBACK_BACKEND", "claude_cli")

# Roughly how long each AI summary should be.
SUMMARY_MAX_WORDS = int(os.getenv("SUMMARY_MAX_WORDS", "60"))

# -- api backend --
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
# Haiku 4.5 is cheap + fast for summarizing short abstracts in bulk.
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5")

# -- claude_cli backend --
# Path to the `claude` binary (or just "claude" if it's on PATH).
CLAUDE_CLI_PATH = os.getenv("CLAUDE_CLI_PATH", "claude")
# Model alias for the CLI; "haiku" keeps the fallback cheap/fast too.
CLAUDE_CLI_MODEL = os.getenv("CLAUDE_CLI_MODEL", "haiku")
# Per-paper timeout (seconds) for a headless CLI call.
CLAUDE_CLI_TIMEOUT = int(os.getenv("CLAUDE_CLI_TIMEOUT", "120"))

# --- Server ------------------------------------------------------------------
FLASK_HOST = os.getenv("FLASK_HOST", "127.0.0.1")
FLASK_PORT = int(os.getenv("FLASK_PORT", "5000"))


def ensure_dirs() -> None:
    """Create the data directory if it doesn't exist yet."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
