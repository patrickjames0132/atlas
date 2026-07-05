"""Central configuration for arXiv Atlas, loaded from config.json.

Every tunable — paths, API keys, model names, agent definitions — lives in
one JSON file at the repo root, parsed by Pydantic into the nested
``settings`` object below. There are **no defaults**: config.json must spell
out every value (copy ``config.example.json`` to start), and any mistake —
an unknown key, a negative limit, a misspelled literal — fails loudly at
import time instead of silently becoming a default. Each field carries its
own ``description`` explaining what it does and why its example value is
what it is; for cross-cutting rationale (why a config choice affects several
fields at once) see docs/configuration.md.

    from arxiv_digest.config import settings
    settings.llm.providers.anthropic.api_key
    settings.llm.agents[0].model  # "anthropic:claude-sonnet-4-6"

The models are mutable on purpose: the test suite's autouse ``_isolate``
fixture points ``settings.storage.data_dir`` at a per-test temp directory
and zeroes ``settings.s2.min_interval`` so tests never touch real data or
sleep. Keep field lookups late (``settings.x.y`` at call time, not a
module-level ``from ... import y``) so those overrides are seen.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    NonNegativeFloat,
    NonNegativeInt,
    PositiveInt,
    field_validator,
    model_validator,
)

# This file lives at src/arxiv_digest/config.py; the repo root is 3 levels up.
PROJECT_ROOT = Path(__file__).resolve().parents[2]


class ConfigModel(BaseModel):
    """Base for every settings group: unknown keys in config.json are typos,
    so reject them instead of ignoring them."""

    model_config = ConfigDict(extra="forbid")


class StorageConfig(ConfigModel):
    """Where the app keeps its three SQLite databases.

    Three separate files because three lifecycles: the graph cache is
    disposable (short TTL), the sources collection is expensive to rebuild
    (re-embedding your PDFs), and saved sessions are precious (never
    auto-evicted). Clearing one can never destroy another.
    """

    data_dir: Path = Field(
        description="Directory holding all three SQLite databases. A relative "
        "path is anchored to the repo root, not the process's cwd."
    )

    @field_validator("data_dir")
    @classmethod
    def _anchor_to_repo_root(cls, v: Path) -> Path:
        """A relative path in config.json means "relative to the repo root"."""
        v = v.expanduser()
        return v if v.is_absolute() else PROJECT_ROOT / v

    # The DB paths derive from data_dir, so overriding that one field (as the
    # tests do) relocates all storage at once.

    @property
    def digest_db(self) -> Path:
        """The ephemeral cache: graph snapshots, figures, code links."""
        return self.data_dir / "digest.db"

    @property
    def sources_db(self) -> Path:
        """The bring-your-own sources: chunks + local embeddings."""
        return self.data_dir / "sources.db"

    @property
    def sessions_db(self) -> Path:
        """Saved workspaces: a graph + its chat transcript, reopenable later."""
        return self.data_dir / "sessions.db"

    def ensure_dirs(self) -> None:
        """Create ``data_dir`` if missing.

        Called before every database open, so a fresh checkout works without
        any setup step.
        """
        self.data_dir.mkdir(parents=True, exist_ok=True)


class SemanticScholarConfig(ConfigModel):
    """Connection settings for the Semantic Scholar API — Atlas's academic-
    graph backbone.

    Atlas stores no paper corpus; it asks S2 on demand (the same data
    backbone Connected Papers uses). See docs/configuration.md for why
    ``min_interval`` and unauthenticated rate limits matter here.
    """

    api_key: str = Field(
        description="Free key from https://www.semanticscholar.org/product/api. "
        "Empty string works (keyless) but is rate-limited much harder."
    )
    graph_url: str = Field(description="Base URL of the Academic Graph API.")
    recs_url: str = Field(description="Base URL of the Recommendations API.")
    timeout: PositiveInt = Field(description="HTTP timeout in seconds for S2 requests.")
    min_interval: NonNegativeFloat = Field(
        description="Minimum seconds between S2 requests (self-imposed throttle, "
        "since even authenticated callers get ~1 req/sec). 0 disables it — tests do."
    )


class GraphConfig(ConfigModel):
    """How big a neighborhood one seed paper pulls onto the canvas.

    See docs/configuration.md for the node-count math behind the example
    limits and why ``recs_pool`` must stay "all-cs".
    """

    ref_limit: PositiveInt = Field(description="Max references (papers it cites) to pull in.")
    cite_limit: PositiveInt = Field(description="Max citations (papers citing it) to pull in.")
    similar_limit: PositiveInt = Field(
        description="Max SPECTER2-embedding neighbors to pull in as 'similar' nodes."
    )
    recs_pool: Literal["all-cs", "recent"] = Field(
        description="Candidate pool for similar-paper recommendations. 'recent' "
        "returns nothing for older seeds — keep 'all-cs' unless you only explore "
        "brand-new papers."
    )
    cache_ttl: NonNegativeInt = Field(
        description="Seconds a graph snapshot stays cached before rebuilding. "
        "Citation data changes slowly, so a day keeps repeat exploration instant."
    )


class AnthropicConfig(ConfigModel):
    """Credentials for the Anthropic API.

    Mirrors ``pydantic_ai.providers.anthropic.AnthropicProvider(api_key=...)``
    directly — this value is passed straight through when an agent factory
    builds a real PydanticAI provider, rather than relying on PydanticAI's
    own environment-variable fallback.
    """

    api_key: str = Field(description="Key from https://console.anthropic.com.")


class ProvidersConfig(ConfigModel):
    """Backend LLM providers this app can reach, keyed by vendor name.

    One sub-object per vendor — mirrors PydanticAI's own per-vendor
    ``Provider`` classes (``AnthropicProvider``, ``OpenAIProvider``, ...).
    Only Anthropic is wired up today (that's what we're testing against),
    but adding a vendor later is purely additive: a new field here, no
    redesign. Every ``AgentConfig.model``'s ``"<provider>:<model>"`` prefix
    must name a vendor configured here (``LLMConfig`` validates this).
    """

    anthropic: AnthropicConfig


class AgentConfig(ConfigModel):
    """One configured Claude agent, built (eventually) into a real
    ``pydantic_ai.Agent``.

    Today there's a single entry — the teaching assistant — but ``agents``
    is a list because more are planned (see OnePager.md), potentially on
    different providers. ``extras`` is a deliberate escape hatch for
    settings that don't have a permanent home yet (e.g. tool-call budgets,
    retrieval knobs): stash them there while building, then promote
    anything that earns its keep to a proper typed field once its shape has
    settled.
    """

    id: str = Field(
        min_length=1, description="Unique key other code uses to look this agent up."
    )
    model: str = Field(
        description="Which model this agent runs, as PydanticAI's own "
        "'<provider>:<model_name>' string (e.g. 'anthropic:claude-sonnet-4-6'). The "
        "prefix must name a vendor configured under `providers`."
    )
    system_prompt: str = Field(
        description="This agent's system prompt. Empty is valid — not written yet."
    )
    tools: list[str] = Field(
        description="Names of tools this agent may call. Empty means no tool use."
    )
    extras: dict[str, Any] = Field(
        description="Free-form bag for agent-specific settings not yet promoted to "
        "a first-class field."
    )

    @field_validator("model")
    @classmethod
    def _model_has_provider_prefix(cls, v: str) -> str:
        """Catch a bare model name early — PydanticAI needs the vendor prefix."""
        if ":" not in v:
            raise ValueError(
                f"model {v!r} must be '<provider>:<model_name>', e.g. "
                "'anthropic:claude-sonnet-4-6'"
            )
        return v

    @property
    def provider(self) -> str:
        """The vendor name parsed from ``model``'s '<provider>:<model_name>' prefix."""
        return self.model.split(":", 1)[0]


