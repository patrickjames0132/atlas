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
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    NonNegativeFloat,
    NonNegativeInt,
    PositiveInt,
    ValidationError,
    ValidationInfo,
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


class LecturerExtras(ConfigModel):
    """The lecturer's knobs: the frontier window and the beat-count bounds."""

    frontier_window_months: PositiveInt = Field(
        default=60,
        description="THE CURRENT FRONTIER's recency window, in months. Wide (~5 years) "
        "on purpose: since the OpenAlex hybrid (v4.0.0) the graph's light-green 'Latest "
        "Publications' nodes span the newest years plus the per-year bands below them "
        "(caps.LATEST_NUMBER_OF_BANDS), so the old 12-month lecture window narrated "
        "almost none of what the user sees.",
    )
    min_beats: PositiveInt = Field(
        default=7,
        description="Fewest beats a lecture asks for. Too few for a multi-decade story "
        "forces skipping, which is why this was widened from 5.",
    )
    max_beats: PositiveInt = Field(
        default=12,
        description="Most beats a lecture asks for. The bound lives in the prompt (there "
        "is no hard output cap) and is what keeps lecture length in check — raising it "
        "materially lengthens (and slows) every lecture.",
    )

    @model_validator(mode="after")
    def _beats_bound_is_ordered(self) -> LecturerExtras:
        """A lecture can't want more beats at minimum than at maximum."""
        if self.min_beats > self.max_beats:
            raise ValueError(
                f"min_beats ({self.min_beats}) must not exceed max_beats ({self.max_beats})"
            )
        return self


class ResearcherExtras(ConfigModel):
    """The researcher's per-question budgets — the ceilings on one agentic run.

    Every one is a hard stop on cost and latency, so they're bounded types
    rather than free ints: a zero read budget is legitimate (turn the tool
    off), a negative one is nonsense.
    """

    max_steps: PositiveInt = Field(
        default=12, description="Total tool calls per question, across all tools."
    )
    full_reads: NonNegativeInt = Field(
        default=4, description="Full-text paper reads per question — the priciest tokens."
    )
    summary_reads: NonNegativeInt = Field(
        default=12, description="Abstract/TL;DR reads per question."
    )
    hops: NonNegativeInt = Field(
        default=5, description="expand_node calls per question — bounds graph growth."
    )
    expand_limit: PositiveInt = Field(
        default=8, description="Neighbors fetched per expand_node hop."
    )
    searches: NonNegativeInt = Field(
        default=3, description="search_papers calls per question — bounds off-graph reach."
    )
    search_limit: PositiveInt = Field(default=8, description="Hits fetched per search.")
    source_searches: NonNegativeInt = Field(
        default=5, description="Library-retrieval calls per question."
    )
    figures: NonNegativeInt = Field(
        default=3, description="show_source_figure calls per answer (0 disables figures)."
    )
    fulltext_max_chars: PositiveInt = Field(
        default=8000,
        description="Characters kept per full-text read, so one read can't flood the context.",
    )


class LibrarianExtras(ConfigModel):
    """The librarian's one knob."""

    figures: NonNegativeInt = Field(
        default=2, description="show_source_figure calls per answer (0 disables figures)."
    )


