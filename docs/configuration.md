# Configuration reference

`config.json` (repo root, gitignored) holds every tunable; copy
`config.example.json` to start. Each field's meaning lives as a Pydantic
`Field(description=...)` right next to it in
[`config.py`](../src/atlas/config.py) — read that file for what each
setting does. This page is for the **why** behind specific example values,
where a JSON file (no comments allowed) can't say it.

## `providers` — external data APIs

The academic-data backbones the graph is built from, one sub-object per
service (`providers.s2`, `providers.openalex`) — grouped the same way
`llm.providers` groups the LLM vendors (which live separately under `llm`,
because those are chat/tool-use credentials, not graph data sources).

### `providers.s2` — Semantic Scholar

- **`min_interval: 1.1`** — even an authenticated API key only allows ~1
  request/second on the graph endpoints. Waiting 1.1s between requests up
  front is cheaper than firing bursts and eating 429s + exponential backoff.
  Set to `0` to disable (the test suite does this so it never sleeps).
- **No `api_key` still works.** Atlas runs fully keyless, just harder
  rate-limited. A free key from
  [semanticscholar.org/product/api](https://www.semanticscholar.org/product/api)
  lifts that ceiling substantially.

### `providers.openalex` — OpenAlex

- **`min_interval: 0.1`** — OpenAlex allows ~10 req/s, so a light throttle
  suffices; its budget/lock is separate from the S2 client's.
- **`mailto`** joins OpenAlex's "polite pool" (faster, more reliable) even
  keyless; a free `api_key` grants $1/day of metered usage vs $0.10 keyless
  (id/DOI lookups are free either way — see `config.py` for the pricing
  notes, verified live 2026-07-09).

## `storage.s2` — where the citations corpus lives

Two roots, because the corpus's halves have **opposite access patterns**. Both
default to `null` (corpus off — the s2 provider uses the live citation endpoint).
See [`corpus/README.md`](../src/atlas/integrations/semantic_scholar/corpus/README.md).

- **`s2.raw`** — the downloaded `.gz` shards (~400 GB/release) plus their
  `download.json` checkpoint. Written once, read once, **sequentially** — which
  even a 5400-RPM drive does perfectly well, so this is where a big slow disk
  earns its keep. Deletable the moment an ingest succeeds; a re-ingest just means
  a re-download. `null` on a machine that only serves.
- **`s2.parquet`** — the ingested working set (~50 GB) **and the `CURRENT`
  pointer**. It absorbs the ingest's ~400k partitioned writes and then serves every
  graph build, so it wants the fast drive: measured on one citations shard,
  **20.6s on NVMe vs 98.2s on an SMR HDD** — 2.2h vs 10.6h for a full release.
  `null` turns the corpus off.

**`parquet` is the app's only serving dependency.** `CURRENT` lives beside the data
it names, so once a release is ingested you can pull the raw drive (or delete its
shards) and graph builds carry on. `raw` is an operator concern — only
`atlas corpus download`/`ingest` read it.

Point both at the same directory when one drive holds everything; there's no
special case for it. A typical split:

```json
"s2": { "raw": "E:\\s2corpus", "parquet": "D:\\s2corpus" }
```

## `graph` — neighborhood size

- **`ref_limit` / `cite_limit` / `similar_limit` = 100 / 150 / 60** — ship
  counts, not display caps: the frontend sliders default to a modest reveal
  and treat these as their maximum, so generous values give the sliders
  range without cluttering the first render.
- **`adaptive_cite_limit: true`** — a flat landmark budget fits no one:
  an old classic's top citers span decades and read as a map (Hawking
  Radiation earns a large budget), while a young hot paper's top citers are
  same-era pile-on (DQN reads better at ~60, "Attention Is All You Need" at
  ~30). When on, the landmark ship count is sized per seed — by one of two
  routes to the same criterion, both in `services/graph/budget.py`:
  - **Computed** — the **STOP rule** (`computed_cite_limit`): walk the seed's
    citers most-cited first, bucketing by publication year, and stop where a
    year first overflows `PER_YEAR_CAP` (12); ship that many, a prefix of the
    all-time ranking. Used by every path holding a whole-history ranking: the
    **offline corpus**, **OpenAlex** (the rule only ever reads the top of the
    ranking, so one server-sorted page suffices), and a **complete live S2
    pool** (a seed whose citer list ends before the API's offset ceiling). No
    model artifact involved — the count is measured, not estimated. (A trained
    model predicted this number for OpenAlex until v5.13.0; see
    [`predict-vs-compute.md`](predict-vs-compute.md).)
  - **Selected** from the citer pool directly — up to `PER_YEAR_CAP` landmarks
    **per publication year**, taking the most-cited in each and *skipping* citers
    whose year is already full (`select_landmarks`, the **SKIP rule**). Used by
    the live S2 fallback's **truncated** pools (the offset ceiling cut the list
    off): a truncated ranking has no honest prefix — DQN's stops at 29 landmarks
    with **nothing from 2024–2025**, an 18-month hole before the Latest
    frontier, where skipping full years ships 84, twelve in each of 2019–2025.

  Turn off to always ship the flat `cite_limit` on every path. Both routes' terms
  are defined in [`landmark-vocabulary.md`](landmark-vocabulary.md).
