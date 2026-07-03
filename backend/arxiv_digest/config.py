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

# --- Semantic Scholar (dynamic academic graph) -------------------------------
# arXiv Atlas connects to Semantic Scholar dynamically instead of storing a paper
# corpus locally — S2 is the same data backbone Connected Papers uses. The
# unauthenticated pool is tight (the single-paper GET 429s almost immediately, so
# we hydrate nodes through the far more lenient POST /paper/batch endpoint); set
# S2_API_KEY for reliable, higher-rate access:
# https://www.semanticscholar.org/product/api
S2_API_KEY = os.getenv("S2_API_KEY", "")
S2_GRAPH_URL = os.getenv("S2_GRAPH_URL", "https://api.semanticscholar.org/graph/v1")
S2_RECS_URL = os.getenv(
    "S2_RECS_URL", "https://api.semanticscholar.org/recommendations/v1"
)
S2_TIMEOUT = int(os.getenv("S2_TIMEOUT", "30"))

# How many neighbors of each kind to pull into a paper's graph neighborhood.
GRAPH_REF_LIMIT = int(os.getenv("ATLAS_GRAPH_REFS", "25"))
GRAPH_CITE_LIMIT = int(os.getenv("ATLAS_GRAPH_CITES", "25"))
GRAPH_SIMILAR_LIMIT = int(os.getenv("ATLAS_GRAPH_SIMILAR", "15"))
# The recommendation candidate pool: "all-cs" (all of CS, good for older seminal
# papers) or "recent". The default "recent" pool returns nothing for a 2017 seed.
GRAPH_RECS_POOL = os.getenv("ATLAS_GRAPH_RECS_POOL", "all-cs")
# Graph-snapshot cache TTL (seconds). S2 citation data changes slowly, so a day
# keeps repeat exploration snappy while respecting the rate limit.
GRAPH_CACHE_TTL = int(os.getenv("ATLAS_GRAPH_CACHE_TTL", "86400"))

# --- Claude backend (shared defaults for the AI teacher) ---------------------
# Backends:
#   "api"        — call the Anthropic API directly (pay-as-you-go, needs a key).
#   "claude_cli" — shell out to the `claude` CLI under your Claude Pro/Max
#                  subscription (no API billing; local-only).
# The AI teacher (below) inherits these as its default backend + fallback, but
# can override them via TEACHER_BACKEND / TEACHER_FALLBACK_BACKEND.
SUMMARY_BACKEND = os.getenv("SUMMARY_BACKEND", "api")
SUMMARY_FALLBACK_BACKEND = os.getenv("SUMMARY_FALLBACK_BACKEND", "claude_cli")

# -- api backend --
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# -- claude_cli backend --
# Path to the `claude` binary (or just "claude" if it's on PATH).
CLAUDE_CLI_PATH = os.getenv("CLAUDE_CLI_PATH", "claude")

# --- AI teacher (Phase 3) ----------------------------------------------------
# The narration/Q&A engine reuses the same dual-backend idea as summaries (API
# or the `claude` CLI under a Pro/Max subscription) but STREAMS its output so the
# frontend can reveal the lecture beat-by-beat and light up graph nodes in sync.
# Defaults inherit the summary backend choice; override independently if you want
# (e.g. cheap Haiku for bulk summaries, smarter Sonnet for narration).
TEACHER_BACKEND = os.getenv("TEACHER_BACKEND", SUMMARY_BACKEND)
TEACHER_FALLBACK_BACKEND = os.getenv("TEACHER_FALLBACK_BACKEND", SUMMARY_FALLBACK_BACKEND)
# Narration wants a stronger model than the bulk summarizer's Haiku.
TEACHER_MODEL = os.getenv("TEACHER_MODEL", "claude-sonnet-4-6")
TEACHER_CLI_MODEL = os.getenv("TEACHER_CLI_MODEL", "sonnet")
# Token/latency budgets for a single lecture or answer.
TEACHER_MAX_TOKENS = int(os.getenv("TEACHER_MAX_TOKENS", "3000"))
TEACHER_CLI_TIMEOUT = int(os.getenv("TEACHER_CLI_TIMEOUT", "180"))
# How many past turns of a Q&A session to keep as context (user+assistant pairs).
TEACHER_HISTORY_TURNS = int(os.getenv("TEACHER_HISTORY_TURNS", "8"))

# --- Server ------------------------------------------------------------------
FLASK_HOST = os.getenv("FLASK_HOST", "127.0.0.1")
FLASK_PORT = int(os.getenv("FLASK_PORT", "5000"))
# Verbose logging (DEBUG level, incl. the arXiv client's per-page requests).
DEBUG = os.getenv("ARXIV_DEBUG", "").lower() in ("1", "true", "yes")


def ensure_dirs() -> None:
    """Create the data directory if it doesn't exist yet."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