#: Which typed knob model validates each agent's ``extras`` — the registry
#: ``AgentConfig`` looks itself up in. An agent absent from here has no
#: tunable knobs and must leave ``extras`` empty. Adding a knob means adding
#: a field to the model here (with its default and description), not a bare
#: key in config.json.
AGENT_EXTRAS: dict[str, type[ConfigModel]] = {
    "lecturer": LecturerExtras,
    "researcher": ResearcherExtras,
    "librarian": LibrarianExtras,
}


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
    extras: dict[str, int] = Field(
        description="This agent's tuning knobs — validated against the typed model "
        "registered for its `id` (see AGENT_EXTRAS), so a nonsensical value is "
        "rejected at load instead of reaching the agent. Omitted knobs take the "
        "model's default, and the stored value is always the fully-populated set. "
        "An agent with no registered knobs must leave this empty."
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

    @field_validator("extras")
    @classmethod
    def _extras_match_this_agents_schema(
        cls, extras: dict[str, int], info: ValidationInfo
    ) -> dict[str, int]:
        """Validate the knobs against this agent's typed model, filling defaults.

        The knobs used to be a free-form ``dict[str, Any]`` that each agent
        package range-checked by hand at import — so a value the hand-check
        didn't cover (a negative ``min_beats``, say) sailed through the
        settings modal's save and only misbehaved later. Validation lives here
        now, so every writer of the config — hand-edit, modal, or test — hits
        the same typed schema. Runs as a *field* validator so a failure is
        reported at ``…agents.<n>.extras``, which is where the reader has to
        go to fix it.

        Args:
            extras: The knob values as written in the config file.
            info: Pydantic's validation context — ``id`` is already validated
                (it's declared first), so it can be read from ``info.data``.

        Returns:
            The validated, fully populated knob set.

        Raises:
            ValueError: When a knob is unknown, out of range, or supplied for
                an agent that has none.
        """
        agent_id = info.data.get("id")
        schema = AGENT_EXTRAS.get(agent_id) if isinstance(agent_id, str) else None
        if schema is None:
            if extras:
                raise ValueError(
                    f"agent {agent_id!r} has no tunable knobs — extras must be empty, "
                    f"got {sorted(extras)}"
                )
            return extras
        try:
            return dict(schema.model_validate(extras).model_dump())
        except ValidationError as error:
            # Flatten the inner model's failures into one readable line each —
            # the reader wants the knob name and the rule, not a nested dump.
            raise ValueError(
                "; ".join(
                    f"{'.'.join(str(part) for part in item['loc']) or 'extras'}: {item['msg']}"
                    for item in error.errors()
                )
            ) from None

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


class UIConfig(ConfigModel):
    """Frontend defaults — what a fresh browser starts with.

    Same shape of setting as ``providers.default_provider``: config decides
    where the UI *starts*, and an in-app control overrides it from there,
    remembered per browser. Nothing here affects a request; it's the opening
    state of a preference the user owns.
    """

    default_theme: Literal["dark", "light"] = Field(
        description="Which colour theme a browser with no saved preference opens in. "
        "The header's toggle overrides it and remembers the choice locally, so this "
        "is the default, not a lock. 'dark' is the app's native look — the relation "
        "palette (gold seed, blue references, green landmarks) is tuned against it, "
        "though it reads on either background."
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
    ui: UIConfig


CONFIG_PATH = PROJECT_ROOT / "config.json"

#: The tracked template. A missing default ``config.json`` is **created from
#: it automatically** at load (fresh checkout boots keyless with no setup
#: step), and the settings route uses its key order as the canonical
#: structure every save is written in.
EXAMPLE_CONFIG_PATH = PROJECT_ROOT / "config.example.json"

#: Optional sidecar naming the active config file — one absolute path on one
#: line. Written by the settings modal's "config file location" setting. A
#: sidecar rather than a config field because the pointer to the config can't
#: live inside the file it points at. Gitignored, like the config itself.
CONFIG_LOCATION_FILE = PROJECT_ROOT / ".config-location"


def active_config_path() -> Path:
    """The config file the app runs on — the sidecar's pick, or the default.

    Returns:
        The path named by ``CONFIG_LOCATION_FILE`` when the sidecar exists and
        is non-blank, else the default ``CONFIG_PATH`` (created from the
        example on first load — see :func:`load_settings`).
    """
    try:
        named = CONFIG_LOCATION_FILE.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        named = ""
    return Path(named).expanduser() if named else CONFIG_PATH


def load_settings(path: Path | None = None) -> Config:
    """Parse and validate a config file into a Settings object.

    A missing **default** ``config.json`` is created from the tracked example
    first (a fresh checkout boots keyless, no setup step); only a missing
    *sidecar-named* file is an error — the user pointed at something that
    isn't there.

    Args:
        path: The file to load; None (the default) loads the active config
            (see :func:`active_config_path`).

    Returns:
        The validated settings.

    Raises:
        FileNotFoundError: When a user-chosen config file doesn't exist.
    """
    path = path if path is not None else active_config_path()
    if path == CONFIG_PATH and not path.exists():
        path.write_text(EXAMPLE_CONFIG_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    try:
        raw = path.read_text()
    except FileNotFoundError:
        raise FileNotFoundError(f"config file {path} not found") from None
    return Config.model_validate_json(raw)


config = load_settings()


def reload_config(path: Path | None = None) -> None:
    """Re-read the active config file into the shared ``config``, in place.

    The settings modal's write path: after the settings route rewrites the
    config file (or repoints the sidecar), this folds the fresh values into
    the **existing** ``config`` object field by field — every consumer holds
    the module-level ``config`` and reads its fields late (the codebase
    convention), so an in-place update is seen everywhere without a restart.
    Validation happens in :func:`load_settings`; on failure the shared object
    is left untouched.

    Args:
        path: The file to load; None (the default) re-reads the active config.

    Raises:
        FileNotFoundError: When the file doesn't exist.
        pydantic.ValidationError: When the file's contents are invalid —
            propagated so the caller can report it; ``config`` is unchanged.
    """
    fresh = load_settings(path)
    for field_name in Config.model_fields:
        setattr(config, field_name, getattr(fresh, field_name))
