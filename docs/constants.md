# Constants catalogue

Every module-level tunable constant in `src/` — the raw material for the
constants-audit decisions (which values stay code, which belong in
`config.json`, which graduate to the settings modal). Compiled 2026-07-19 at
v6.0.0; **hand-maintained**, so update the row when a constant moves or its
value changes. Structural definitions (regexes, SQL schemas, prompts, agent
ids, field-select strings) are deliberately out of scope — they aren't
tunables. Reference lists cover `src/` only (tests mirror them); a file is
listed whether the reference is code or a load-bearing docstring.

The verdict grouping below mirrors the audit's recommendation, so a row's
section is a *proposal*, not a decision — the decisions land in the
settings-modal ticket's candidate list.

## API reality — turning these breaks calls or corrupts data

| Name | What it is | Why it's needed | Value | Referenced in |
|---|---|---|---|---|
| `_BATCH_MAX` | Ids per S2 `/paper/batch` call | S2 rejects larger batches | 500 | `src/atlas/integrations/semantic_scholar/traversal.py` |
| `_RANK_POOL` | S2 over-fetch page size (references/citations) | S2 offers no server sort — fetch a big pool, rank locally; also the deep-pager's page size (S2's max `limit`) | 1000 | `src/atlas/integrations/semantic_scholar/traversal.py` |
| `_MAX_OFFSET` | Deepest S2 citations-page offset | S2 400s past it (verified live 2026-07-15: 9000 fails, 8000 serves) | 8000 | `src/atlas/integrations/semantic_scholar/traversal.py` |
| `_PER_PAGE` | OpenAlex page size | OpenAlex caps `per-page` at 200 | 200 | `src/atlas/integrations/openalex/traversal.py` |
| `_OR_FILTER_MAX` | Values per OpenAlex OR filter | OpenAlex caps `a\|b\|c` filters at 50 values | 50 | `src/atlas/integrations/openalex/traversal.py` |
| `NBUCKETS` | Corpus citations hash-partition count | Baked into the ingested Parquet layout — a different value orphans every ingested release | 1024 | `src/atlas/integrations/semantic_scholar/corpus/ingest.py`, `.../corpus/source.py` |
| `_CHUNK_BYTES` (corpus) | Download stream chunk size | Throughput mechanics for ~400 GB shard downloads | 4 MiB | `src/atlas/integrations/semantic_scholar/corpus/download.py` |
| `_CHUNK_BYTES` (pdf) | PDF download chunk size | Same mechanics, small files | 64 KiB | `src/atlas/services/pdf/fetch.py` |
| `_SHARDS_PER_WORKER` | Corpus-ingest work-unit size | Balances DuckDB memory vs. parallelism during ingest | 16 | `src/atlas/integrations/semantic_scholar/corpus/ingest.py` |
| `_EMBED_BATCH` | Chunks embedded per model call | sentence-transformers throughput/memory balance | 64 | `src/atlas/services/sources/ingest.py` |

## Fitted or derived — the "data-driven over magic numbers" set

