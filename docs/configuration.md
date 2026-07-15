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
  - **Predicted** from the seed's age and citation count by a **scikit-learn
    model trained on real data** (not hand-tuned numbers), clamped to
    `[floor, cite_limit]`. Used wherever the citers come back all-time-ranked —
    the OpenAlex provider and the offline S2 citations corpus. The app loads the
    model (`src/ml_pipelines/cite_budget/model.joblib`) and calls `.predict()`;
    it's fit by `src/ml_pipelines/cite_budget/train.py` (see that package's
    README, and `research/cite_budget/` for the exploratory study).
  - **Selected** from the citer pool directly — up to `DENSITY_CAP` (12) landmarks
    **per publication year**, taking the most-cited in each. Used by the **live S2
    citation fallback**, which holds its whole pool in memory before trimming, so
    nothing has to be predicted. It also can't use a count: a count keeps a prefix
    of the ranking, and DQN's prefix is entirely 2019–2023 — leaving an 18-month
    hole before the Latest frontier. Per-year banding ships 84 landmarks evenly
    across 2019–2025 instead, with no hole. No model artifact needed.

  Turn off to always ship the flat `cite_limit` on every path.
- **`adaptive_latest_band: true`** — the *Latest Publications* relation fills
  recent years evenly, one query per year up to the current year; the lower edge
  defaults to a fixed `latest_band_years` offset (5). For an old seed whose
  landmarks tail off years before that, the timeline shows a dead stretch between
  the last landmark and the first band. When on, the band start is chosen **per
  seed** at the **density tail edge** of the seed's landmark cluster — the most
  recent year still holding ≥ `tau` of its peak year's landmark count (a second
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
`query_analyst`, which expands seed-search queries; the librarian,
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