class LLMConfig(ConfigModel):
    """Everything about talking to LLMs: which backend vendors we can reach
    (``providers``) and which agents are configured to use them (``agents``).

    Grouped together because an agent is meaningless without a provider to
    run it on, and this is a different concern from ``sources.embedding`` —
    that's a local embedding model for search, not a chat/tool-use LLM.
    """

    providers: ProvidersConfig
    agents: list[AgentConfig] = Field(min_length=1, description="Every agent the app can run.")

    @model_validator(mode="after")
    def _agent_ids_are_unique(self) -> LLMConfig:
        """Other code will look agents up by id — a duplicate would be ambiguous."""
        ids = [a.id for a in self.agents]
        dupes = {i for i in ids if ids.count(i) > 1}
        if dupes:
            raise ValueError(f"duplicate agent id(s): {sorted(dupes)}")
        return self

    @model_validator(mode="after")
    def _agent_providers_are_configured(self) -> LLMConfig:
        """An agent naming an unconfigured vendor would fail at first request,
        not at load — catch it here instead."""
        configured = ProvidersConfig.model_fields.keys()
        for agent in self.agents:
            if agent.provider not in configured:
                raise ValueError(
                    f"agent {agent.id!r} wants provider {agent.provider!r}, but only "
                    f"{sorted(configured)} are configured under `providers`"
                )
        return self


