# Configuration reference

`config.json` (repo root, gitignored) holds every tunable; copy
`config.example.json` to start. Each field's meaning lives as a Pydantic
`Field(description=...)` right next to it in
[`config.py`](../src/arxiv_digest/config.py) — read that file for what each
setting does. This page is for the **why** behind specific example values,
where a JSON file (no comments allowed) can't say it.

## `s2` — Semantic Scholar

- **`min_interval: 1.1`** — even an authenticated API key only allows ~1
  request/second on the graph endpoints. Waiting 1.1s between requests up
  front is cheaper than firing bursts and eating 429s + exponential backoff.
  Set to `0` to disable (the test suite does this so it never sleeps).
- **No `api_key` still works.** Atlas runs fully keyless, just harder
  rate-limited. A free key from
  [semanticscholar.org/product/api](https://www.semanticscholar.org/product/api)
  lifts that ceiling substantially.

## `graph` — neighborhood size

- **`ref_limit` / `cite_limit` / `similar_limit` = 25 / 25 / 15** — caps
  ~65 nodes per graph: enough to explore meaningfully, small enough to
  render smoothly on `react-force-graph-2d` and stay polite to the S2 rate
  limit.
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

A **list**, not a single object, because more agents are planned beyond
today's one entry (the teaching assistant that narrates lectures and
answers grounded Q&A over the graph) — potentially on different vendors.
Each entry:

```json
{ "id": "teaching_assistant", "model": "anthropic:claude-sonnet-4-6", "system_prompt": "...", "tools": [...], "extras": {...} }
```

- **`id`** must be unique across the list — other code looks an agent up by
  it, so a duplicate would be ambiguous. Validated at load time.
- **`model`** is PydanticAI's own `"<provider>:<model_name>"` shorthand
  string (e.g. `"anthropic:claude-sonnet-4-6"`), not a bare model name. The
  prefix must name a vendor configured under `llm.providers` — validated at
  load time, so a typo'd or unconfigured vendor fails immediately instead of
  on the agent's first request. `AgentConfig.provider` parses that prefix
  back out for whatever builds the real `pydantic_ai.Agent`.
- **`system_prompt`** and **`tools`** are placeholders for now (`""` and
  `[]`) — they'll be filled in as the teacher/agentic code is ported
  (Phase 4 of the rebuild).
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
