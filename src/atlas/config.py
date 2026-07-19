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


class S2CorpusStorage(ConfigModel):
    """Where the offline Semantic Scholar citations corpus lives — both halves.

    Two roots rather than one, because the halves have **opposite access
    patterns** and can want different drives:

    * ``raw`` — the downloaded ``.gz`` shards (~400GB/release) plus their
      ``download.json`` checkpoint. Written once, read once, sequentially: a
      spinning disk does that perfectly well, and the shards are deletable the
      moment an ingest succeeds (a re-ingest means a re-download).
    * ``parquet`` — the ingested, queried working set (~50GB) **and the
      ``CURRENT`` pointer**. It absorbs the ingest's ~400k partitioned writes and
      then serves every graph build, so it wants the fast drive (measured:
      20.6s/shard on NVMe vs 98.2s on an SMR HDD — 2.2h vs 10.6h per release).

    ``parquet`` is the app's **only serving dependency**: ``CURRENT`` lives beside
    the data it names, so a machine that only serves needs nothing but this root
    — pull the raw drive and the corpus keeps working. ``raw`` is an operator
    concern, needed by ``atlas corpus download``/``ingest`` alone.

    Either may be null. Null ``parquet`` turns the corpus off (the s2 provider
    falls back to the live citation endpoint); null ``raw`` just means this
    machine doesn't download. Both may point at the same directory when one drive
    holds everything. Same anchoring as ``data_dir``: relative → repo root,
    absolute → as-is. **Kept outside the repo and gitignored** — it's hundreds of
    GB. See integrations/semantic_scholar/corpus/README.md.
    """

    raw: Path | None = Field(
        default=None,
        description="Root for downloaded shards + download.json — `atlas corpus download` "
        "writes here and `ingest` reads it. Null means this machine doesn't download; "
        "serving doesn't need it. Deletable after a successful ingest.",
    )
    parquet: Path | None = Field(
        default=None,
        description="Root for the ingested Parquet + the CURRENT pointer — the app's only "
        "serving dependency. Null turns the corpus off (live S2 citations instead).",
    )

    @field_validator("raw", "parquet")
    @classmethod
    def _anchor_to_repo_root(cls, path: Path | None) -> Path | None:
        """Anchor a relative corpus root to the repo root; leave an absolute one
        (the common case — the corpus lives on its own drive) untouched. None
        stays None: that half is simply not configured.
        """
        if path is None:
            return None
        path = path.expanduser()
        return path if path.is_absolute() else PROJECT_ROOT / path


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
    s2: S2CorpusStorage = Field(
        default_factory=S2CorpusStorage,
        description="The offline S2 citations corpus's two roots (see S2CorpusStorage). "
        "Omit entirely to run without a corpus.",
    )

    @field_validator("data_dir")
    @classmethod
    def _anchor_to_repo_root(cls, path: Path) -> Path:
        """A relative path in config.json means "relative to the repo root"."""
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
    service.

    Groups the academic-data backbones (Semantic Scholar, OpenAlex) the same
    way ``llm.providers`` groups the LLM vendors: connection settings — keys,
    URLs, timeouts, throttles — live together, per service. Adding a data
    source later is purely additive: a new field here, no redesign.
    """

    s2: SemanticScholarConfig
    openalex: OpenAlexConfig


class GraphConfig(ConfigModel):
    """How big a neighborhood one seed paper pulls onto the canvas.

    Each ``*_limit`` is a **ship count**, not a display cap: the backend ranks
    the relation and ships this many nodes (each tagged with its ``rank``), and
    the frontend's per-relation slider treats it as the **maximum** — it defaults
    to showing a modest 25 and reveals more on demand, no re-query. So raise
    these to give the sliders more range ("fetch as much as possible"), at some
    payload cost; a value at or below 25 leaves that slider no room to move.
    **``null`` means unbounded** — ship everything the paper actually has for
    that relation, so the slider can max out to the full count (handy for
    testing; heavy for a busy paper — a reference/similar list is naturally
    small, but ``citation``/``latest`` on a mega seed can be thousands). See
    docs/configuration.md for the node-count math and why ``recs_pool`` must
    stay "all-cs".
    """

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
    ref_limit: PositiveInt | None = Field(
        description="References (papers it cites) to ship — the References slider's max. "
        "null = ship them all."
    )
    cite_limit: PositiveInt | None = Field(
        description="Max all-time-most-cited LANDMARK citations ('citation' nodes) to ship — "
        "the Field Landmarks slider's max. null = ship the unbounded cap (500)."
    )
    adaptive_cite_limit: bool = Field(
        description="Size the landmark band to the seed instead of always shipping "
        "cite_limit: an old classic earns a deep band (its top citers span decades), a "
        "young hot paper a tight one (its top citers are same-era pile-on). Every path "
        "measures its real citer pool with the rules in services/graph/budget.py; "
        "cite_limit stays the ceiling."
    )
    latest_limit: PositiveInt | None = Field(
        description="LATEST citations (the recent frontier — citers from the newest "
        "years plus the per-year bands below them) to ship as 'latest' nodes — the "
        "Latest Publications slider's max. null = ship them all."
    )
    similar_limit: PositiveInt | None = Field(
        description="SPECTER2-embedding neighbors to ship as 'similar' nodes — the "
        "Similar slider's max. null = as many as S2 will return."
    )
    latest_band_years: PositiveInt = Field(
        description="How far below the landmark cutoff the per-year 'Latest Publications' "
        "bands start — one cited_by_count:desc query per year, each feeding the LATEST "
        "relation (not landmarks), running up to the current year. Fills recent years "
        "evenly. The fixed FALLBACK lower edge when adaptive_latest_band is off or its model "
        "can't load. See openalex/traversal.py citation_relations."
    )
    adaptive_latest_band: bool = Field(
        description="Start the 'Latest Publications' bands at the density tail edge of the "
        "seed's landmark cluster (the most recent still-dense year) instead of a fixed "
        "latest_band_years lower edge: an old classic whose landmarks tail off early extends "
        "its bands back to close the gap, while a young paper starts at its own recent edge "
        "(a tight frontier). Capped by max_span for bounded query cost. See "
        "services/graph/bands.py earliest_band_year."
    )
    latest_per_year: PositiveInt = Field(
        description="Top-N most-cited citers kept from each Latest-Publications year band "
        "(≤200, OpenAlex's page cap). Per-year banding gives even coverage; a single "
        "recent-window query sorted by citations would let its oldest year dominate."
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
    max_floats: PositiveInt = Field(
        description="Maximum figures/tables/algorithms mined from one PDF — the "
        "pymupdf twin of the ar5iv extractor's 8-figure cap, a little higher "
        "because tables and algorithms now count too."
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