class Embedding(ConfigModel):
    """The local embedding model used to make uploaded sources searchable."""

    model: str = Field(
        min_length=1,
        description="sentence-transformers model id. Changing this requires "
        "re-ingesting existing sources — their vectors were made by the old model.",
    )
    dim: PositiveInt = Field(description="Embedding vector size. Must match the model.")
    query_prefix: str = Field(
        description="Instruction prepended to SEARCH QUERIES only (never to stored "
        "passages). Asymmetric-retrieval models want one; symmetric models like the "
        "default MiniLM leave it empty."
    )


class Chunking(ConfigModel):
    """How uploaded text is split into embeddable, searchable passages."""

    chars: PositiveInt = Field(
        description="Characters per chunk. Character-based chunking is cheap and "
        "model-agnostic, but must respect the embedding model's token limit — "
        "MiniLM truncates at ~256 word-pieces (~1000 chars), so anything longer has "
        "its tail embedded into nothing, i.e. unsearchable text."
    )
    overlap: NonNegativeInt = Field(
        description="Characters shared between consecutive chunks, so a sentence "
        "straddling a boundary stays findable from either side. Must be smaller "
        "than 'chars'."
    )

    @model_validator(mode="after")
    def _overlap_fits_inside_chunk(self) -> Chunking:
        """An overlap as big as the chunk would make chunking loop forever."""
        if self.overlap >= self.chars:
            raise ValueError(f"overlap ({self.overlap}) must be smaller than chars ({self.chars})")
        return self


class Retrieval(ConfigModel):
    """Search over the local sources: hybrid semantic + lexical retrieval.

    Semantic ranking (vector KNN) is fused with lexical ranking (FTS5 BM25)
    via Reciprocal Rank Fusion, so exact terms and proper nouns the embedder
    blurs together still surface.
    """

    search_k: PositiveInt = Field(
        description="Passages returned by a single search — used by both the "
        "teaching assistant's search_sources tool and the graph-free sources chat."
    )
    hybrid: bool = Field(
        description="Fuse semantic + lexical ranking via RRF. When false, falls "
        "back to pure vector search; lexical is skipped automatically if the "
        "SQLite build lacks FTS5."
    )
    rrf_k: PositiveInt = Field(
        description="RRF rank-damping constant. 60 is the standard value from the "
        "Reciprocal Rank Fusion paper."
    )
    chat_k: PositiveInt = Field(
        description="Passages retrieved for the graph-free sources chat — higher "
        "than search_k because it's the answer's only grounding (no paper reading, "
        "no follow-up searches)."
    )


class SourcesConfig(ConfigModel):
    """Bring-your-own sources: local ingestion, embedding, and retrieval.

    Named ``sources`` (not ``library``) to match what this feature is
    actually called everywhere else in the app — the Sources drawer, the
    `/api/sources` routes — and to avoid the ambiguity with Python packages
    that "library" invites.

    Uploaded PDFs and fetched web pages are chunked and embedded LOCALLY —
    no API, no key; the text never leaves the machine (which matters for
    copyrighted books). If the embedding model can't load, everything
    degrades gracefully: ingestion and search report "unavailable" instead
    of crashing the app.
    """

    semantic_enabled: bool = Field(
        description="Master switch for the whole bring-your-own-sources feature."
    )
    embedding: Embedding
    chunking: Chunking
    retrieval: Retrieval


class ServerConfig(ConfigModel):
    """Where the Flask app listens, and how loudly it logs."""

    host: str = Field(min_length=1, description="Interface Flask binds to.")
    port: int = Field(ge=1, le=65535, description="TCP port Flask listens on.")
    debug: bool = Field(
        description="Verbose (DEBUG-level) logging, including the arXiv client's "
        "per-page requests."
    )


class Config(ConfigModel):
    """All configuration, grouped by the part of the app that consumes it."""

    storage: StorageConfig
    s2: SemanticScholarConfig
    graph: GraphConfig
    sources: SourcesConfig
    server: ServerConfig
    llm: LLMConfig


CONFIG_PATH = PROJECT_ROOT / "config.json"


def load_settings(path: Path = CONFIG_PATH) -> Config:
    """Parse and validate a config file into a Settings object."""
    try:
        raw = path.read_text()
    except FileNotFoundError:
        raise FileNotFoundError(
            f"{path} not found — copy config.example.json to config.json "
            "and fill in your values."
        ) from None
    return Config.model_validate_json(raw)


settings = load_settings()
