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
- **`backfill`** — the deterministic "How we got here" reference walk the
  orchestrator runs before a history lecture (no LLM involved, which is why
  it lives here and not under `llm.agents` extras). `hops: 3` ×
  `frontier: 2` launch papers × `fetch_limit: 8` references bounds the walk
  at ~48 day-cached S2 lookups worst case; `per_hop: 6` keeps only the
  most-cited (seminal) new ancestors per hop so the graph grows by ≤18
  nodes; `lookback_years: 40` stops the march once the story reaches ~a
  career-length before the seed — past that, "roots" stop being
  interpretable context for a modern paper.

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
`src/arxiv_digest/agents/` — they land one at a time (today:
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
  `config.py` and `tools.py` (see `src/arxiv_digest/agents/README.md`).
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
