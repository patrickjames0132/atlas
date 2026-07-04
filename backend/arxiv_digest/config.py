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
    """Read a filesystem path from the environment.

    Args:
        env_name: The environment variable to read.
        default: The path to use when the variable is unset.

    Returns:
        The configured path with ``~`` expanded, or ``default``.
    """
    raw = os.getenv(env_name)
    return Path(raw).expanduser() if raw else default


# --- Storage -----------------------------------------------------------------
DATA_DIR = _path("ARXIV_DATA_DIR", PROJECT_ROOT / "data")
DB_PATH = DATA_DIR / "digest.db"
# Bring-your-own sources (Phase 3d) live in their own DB — a persistent user
# library with a different lifecycle than the 1-day graph cache in digest.db.
SOURCES_DB_PATH = DATA_DIR / "sources.db"
# Saved sessions & workspaces (Phase 4) — a saved graph + chat transcript the
# user can reopen. Persistent, own lifecycle (never TTL-evicted), so its own DB
# apart from the ephemeral graph cache in digest.db.
SESSIONS_DB_PATH = DATA_DIR / "sessions.db"

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
# Minimum seconds between S2 requests. Even authenticated, the graph endpoints
# allow ~1 req/sec per key, so we self-throttle to keep bursts (graph build, the
# Phase 3e backfill, agent expansion) from tripping 429s — cheaper than eating a
# 429 + exponential backoff. Set 0 to disable.
S2_MIN_INTERVAL = float(os.getenv("S2_MIN_INTERVAL", "1.1"))

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

# --- Agentic teacher (Phase 3b) ----------------------------------------------
# The Q&A agent can pull full paper text into context via tool use, grounding its
# answer in what it actually reads. Hard guardrails keep it from wandering: caps
# on total tool-loop steps and on how many papers it may read (full vs summary),
# plus a wall-clock ceiling. Agentic Q&A needs the Anthropic API (tool use); with
# the claude CLI backend, Q&A falls back to the non-agentic grounded answer.
AGENT_MODEL = os.getenv("AGENT_MODEL", TEACHER_MODEL)
AGENT_MAX_STEPS = int(os.getenv("AGENT_MAX_STEPS", "12"))
AGENT_MAX_FULL_READS = int(os.getenv("AGENT_MAX_FULL_READS", "4"))
AGENT_MAX_SUMMARY_READS = int(os.getenv("AGENT_MAX_SUMMARY_READS", "12"))
AGENT_WALLCLOCK = int(os.getenv("AGENT_WALLCLOCK", "90"))
# Phase 3b.2 — expand_node lets the agent pull papers not yet on the graph (one
# hop via references/citations/similar). AGENT_MAX_HOPS caps how many expand
# calls a single question may make; AGENT_EXPAND_LIMIT caps how many neighbors
# come back per hop (kept small — these land in the tool result, not just the
# graph). A visited (paper, relation) set in teacher.py kills repeat traversal.
AGENT_MAX_HOPS = int(os.getenv("AGENT_MAX_HOPS", "5"))
AGENT_EXPAND_LIMIT = int(os.getenv("AGENT_EXPAND_LIMIT", "8"))
# Phase 3c.2 — search_papers runs an UNGROUNDED free-text search against S2's
# paper-search endpoint (optional year filter) to reach recent / topical work
# that citation & similarity hops can't (those are lineage- and embedding-biased:
# a 2026 paper citing a 2017 seed has no citations of its own yet). It gets its
# OWN budget, separate from AGENT_MAX_HOPS, because open-ended search wanders more
# freely than a graph hop. AGENT_SEARCH_LIMIT caps results per search.
AGENT_MAX_SEARCHES = int(os.getenv("AGENT_MAX_SEARCHES", "3"))
AGENT_SEARCH_LIMIT = int(os.getenv("AGENT_SEARCH_LIMIT", "8"))
# Max characters of full text loaded per paper read (keeps the context bounded).
FULLTEXT_MAX_CHARS = int(os.getenv("FULLTEXT_MAX_CHARS", "8000"))

