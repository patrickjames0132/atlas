"""Central configuration for arXiv Atlas, loaded from config.json.

Every tunable — paths, API keys, model names, agent definitions — lives in
one JSON file at the repo root, parsed by Pydantic into the nested
``config`` object below. There are **no defaults**: config.json must spell
out every value (copy ``config.example.json`` to start), and any mistake —
an unknown key, a negative limit, a misspelled literal — fails loudly at
import time instead of silently becoming a default. Each field carries its
own ``description`` explaining what it does and why its example value is
what it is; for cross-cutting rationale (why a config choice affects several
fields at once) see docs/configuration.md.

    from atlas.config import config
    config.llm.providers.anthropic.api_key
    config.llm.agents[0].model  # "anthropic:claude-sonnet-4-6"

The models are mutable on purpose: the test suite's autouse ``_isolate``
fixture points ``config.storage.data_dir`` at a per-test temp directory
and zeroes ``config.providers.s2.min_interval`` so tests never touch real data or
sleep. Keep field lookups late (``config.x.y`` at call time, not a
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

# This file lives at src/atlas/config.py; the repo root is 3 levels up.
PROJECT_ROOT = Path(__file__).resolve().parents[2]


class ConfigModel(BaseModel):
    """Base for every settings group: unknown keys in config.json are typos,
    so reject them instead of ignoring them.
    """

    model_config = ConfigDict(extra="forbid")


class StorageConfig(ConfigModel):
    """Where the app keeps its three SQLite databases, and the S2 corpus.

    Three separate DB files because three lifecycles: the graph cache is
    disposable (short TTL), the sources collection is expensive to rebuild
    (re-embedding your PDFs), and saved sessions are precious (never
    auto-evicted). Clearing one can never destroy another.
    """

    data_dir: Path = Field(
        description="Directory holding all three SQLite databases. A relative "
        "path is anchored to the repo root, not the process's cwd."
    )
    s2_corpus: Path | None = Field(
        default=None,
        description="Root of the offline S2 citations corpus — the downloaded .gz "
        "shards, the ingested Parquet, and the CURRENT pointer all live under this "
        "one directory, in per-release subtrees (releases/<id>/{raw,parquet}). "
        "Null turns the corpus off (the s2 provider falls back to the live citation "
        "endpoint). Kept outside the repo and gitignored — hundreds of GB; the "
        "shards half is deletable after a successful ingest. See "
        "integrations/semantic_scholar/corpus/README.md.",
    )

    @field_validator("data_dir", "s2_corpus")
    @classmethod
    def _anchor_to_repo_root(cls, path: Path | None) -> Path | None:
        """A relative path in config.json means "relative to the repo root".

        An absolute path (the corpus's common case — its own drive) passes
        untouched; None stays None (the corpus is simply not configured).
        """
        if path is None:
            return None
        path = path.expanduser()
        return path if path.is_absolute() else PROJECT_ROOT / path

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


class OpenAlexConfig(ConfigModel):
    """Connection settings for the OpenAlex API — the hybrid citation backbone.

    Since v4.0.0 OpenAlex supplies the **citation** relation (landmark + latest),
    because sorted, year-banded ``cites:`` queries return a seed's most-cited
    citers directly — no newest-first recency bias and no reference-list mining
    (which S2 needed, now retired). S2 still owns references, the *Similar*
    relation, and TL;DRs/details; the two are matched by DOI / arXiv id. See
    ``integrations/openalex/README.md`` and the OpenAlex spike in ``OnePager.md``.

    Pricing is metered (verified live 2026-07-09): a free API key grants $1/day,
    keyless (``mailto`` polite pool) $0.10/day; **id/DOI lookups are free**,
    search/filter ~$1 per 1,000 calls. A per-seed citation build is a handful of
    filter calls, so the free tier is ample — but keep the throttle polite.
    """

    api_key: str = Field(
        description="Free key from https://openalex.org/settings/api — grants "
        "$1/day of metered usage. Empty string works (keyless polite pool, "
        "$0.10/day). Sent as the ``api_key`` query param when set."
    )
    mailto: str = Field(
        description="Contact email for OpenAlex's 'polite pool' (sent as the "
        "``mailto`` query param) — faster, more reliable service and the courteous "
        "default even keyless. Empty string omits it."
    )
    base_url: str = Field(description="Base URL of the OpenAlex API (one unified endpoint).")
    timeout: PositiveInt = Field(description="HTTP timeout in seconds for OpenAlex requests.")
    min_interval: NonNegativeFloat = Field(
        description="Minimum seconds between OpenAlex requests (self-imposed throttle; "
        "OpenAlex allows ~10 req/sec, so this stays well under). 0 disables it — tests do."
    )


class ProvidersConfig(ConfigModel):
    """The external data APIs the graph is built from, one sub-object per
    service — plus which of them is the default.

    Groups the academic-data backbones (Semantic Scholar, OpenAlex) the same
    way ``llm.providers`` groups the LLM vendors: connection settings — keys,
    URLs, timeouts, throttles — live together, per service. Adding a data
    source later is purely additive: a new field here, no redesign.
    ``default_provider`` lives here beside the services it chooses between,
    not under ``graph``.
    """

    s2: SemanticScholarConfig
    openalex: OpenAlexConfig
    default_provider: Literal["s2", "openalex"] = Field(
        description="Which academic-data backend a new graph is built from when the "
        "request doesn't name one — the initial state of the header provider selector. "
        "Since v5.0.0 a graph is built from ONE provider end-to-end (no cross-source "
        "hybrid): 's2' (Semantic Scholar) is the safe default — the seed's own citation "
        "count is complete and every relation resolves, though its live citation endpoint "
        "is newest-first, so landmark citers are recency-biased until the offline S2 "
        "citations corpus lands. 'openalex' returns server-sorted landmark citers directly, "
        "but reads the seed from OpenAlex's own record (a famous published paper resolves "
        "to its lower-cited arXiv-preprint stub). The user overrides this per graph from "
        "the header dropdown."
    )


class GraphConfig(ConfigModel):
    """The graph build's one remaining knob — the snapshot cache.

    Deliberately minimal: the app **sizes every relation itself** (the
    adaptive rules in ``services/graph/budget.py`` and ``bands.py``, with the
    shared guards and band-shape defaults in ``integrations/caps.py``), so
    there are no per-relation count caps, no adaptive on/off toggles, and no
    band-shape fields here — all deleted as knobs nobody turned. The default
    provider lives with the providers (``providers.default_provider``). See
    docs/configuration.md.
    """

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


class LLMProvidersConfig(ConfigModel):
    """Backend LLM providers this app can reach, keyed by vendor name.

    One sub-object per vendor — mirrors PydanticAI's own per-vendor
    ``Provider`` classes (``AnthropicProvider``, ``OpenAIProvider``, ...).
    Only Anthropic is wired up today (that's what we're testing against),
    but adding a vendor later is purely additive: a new field here, no
    redesign. Every ``AgentConfig.model``'s ``"<provider>:<model>"`` prefix
    must name a vendor configured here (``LLMConfig`` validates this).
    (Distinct from the top-level ``providers`` group, which holds the
    external *data* APIs — S2, OpenAlex.)
    """

    anthropic: AnthropicConfig


class AgentConfig(ConfigModel):
    """One configured agent: which model it runs, plus its tunables.

    One entry per sub-agent package under ``agents/`` (they land one at a
    time — see ``src/atlas/agents/README.md``), looked up by ``id``.
    Deliberately *thin*: an agent's words (system prompt, skills) and its
    tool functions are code, defined in its own package's ``config.py`` and
    ``tools.py`` — this entry supplies only what an operator tunes: the
    model and the knobs. ``extras`` is the escape hatch for knobs that
    don't have a permanent typed home yet (e.g. tool-call budgets): stash
    them there while building, then promote anything that earns its keep to
    a proper typed field once its shape has settled.
    """

    id: str = Field(
        min_length=1, description="Unique key other code uses to look this agent up."
    )
    model: str = Field(
        description="Which model this agent runs, as PydanticAI's own "
        "'<provider>:<model_name>' string (e.g. 'anthropic:claude-sonnet-4-6'). The "
        "prefix must name a vendor configured under `providers`."
    )
    extras: dict[str, Any] = Field(
        description="Free-form bag for agent-specific settings not yet promoted to "
        "a first-class field."
    )

    @field_validator("model")
    @classmethod
    def _model_has_provider_prefix(cls, model: str) -> str:
        """Catch a bare model name early — PydanticAI needs the vendor prefix."""
        if ":" not in model:
            raise ValueError(
                f"model {model!r} must be '<provider>:<model_name>', e.g. "
                "'anthropic:claude-sonnet-4-6'"
            )
        return model

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

    providers: LLMProvidersConfig
    agents: list[AgentConfig] = Field(min_length=1, description="Every agent the app can run.")

    @model_validator(mode="after")
    def _agent_ids_are_unique(self) -> LLMConfig:
        """Other code will look agents up by id — a duplicate would be ambiguous."""
        ids = [agent.id for agent in self.agents]
        dupes = {agent_id for agent_id in ids if ids.count(agent_id) > 1}
        if dupes:
            raise ValueError(f"duplicate agent id(s): {sorted(dupes)}")
        return self

    @model_validator(mode="after")
    def _agent_providers_are_configured(self) -> LLMConfig:
        """An agent naming an unconfigured vendor would fail at first request,
        not at load — catch it here instead.
        """
        configured = LLMProvidersConfig.model_fields.keys()
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
    device: str = Field(
        default="auto",
        description="Torch device the embedder runs on. 'auto' delegates to "
        "sentence-transformers, which picks the best available (cuda on a Windows/Linux "
        "box with a CUDA torch build, mps on Apple silicon, else cpu). Set an explicit "
        "torch device string ('cpu', 'cuda', 'cuda:1', 'mps') to override — a bad or "
        "unavailable device falls back to cpu rather than breaking search.",
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


class MiningCaps(ConfigModel):
    """How much of one PDF the float miner will look at — one set of caps per
    corpus, because limits tuned for papers were silent data loss on books
    (docs/bugs.md, the Sarsa(λ) incident).
    """

    max_floats: PositiveInt = Field(
        description="Stop mining after this many figures/tables/algorithms."
    )
    max_pages: PositiveInt = Field(description="Scan at most this many pages.")


class PdfConfig(ConfigModel):
    """Fetching and mining open-access PDFs for papers with no ar5iv render.

    Journal papers (and the rare arXiv paper ar5iv can't convert) have no
    HTML render to read text/figures from; when a provider reports an
    open-access PDF URL, Atlas downloads it once into a small on-disk cache
    and mines it with pymupdf — full text for the researcher's ``read_paper``
    and caption-anchored figures/tables/algorithms for the detail panel and
    ``show_figure``. Everything degrades gracefully: a paywalled, oversized,
    or unparseable PDF simply reports "unavailable".
    """

    max_bytes: PositiveInt = Field(
        description="Largest PDF the fetcher will download, in bytes. Oversized "
        "files abort mid-stream and report unavailable — 25 MB covers virtually "
        "every paper while keeping a hostile/mislabeled URL from filling the disk."
    )
    timeout: PositiveInt = Field(
        description="HTTP timeout in seconds for one PDF download. PDFs are much "
        "bigger than API responses, so this is separate from (and longer than) the "
        "provider timeouts."
    )
    cache_files: PositiveInt = Field(
        description="Maximum PDFs kept in the on-disk cache (data_dir/oa_pdfs); "
        "the least-recently-used files beyond it are pruned after each download. "
        "At ~2 MB per typical paper, 200 files ≈ 400 MB."
    )
    research_papers: MiningCaps = Field(
        description="Mining caps for open-access PAPER PDFs (the graph's journal "
        "papers). Papers are short and mined on a panel open, so these stay small: "
        "12 floats is the pymupdf twin of the ar5iv extractor's 8-figure cap (a "
        "little higher because tables and algorithms count too), and 80 pages "
        "covers even long papers while keeping a mislabeled 1000-page scan from "
        "stalling the panel."
    )
    library_documents: MiningCaps = Field(
        description="Mining caps for UPLOADED LIBRARY PDFs, sized for textbooks "
        "instead of papers: hundreds of numbered figures, all of which must be "
        "addressable (chapter 12's included — the Sarsa(λ) lesson in "
        "docs/bugs.md). Mining runs once per upload and is cached (~6s for a "
        "548-page book); the caps only guard against pathological documents."
    )
    render_dpi: PositiveInt = Field(
        description="Resolution for rendering a mined float's page region to PNG. "
        "150 dpi reads crisply in the panel/lightbox without ballooning image size."
    )


class ServerConfig(ConfigModel):
    """Where the Flask app listens, how loudly it logs, and the route-owned
    conversation policy.
    """

    host: str = Field(min_length=1, description="Interface Flask binds to.")
    port: int = Field(ge=1, le=65535, description="TCP port Flask listens on.")
    debug: bool = Field(
        description="Verbose (DEBUG-level) logging, including the arXiv client's "
        "per-page requests."
    )
    history_turns: PositiveInt = Field(
        description="Past user+assistant turn pairs each chat keeps as context. "
        "The whole retained window is re-sent to the model on every follow-up, "
        "so this caps token cost and context growth, not storage."
    )


class Config(ConfigModel):
    """All configuration, grouped by the part of the app that consumes it."""

    storage: StorageConfig
    providers: ProvidersConfig
    graph: GraphConfig
    sources: SourcesConfig
    pdf: PdfConfig
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


config = load_settings()
