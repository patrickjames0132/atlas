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

# --- Semantic search (embeddings) --------------------------------------------
# The sentence-transformers model used to embed papers for semantic/hybrid
# search. EMBED_DIM MUST match the model's output dimension (all-MiniLM-L6-v2 →
# 384); if you swap to a model with a different dimension, set both and re-embed
# (`python backend/run.py embed --rebuild`). Set ARXIV_SEMANTIC=0 to turn the
# whole embedding layer off (search then stays lexical-only).
EMBED_MODEL = os.getenv("ARXIV_EMBED_MODEL", "all-MiniLM-L6-v2")
EMBED_DIM = int(os.getenv("ARXIV_EMBED_DIM", "384"))
SEMANTIC_ENABLED = os.getenv("ARXIV_SEMANTIC", "1").lower() not in ("0", "false", "no")
# Reciprocal-rank-fusion constant for blending lexical + semantic result lists.
# Higher = flatter weighting across ranks; 60 is the common default.
RRF_K = int(os.getenv("ARXIV_RRF_K", "60"))

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
# Verbose logging (DEBUG level, incl. the arXiv client's per-page requests).
DEBUG = os.getenv("ARXIV_DEBUG", "").lower() in ("1", "true", "yes")


def ensure_dirs() -> None:
    """Create the data directory if it doesn't exist yet."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