# Phase 3e — "How we got here" time travel. Before the history lecture narrates,
# walk BACKWARD through references to surface a field's older roots, so the story
# starts at the beginning even when the seed is modern. Bounded so it doesn't
# hammer the rate limit: HOPS backward levels, PER_HOP most-cited ancestors added
# each level, FRONTIER oldest of those carried into the next hop, and LOOKBACK
# years back from the seed we aim to reach before stopping early.
LECTURE_HISTORY_HOPS = int(os.getenv("LECTURE_HISTORY_HOPS", "3"))
LECTURE_HISTORY_PER_HOP = int(os.getenv("LECTURE_HISTORY_PER_HOP", "6"))
LECTURE_HISTORY_FRONTIER = int(os.getenv("LECTURE_HISTORY_FRONTIER", "2"))
LECTURE_HISTORY_LOOKBACK = int(os.getenv("LECTURE_HISTORY_LOOKBACK", "40"))

# --- Bring-your-own sources (Phase 3d) ---------------------------------------
# Uploaded books/PDFs and fetched web pages are chunked, embedded LOCALLY (no
# API, no key — the text never leaves the machine, which matters for copyrighted
# books) and stored in a sqlite-vec index the teacher can semantic-search. All of
# it degrades gracefully: if the embedding model can't load, `available()` is
# False and ingestion/search report unavailable rather than crashing.
SEMANTIC_ENABLED = os.getenv("ARXIV_SEMANTIC", "1").lower() not in ("0", "false", "no")
EMBED_MODEL = os.getenv("ARXIV_EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
EMBED_DIM = int(os.getenv("ARXIV_EMBED_DIM", "384"))
# Optional instruction prepended to SEARCH QUERIES only (not stored passages).
# Asymmetric-retrieval models want one, e.g. BAAI/bge-small-en-v1.5:
# ARXIV_EMBED_QUERY_PREFIX="Represent this sentence for searching relevant passages: "
# Empty for symmetric models like all-MiniLM-L6-v2 (the default).
EMBED_QUERY_PREFIX = os.getenv("ARXIV_EMBED_QUERY_PREFIX", "")
# Chunking is char-based (cheap, model-agnostic). all-MiniLM-L6-v2 truncates at
# ~256 word-pieces, so keep a chunk under ~1000 chars (~250 tokens) or its tail
# is embedded into nothing. Overlap preserves context across chunk boundaries.
SOURCE_CHUNK_CHARS = int(os.getenv("SOURCE_CHUNK_CHARS", "900"))
SOURCE_CHUNK_OVERLAP = int(os.getenv("SOURCE_CHUNK_OVERLAP", "150"))
# How many passages a single source search returns, and how many such searches
# the agent may run per question (its own budget, separate from S2 search).
SOURCE_SEARCH_K = int(os.getenv("SOURCE_SEARCH_K", "6"))
AGENT_MAX_SOURCE_SEARCHES = int(os.getenv("AGENT_MAX_SOURCE_SEARCHES", "5"))
# Offline library chat (Phase 3d): a graph-free RAG chat straight over the local
# library. Retrieve a few more passages than a single agent search, since this is
# the answer's only grounding (no paper reading, no follow-up searches).
SOURCES_CHAT_K = int(os.getenv("SOURCES_CHAT_K", "8"))

# --- Server ------------------------------------------------------------------
FLASK_HOST = os.getenv("FLASK_HOST", "127.0.0.1")
FLASK_PORT = int(os.getenv("FLASK_PORT", "5000"))
# Verbose logging (DEBUG level, incl. the arXiv client's per-page requests).
DEBUG = os.getenv("ARXIV_DEBUG", "").lower() in ("1", "true", "yes")


def ensure_dirs() -> None:
    """Create the data directory if it doesn't exist yet.

    Called by every storage module before opening its database, so a fresh
    checkout works without any setup step.

    Returns:
        None.

    Raises:
        OSError: When the directory can't be created (permissions, etc.).
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