| Name | What it is | Why it's needed | Value | Referenced in |
|---|---|---|---|---|
| `PER_YEAR_CAP` | Max landmarks per publication year (STOP/SKIP bucket cap) | **Fitted** by a parameter sweep (the fitting pipeline was removed in the 2026-07-22 research reset); makes "clutter" concrete — both sizing rules share it | 12 | `src/atlas/services/graph/budget.py`, `src/atlas/integrations/openalex/traversal.py`, `src/atlas/integrations/caps.py` (doc) |
| `TAU`, `MAX_SPAN` | Latest-band start rule: density threshold + widest span | **Fitted** on a 64-seed corpus, then **inlined** as constants when the fitting pipeline was removed (2026-07-22 research reset) | 0.25 / 7 | `src/atlas/services/graph/bands.py` |
| `MIN_LANDMARK_YEARS` | Fewest dated landmark years the tau rule trusts | Below it no boundary is trustworthy — the rule declines and the fixed span serves | 10 | `src/atlas/services/graph/bands.py` |
| `UNBOUNDED_LANDMARK_CAP` | The shared **payload guard** — every citation relation's flat ceiling | Never fitted, deliberately not config (settled v6.0.0): a mega seed can't page its citer list into one response | 500 | `src/atlas/integrations/caps.py` (home), `.../openalex/traversal.py`, `.../semantic_scholar/traversal.py`, `.../semantic_scholar/corpus/source.py`, `src/atlas/services/graph/budget.py`, `src/atlas/config.py` (doc), `src/atlas/integrations/__init__.py` (doc) |
| `LATEST_NUMBER_OF_BANDS` | The Latest bands' fallback span (one-year bands below the landmark cutoff) | Serves only when the tau rule can't place a per-seed start; code by the same argument as the landmarks' guard (was config `graph.latest_nodes.number_of_bands`) | 5 | `src/atlas/integrations/caps.py` (home), `.../openalex/traversal.py`, `.../semantic_scholar/traversal.py`, `.../semantic_scholar/corpus/source.py`, `src/atlas/services/graph/bands.py` (doc) |
| `LATEST_NODES_PER_BAND` | Top-N most-cited citers each one-year Latest band keeps | The Latest analog of `PER_YEAR_CAP` — except eyeballed, not fitted (≤200, OpenAlex's page cap); the modal's non-adaptive mode will hand it to the user per request (was config `graph.latest_nodes.nodes_per_band`) | 50 | `src/atlas/integrations/caps.py` (home), `.../openalex/traversal.py`, `.../semantic_scholar/traversal.py`, `.../semantic_scholar/corpus/source.py` |
| `REACHABLE_CITERS` | Most citers a live deep-page can return | Derived: `_MAX_OFFSET + _RANK_POOL` — the truncation boundary | 9000 | `src/atlas/integrations/semantic_scholar/traversal.py` |
| `_LATEST_YEARS` | Calendar years that are latest-only, never landmarks | Defines the landmark/latest boundary (`landmark_max_year`) — a relation *definition*, not a size | 2 | `src/atlas/integrations/openalex/traversal.py` |
| `_LATEST_WINDOW_MONTHS` | Truncated live pool's rolling "latest" window | The degraded fallback's frontier definition (a truncated pool can't be banded per-year honestly) | 12 | `src/atlas/integrations/semantic_scholar/traversal.py` |
| `_BUILD_STEPS` | Coarse build stages reported to the progress UI | The progress bar's denominator — counts the build's actual stages | 4 | `src/atlas/services/graph/build.py` |

## Content & prompt budgets — shaping what models and panels see

| Name | What it is | Why it's needed | Value | Referenced in |
|---|---|---|---|---|
| `_FIGURE_PAPERS` | Most-cited papers contributing figures to a lecture pool | Bounds figure fetches + prompt size per lecture | 4 | `src/atlas/agents/lecturer/main.py` |
| `_FIGURES_PER_PAPER` | Figures taken from each of those papers | Same bound, per paper | 3 | `src/atlas/agents/lecturer/main.py` |
| `_SEED_FULLTEXT_CHARS` | Seed full-text cap for the intuition lecture | Keeps the teach-the-paper prompt affordable | 12000 | `src/atlas/agents/lecturer/main.py` |
| `_LECTURES_MAX_CHARS` | Played-lectures context cap for the researcher | A full set of four lectures can't blow the prompt | 6000 | `src/atlas/agents/researcher/main.py` |
| `_MAX_TOPICS` | OpenAlex topics kept per node | Detail-panel display cap | 6 | `src/atlas/integrations/openalex/nodes.py` |
| `_MAX_ITEMS` | Hugging Face code links kept per paper | Detail-panel display cap | 5 | `src/atlas/integrations/huggingface/code_links.py` |
| `_MAX_CANDIDATES` | Figure candidates listed to the librarian | Bounds the figure-choice prompt | 8 | `src/atlas/services/sources/figures.py` |
| `_CANDIDATE_CAPTION` | Chars of each candidate's caption shown | Same prompt bound | 80 | `src/atlas/services/sources/figures.py` |
| `_MAX_CAPTION` (ar5iv) | Caption length cap, extracted figures | A runaway caption is extraction noise | 600 | `src/atlas/integrations/arxiv/figures.py` |
| `_MAX_CAPTION` (pdf) | Caption length cap, mined PDF floats | Same, deliberately equal to the ar5iv cap | 600 | `src/atlas/services/pdf/floats.py` |

## PDF float-mining geometry — tuned against real PDFs (v5.28.0)

All in `src/atlas/services/pdf/floats.py`; changing any re-opens the
caption-anchoring work they were tuned during.

| Name | What it is | Why it's needed | Value |
|---|---|---|---|
| `_MIN_TILE` | Smallest kept image tile | Keeps film-strip tiles, drops glyph-sized fragments | 30 pt |
| `_MIN_CLUSTER_AREA` | Smallest admitted drawing piece | A diagram may be a swarm of small pieces | 100 pt² |
| `_MIN_REGION_AREA` | Smallest grown region kept | A lone rule/box isn't a figure | 4000 pt² |
| `_GAP` | Max caption↔content distance | Anchors a caption to *its* figure, not the next | 60 pt |
| `_CHAIN_GAP` | Max piece↔region distance (one axis) | Grows a region across a diagram's parts | 60 pt |
| `_RULE_SPAN_MAX_STEP` | Max distance between one float's rules | Splits stacked table rules into separate floats | 320 pt |
| `_RULE_X_TOLERANCE` | X-agreement for rules sharing a float | Same table's rules align; neighbors don't | 8 pt |
| `_PAD` | Margin around a rendered region | Breathing room in the cropped image | 4 pt |

## Cache TTLs — content that is effectively immutable

| Name | What it is | Why it's needed | Value | Referenced in |
|---|---|---|---|---|
| `CACHE_TTL` (arxiv) | ar5iv figures/full-text + category cache | Published papers don't change; re-fetch monthly is plenty | 30 d | `src/atlas/integrations/arxiv/client.py` (home), `figures.py`, `fulltext.py`, `categories.py` |
| `CACHE_TTL` (pdf mine) | Mined-floats manifest cache | Same immutability; mining is expensive | 30 d | `src/atlas/services/pdf/mine.py` |
| `CACHE_TTL` (pdf resolve) | arXiv-id→PDF-URL resolution cache | Resolutions are stable | 30 d | `src/atlas/services/pdf/resolve.py` |
| `CACHE_TTL` (sources figures) | Library-source figure choices | Chosen figures don't change under a stable library | 30 d | `src/atlas/services/sources/figures.py` |
| `CODE_TTL` | Hugging Face code-links cache | Repos/models appear over time — daily refresh | 1 d | `src/atlas/integrations/huggingface/client.py`, `code_links.py` |

(The **graph** snapshot TTL is the one cache knob that is a real operator
concern, and it is already config: `graph.cache_ttl`.)

## Agent extras defaults — config-overridable via `config.llm.agents[].extras`

Each is a code default that an `extras` entry may override; the `extras`
staging area is validated (unknown keys fail at import).

| Name | Agent | What it is | Why it's needed | Value | Referenced in |
|---|---|---|---|---|---|
| `frontier_window_months` | lecturer | THE CURRENT FRONTIER's recency window | The lecture must narrate the same window the graph shows as Latest bands | 60 | `src/atlas/agents/lecturer/config.py` |
| `min_beats` / `max_beats` | lecturer | Lecture length bounds (in beats) | Keeps lectures shaped: room for both ends of a long history without rambling | 7 / 12 | `src/atlas/agents/lecturer/config.py` |
| `max_steps` | researcher | Total tool calls per question | The hard stop on an agentic run's cost/latency | 12 | `src/atlas/agents/researcher/config.py` (consumed via `BUDGETS` in `tools.py`/`main.py`) |
| `full_reads` | researcher | Full-text reads per question | Full texts are the priciest tokens | 4 | same |
| `summary_reads` | researcher | Abstract/TL;DR reads per question | Cheap reads still need a ceiling | 12 | same |
| `hops` | researcher | `expand_node` calls per question | Bounds graph growth per answer | 5 | same |
| `expand_limit` | researcher | Neighbors fetched per hop | Bounds each hop's payload | 8 | same |
| `searches` | researcher | `search_papers` calls per question | Bounds off-graph reach | 3 | same |
| `search_limit` | researcher | Hits fetched per search | Bounds each search's payload | 8 | same |
| `source_searches` | researcher | Library-retrieval calls per question | Bounds local-library reads | 5 | same |
| `figures` | researcher | `show_source_figure` calls per answer | Bounds inline images per answer | 3 | same |
| `fulltext_max_chars` | researcher | Chars per full-text read | Keeps one read from flooding the context | 8000 | same |
| `figures` | librarian | `show_source_figure` calls per answer | Same bound, librarian's tighter default | 2 | `src/atlas/agents/librarian/config.py` |

## Defaults with a parameter seam — caller decides, code holds the default

| Name | What it is | Why it's needed | Value | Referenced in |
|---|---|---|---|---|
| `_DEFAULT_RECS_POOL` | Recommendations candidate pool default | S2's `recent` pool returns zero for seeds older than ~a year, so `all-cs` is the only working default; callers pass `recent` deliberately (v6.0.0: was config `recs_pool`) | `"all-cs"` | `src/atlas/integrations/semantic_scholar/traversal.py` |