- **`adaptive_latest_band: true`** — the *Latest Publications* relation fills
  recent years evenly, one query per year up to the current year; the lower edge
  defaults to a fixed `latest_band_years` offset (5). For an old seed whose
  landmarks tail off years before that, the timeline shows a dead stretch between
  the last landmark and the first band. When on, the band start is chosen **per
  seed** at the **tail edge** of the seed's landmark cluster — scanning back from
  the newest landmark year, the first year still holding ≥ `tau` of the peak
  year's landmark count (a second
  model trained on real data, `src/ml_pipelines/latest_gap/model.joblib`, served in
  `services/graph/bands.py`) — so an old classic's bands widen back to meet its
  cluster while a young paper starts at its own recent edge (a tight frontier). A
  `max_span` cap bounds query cost. Turn off (or if the model can't load) to use
  the fixed `latest_band_years` span. See `src/ml_pipelines/latest_gap/README.md` and
  `research/latest_gap/`.
- **`recs_pool: "all-cs"`** — the Recommendations API's default `"recent"`
  pool only draws from newly published papers. Seed on anything older than
  a year or two (e.g. a 2017 paper) and `"recent"` returns *zero* similar
  neighbors. `"all-cs"` searches all of CS, which is what you want unless
  you're deliberately exploring only brand-new work.
- **`cache_ttl: 86400`** (1 day) — citation graphs change slowly; a day-long
  cache keeps repeat exploration and backtracking instant without
  re-hitting S2.

## `llm` — everything about talking to LLMs

Two things live under one group because an agent is meaningless without a
provider to run it on: **`llm.providers`** (backend vendor credentials) and
**`llm.agents`** (the agents themselves). Deliberately separate from
`sources.embedding` — that's a local embedding model for search, not a
chat/tool-use LLM.

### `llm.providers` — backend credentials

This app is migrating its agents onto
[PydanticAI](https://ai.pydantic.dev), which supports many LLM vendors, not
just Anthropic. PydanticAI itself separates *authentication* (a `Provider`
object, e.g. `AnthropicProvider(api_key=...)`) from *behavior* (an `Agent`:
system prompt, tools) — `llm.providers` mirrors that split so our config
maps cleanly onto PydanticAI's own constructs:

```json
"llm": { "providers": { "anthropic": { "api_key": "sk-ant-..." } } }
```

One sub-object per vendor. Only `anthropic` is wired up today (that's what
we're testing against), but adding a second vendor later — say
`llm.providers.openai.api_key` — is purely additive: a new field, no
redesign. Credentials live here, **not** on individual agents, because a
key belongs to an (account × vendor) pair, not to any one agent — two
agents sharing a vendor should share its key rather than duplicate it
(duplicated keys are a rotation hazard: change one copy and forget the
other). This also means we never rely on PydanticAI's own
environment-variable fallback for auth — every key is explicit, straight
from `config.json`.

### `llm.agents` — the agents this app runs

A **list** with one entry per sub-agent package under
`src/atlas/agents/` — they land one at a time (today:
`query_analyst`, which expands seed-search queries; `summarizer`, the
detail panel's on-demand paper TL;DR (generation only ever fires on the
panel's explicit TL;DR toggle, cached per paper forever); the librarian,
lecturer, researcher, and orchestrator follow), potentially on different
vendors. Each entry:

```json
{ "id": "query_analyst", "model": "anthropic:claude-haiku-4-5", "extras": {} }
```

- **`id`** must be unique across the list — each agent package names the
  entry it builds from (its `config.py`'s `AGENT_ID`), so a duplicate would
  be ambiguous. Validated at load time.
- **`model`** is PydanticAI's own `"<provider>:<model_name>"` shorthand
  string (e.g. `"anthropic:claude-haiku-4-5"`), not a bare model name. The
  prefix must name a vendor configured under `llm.providers` — validated at
  load time, so a typo'd or unconfigured vendor fails immediately instead of
  on the agent's first request. The string is only ever **parsed** (by
  `agents/factory.py`, which constructs the provider explicitly with the
  config key) — never handed to PydanticAI whole, since the bare shorthand
  would fall back to environment variables for auth, against the rule
  above.
- An entry is deliberately **thin**: an agent's words (system prompt,
  skills) and its tool functions are *code*, defined in its own package's
  `config.py` and `tools.py` (see `src/atlas/agents/README.md`).
  Config carries only what an operator tunes — the model and the knobs.
- **`extras`** is a deliberate escape hatch: a free-form JSON object for
  settings that don't have a permanent typed home yet. An earlier version
  of this config had a dozen first-class fields here — per-tool-call
  budgets (`max_steps`, `reads.max_full`, `s2_search.limit`, a "How we got
  here" lecture's backward-walk knobs, etc.). All of that was cut rather
  than carried forward as dead weight; if a given knob turns out to still
  matter once the agent is rebuilt, it goes into `extras` first and only
  gets promoted to a proper typed field (with real validation) once its
  final shape has settled. Don't treat `extras` as a long-term home —
  it's a staging area, not a junk drawer.

## `server` — Flask + conversation policy

- **`history_turns: 8`** — each chat (graph Q&A and library chat, separate
  stores) keeps its last 8 user+assistant pairs as context, persisted only
  on success and trimmed after each turn. The whole retained window is
  re-sent to the model on *every* follow-up, so this is a token-cost and
  context-window cap, not a storage limit — 8 pairs keeps multi-step
  tutoring coherent while bounding the per-question overhead. Stores are
  in-memory (cleared on restart — fine for a local single-user app).

## `sources` — bring-your-own sources

- **`embedding.model`**: `all-MiniLM-L6-v2`, 384-dim, symmetric (no query
  prefix needed). Swapping in an asymmetric model (e.g.
  `BAAI/bge-small-en-v1.5`) needs a non-empty `query_prefix` *and*
  re-ingesting every existing source — their stored vectors were produced by
  the old model and aren't comparable to the new one's.
- **`embedding.device: "auto"`** — the torch device the embedder runs on.
  `auto` hands the choice to sentence-transformers, which already knows how to
  find cuda / mps / xpu and falls back to cpu; we don't second-guess it. Set an
  explicit device (`cpu`, `cuda`, `cuda:1`, `mps`) only to override — e.g. to
  keep the GPU free for something else. An explicit device that won't load
  falls back to cpu with a logged warning rather than taking search down.

  This only pays off with a **GPU-enabled torch build**. On Windows that isn't
  the default — PyPI ships a CPU-only wheel — so `pyproject.toml` routes torch
  to PyTorch's `cu130` index for `sys_platform == 'win32'`; other platforms
  resolve from PyPI unchanged. Measured on an RTX 3070 Ti, 2000 chunks
  embedded at **1497/s on cuda vs 80/s on cpu (~19×)**; ingest is where that
  lands, since a single query embedding is overhead-dominated either way.
- **`chunking.chars: 900`, `chunking.overlap: 150`** — chunking is
  character-based (cheap, model-agnostic), but MiniLM truncates its input at
  ~256 word-pieces, roughly 1000 characters. A chunk longer than that has its
  tail silently embedded into nothing — unsearchable text with no error. 900
  stays under that ceiling with margin; the 150-char overlap keeps a sentence
  that straddles a chunk boundary findable from either side.
- **`retrieval.hybrid: true`, `retrieval.rrf_k: 60`** — hybrid search fuses
  vector (semantic) and FTS5 (lexical, BM25) rankings via Reciprocal Rank
  Fusion, so an exact term or proper noun the embedder blurs together still
  surfaces. `60` is the standard damping constant from the original RRF
  paper — no need to tune it. Lexical fusion is skipped automatically (falls
  back to pure vector search) if the local SQLite build lacks FTS5.
- **`retrieval.chat_k` (8) > `retrieval.search_k` (6)** — the graph-free
  sources chat retrieves more passages per query because that retrieval is
  the *only* grounding the answer gets — there's no paper full-text and no
  follow-up search to fall back on.

## `pdf` — open-access PDF mining

Fetch-and-mine settings for papers without an ar5iv render (see
`services/pdf`): full text for the researcher's full reads and
caption-anchored figures/tables/algorithms for the detail panel. The
storage design behind these knobs — why whole PDFs are cached and images
are not — is written up in [pdf-mining.md](pdf-mining.md).

- **`max_bytes: 26214400` (25 MB)** — aborts a download mid-stream, since a
  Content-Length header can lie or be missing. Virtually every paper PDF is
  a few MB; the cap is about a mislabeled/hostile URL, not typical papers.
- **`timeout: 60`** — PDFs are much bigger than the JSON the provider
  timeouts were sized for, so downloads get their own, longer clock.
- **`cache_files: 200`** — the on-disk PDF cache (`data_dir/oa_pdfs`,
  LRU-pruned). At ~2 MB per typical paper that's ~400 MB worst case;
  mined text/floats stay in the SQLite cache for a month either way, so an
  evicted PDF only costs a re-download when its figures are next *rendered*.
- **`research_papers: {max_floats: 12, max_pages: 80}`** — mining caps for
  open-access *paper* PDFs: the pymupdf twin of the ar5iv extractor's
  8-figure cap (slightly higher because tables and algorithm boxes count
  too), and a page cap that keeps a mislabeled 1000-page scan from stalling
  a panel open.
- **`library_documents: {max_floats: 400, max_pages: 1500}`** — the same caps for
  *uploaded library* PDFs, sized for textbooks instead of papers — one
  sub-object per corpus, because limits tuned for papers were silent data
  loss on books: they truncated Sutton & Barto at page 80 / 12 figures,
  making chapter 12's figures unaddressable (the Sarsa(λ) incident in
  `docs/bugs.md`). A 548-page book mines cover-to-cover in ~6 s, once,
  cached.
- **`render_dpi: 150`** — mined floats are served as page-region renders
  (vector figures have no embedded image to extract); 150 dpi reads crisply
  in the panel and lightbox without ballooning image bytes.
