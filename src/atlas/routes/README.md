# `routes`

The Flask API surface: one blueprint per concern, wired onto the app by
`register_blueprints` (called from the app factory). Every route carries its
full `/api/...` path — no blueprint URL prefixes — so the registry order is
cosmetic.

Route modules are thin: parse/validate the request, call one service or
integration, map its outcomes onto HTTP. Anything thicker belongs a layer
down.

## `graph.py` — the canvas and the detail panel

| Endpoint | Job |
| --- | --- |
| `GET /api/graph?seed=&refresh=` | build (or re-fetch) a seed's neighborhood graph |
| `GET /api/graph/stream?seed=&refresh=` | same, as SSE with coarse build-stage progress |
| `GET /api/paper/<ref>` | hydrate one paper's details for the panel |
| `GET /api/paper/<ref>/figures` | the paper's figures — ar5iv, else floats mined from its OA PDF |
| `GET /api/paper/<ref>/code` | Hugging Face code & artifact links |
| `GET /api/paper/<ref>/categories` | the paper's own arXiv category tags |
| `GET /api/pdf_figure/<token>/<n>` | one mined PDF float, rendered to PNG |
| `GET /api/figure_proxy?src=` | same-origin relay for ar5iv images |

Design decisions worth knowing:

- **Two failure philosophies, on purpose.** The load-bearing endpoints
  (graph, paper) map failures to real HTTP: 400 (no seed), 404 (S2 knows no
  such paper), 502 (S2 down, with a user-facing "try again"). The panel
  niceties (figures, code) instead degrade to `available: false` on ANY
  upstream failure — a missing figure strip must never 500 the panel.
- **`/api/graph/stream` is the determinate-progress twin of `/api/graph`.**
  Same result, delivered as SSE so the frontend overlay shows a real filling
  bar instead of a bare spinner. `build_graph` reports five coarse stages
  through an `on_progress` callback; `_build_stream` runs it in a worker thread
  and bridges each callback onto a queue the generator drains into
  `progress`/`done`/`error` frames — the exact pattern `sources.py` uses for
  ingestion. Two consequences fall out of the streaming shape: (1) build
  failures surface as `error` **frames**, not HTTP status (the connection is
  already 200/streaming by then), so only a *missing seed* is still a pre-stream
  400; (2) the generator and its worker must use the **module logger**, never
  `current_app` — they run after the request context is gone (see `sse.py`).
  A cache hit fires no `progress` frames (`build_graph` returns before the first
  stage), so the stream jumps straight to `done`. The blocking `GET /api/graph`
  stays for compatibility and non-streaming callers.
- **`normalize_arxiv_id` extracts; `looks_arxiv` discriminates.** The entry
  filter uses `ID_RE.search` to pull an id out of pasted text (URL-wrapped,
  version-suffixed, whatever); the S2 lookup then uses
  `arxiv.looks_arxiv()` (`fullmatch`) to decide whether the `ARXIV:` prefix
  applies. The old route prefixed unconditionally — which broke panel
  hydration for papers that exist on S2 but not on arXiv (their nodes
  hydrate by raw paperId). Fixed in this port, mirroring `build_graph`.
- **Why arXiv ids at all, when the data all comes from S2?** Because the
  arXiv id is how *humans* hand us papers — recognizing it is input
  handling, not an arXiv dependency. The chain: (1) **paste-recognition** —
  the dominant flow for ML papers is copying `arxiv.org/abs/...` from a
  browser or a tweet; unrecognized, that string would fall through to S2's
  lexical search as junk keywords and find nothing, while a recognized id
  is a statement of intent that skips search and lands on that exact paper.
  (2) **S2 addressing** — S2's own lookup API takes `ARXIV:<id>` as an
  external identifier, so normalization is just translating the reference a
  human gave us into the key S2 wants (accepting an ISBN without being a
  printing press). The version strip belongs here too: `v5` and `v2` are
  the same paper to S2 and to our cache keys. (3) **ar5iv rendering** —
  a node's `arxiv_id` is the ticket to figures and full text. (4) the arXiv
  **category tags** (`/api/paper/<ref>/categories`) — S2 doesn't carry a
  paper's own category codes, so this is the one detail-panel field arXiv's
  metadata (not S2) supplies. Retiring arXiv *search* removed none of these.
- **`/api/graph` serializes the typed `Graph`** via `model_dump()` — the
  route is the model-to-JSON boundary (Phase 3 decision: the graph is a
  Pydantic model everywhere inside the app).
- **The figure proxy is an SSRF chokepoint.** `is_ar5iv_url` allowlists the
  ar5iv host before any fetch, so `/api/figure_proxy` can't be used as an
  open relay; responses carry a day-long `Cache-Control`. This is the
  same-origin contract behind both the detail panel's figure strip and the
  researcher's `show_figure` payloads. Its figure-manifest sibling
  `/api/pdf_figure/<token>/<n>` holds the same posture a different way: the
  browser sends an opaque token (minted server-side when a PDF was mined,
  resolved through the cache's `pdfurl:` registry), never a URL — unknown
  tokens simply 404.
- **`/api/paper/<ref>/figures` chains two sources.** The ar5iv render (real
  `<figcaption>`s) when the paper has one; else the paper's open-access PDF
  is fetched and mined (`services/pdf` — caption-anchored figures, tables,
  and algorithm boxes). An arXiv ref falls back to `arxiv.org/pdf` directly;
  a non-arXiv ref resolves its OA URL through the `provider` query arg's
  backend, which paper hydration usually pre-primed.
- **`/api/paper/<ref>/categories` is a panel nicety, not load-bearing** —
  same degrade-to-`available: false` contract as figures/code (a bad id, a
  raw S2 paperId with no arXiv metadata, or an arXiv outage all look the
  same to the frontend). Labels each code via `arxiv.vocab.name_for`.

## `search.py` — finding a seed paper

| Endpoint | Job |
| --- | --- |
| `GET /api/search?q=&provider=&limit=&year_from=&year_to=&fields=` | live seed search (s2 / openalex) |
| `GET /api/local_search?q=&provider=&limit=&year_from=&year_to=` | instant search over the local snapshot cache |
| `GET /api/taxonomy/<provider>` | a provider's field vocabulary (`s2` / `openalex`) |

Design decisions worth knowing:

- **`/api/search` replaced `/api/arxiv_search`** when seed search moved to
  S2 (wider coverage: 200M+ papers across venues, not just arXiv
  preprints). Papers come back as S2 node dicts — the same shape as graph
  nodes, and the same shape `local_search` returns.
- **A pasted arXiv id/URL short-circuits inside the service** (`live_search`):
  detected id → exact `ARXIV:<id>` lookup, skipping query expansion (an id
  isn't vocabulary — an "improved" id could only be a wrong one) *and* the
  filters (they never apply to an explicit lookup). The query analyst fires
  only on real free-text queries — and only while it's switched on:
  `analyst=0/false/no` (the search bar's Options checkbox) skips the LLM
  and searches the words as typed. An id S2 doesn't know returns nothing
  rather than falling through to a junk lexical search of the id text.
- **Repeated queries answer instantly** — `live_search` caches its results
  whole for a day (query + filters + analyst flag keyed), so re-typing a
  recent query skips the analyst and S2 entirely (see
  `services/search/README.md`).
- **Filters degrade, never error.** A non-numeric year becomes "no filter";
  unknown `fields` values are silently dropped against the **selected
  provider's** vocabulary (`semantic_scholar.vocab.valid_fields()` for s2,
  `openalex.vocab.valid_field_ids()` for openalex) — so an S2 field name left
  over after switching to OpenAlex is simply ignored. Blank queries return an
  empty 200 — the box starts empty; that's not an error.
- **Two error philosophies again:** `/api/search` maps S2 failure to a
  canned 502 (details in the log, matching `graph.py` — the old route
  leaked `str(exc)` to the client); `/api/local_search` **never errors** —
  it degrades to zero hits, because the instant local results must not
  block the live search running alongside them.
- **`/api/taxonomy/<provider>` returns one unified shape** —
  `{fields: [{id, name}]}` for both `s2` (~20 fields of study; id == name) and
  `openalex` (26 top-level fields; id == the numeric `topics.field.id`) — so the
  frontend field picker is provider-agnostic (show `name`, send `id`). Unknown
  provider → 404. (The `arxiv` taxonomy provider was retired in v5.1.0 — it fed
  the long-dead arXiv-category search filter; the detail panel's per-paper tag
  labels come from `arxiv.vocab.name_for`, not this endpoint.)

### LLM title resolution

Query expansion fixes the *vocabulary* gap ("DQN" → "…deep Q-network…"),
but there's a stronger play for famous papers. Google resolves "DQN"
straight to the Mnih et al. paper because the web is full of pages that say
"DQN" and link to it — Google resolves the *association*, not the string.
Claude internalized those same associations in training: asked what paper
"DQN" refers to, it names the exact titles from parametric knowledge — no
retrieval, no built-in RAG needed (a bare API call retrieves nothing;
Anthropic's opt-in web-search tool would be real grounding but is
latency/cost overkill per keystroke). And S2 has the perfect receiving end:
a **title-match endpoint** (`/paper/search/match`) that resolves a
near-exact title to a paper. So the mechanics: the analyst's structured
output is `Expansion{expanded_query, known_titles}` ("name the papers this
query most likely refers to *only if confident*") — still one Haiku call —
and `live_search` runs: pasted id? → exact lookup → **known titles? →
S2 title-match, verified hits lead** → expanded lexical search (deduped
against the verified hits, capped at `limit` together). The
hallucination risk defuses itself: an invented title simply doesn't match
on S2 and we fall back to the lexical search we'd have run anyway — the
failure mode is "no better than today," never worse. Post-cutoff papers
degrade to plain expansion the same way.

## `sessions.py` — saved workspaces

| Endpoint | Job |
| --- | --- |
| `GET /api/sessions` | list saved sessions (metadata only, newest first) |
| `POST /api/sessions` | save the workspace (new, or overwrite by `id`) |
| `GET /api/sessions/<id>` | the full record, to restore |
| `DELETE /api/sessions/<id>` | delete — `{deleted: bool}`, idempotent |

Thin CRUD over `storage/sessions.py`. The workspace blob (`{name, seed,
layout, nodes, edges, chat, beats}`) is **frontend-owned and deliberately
unvalidated** beyond `nodes` being a non-empty list — the store treats it
as opaque JSON, and validating its shape here would create a second place
that has to track the frontend's workspace format. (Old saves may carry a
`hist_trace` field from the retired lecture backfill; it's simply ignored
on restore.) Delete returns `{deleted: false}` rather than 404
(idempotent); a store failure is a canned 500 with details in the log.

## `sources.py` — the local library

| Endpoint | Job |
| --- | --- |
| `GET /api/sources` | list the library + the `available` flag |
| `POST /api/sources` | ingest a PDF upload or a `{url}`, streaming SSE progress |
| `DELETE /api/sources/<id>` | remove a source — `{deleted: bool}`, idempotent |

Thin wrappers over `services/sources`. Points worth knowing:

- **`available` explains a disabled state.** The list response reports
  whether local embeddings + sqlite-vec loaded, so the UI can say *why*
  semantic search is off; the check itself degrades to `False` on any
  error. This endpoint is where the lazy torch load happens — deliberate:
  the sources drawer is the UI's "is semantic search on" indicator (the
  researcher, by contrast, never probes).
- **Two-tier error contract.** `SourceError` text goes to the client
  verbatim as a 400 — those messages are *written for users* by the
  ingestion layer ("no extractable text — is it scanned?"). Anything
  unexpected is a canned 500, details in the log only.
- **Ingestion streams progress** (browser-milestone addition): `progress`
  frames carry `{done, total}` chunks embedded — embedding is where the
  time goes — then `done` (the stored record) or `error`. The pipeline is
  synchronous, so a worker thread runs it and a queue bridges its progress
  callback into the SSE generator. Everything request-scoped (the upload's
  temp file, the parsed URL) happens *before* streaming starts — the
  generator outlives the request context (see `routes/sse.py`, the shared
  SSE helpers promoted from `agents.py` when this second consumer arrived).
- **Temp-file hygiene on upload:** `mkstemp` + close the fd *before*
  `upload.save()` (on Windows an open handle holds an exclusive lock),
  removal in a `finally`.

## `agents.py` — the teacher's SSE endpoints

| Endpoint | Intent | Job |
| --- | --- | --- |
| `POST /api/lecture` | `lecture` | streamed lecture over the visible graph |
| `POST /api/ask` | `research` | agentic Q&A over the graph |
| `POST /api/ask_sources` | `librarian` | offline library chat |

(The route face of the `agents` package — a deliberate name-cousin,
different full paths.) Each endpoint validates, builds typed inputs, and
hands off to `orchestrator.run(intent, ...)`; one `_relay` generator
serializes the typed event stream as SSE.

Design decisions worth knowing:

- **One serialization rule replaces six tuple matches.** Frame name = the
  event's `type` tag, payload = `model_dump(exclude={"type"})`. That
  reproduces the old wire shapes for `token`/`beat`/`cited`/`trace`/`done`
  exactly, with the two documented renames (`nodes` → `discovery`,
  error `{"error"}` → `{"message"}`); `discard` is gone (nothing to disavow
  — the researcher's pre-answer narration is never streamed).
- **The typed-node boundary.** `orchestrator.run` takes `Node` models; the
  frontend sends dicts that the force-graph renderer has mutated with
  simulation fields (`x`, `vy`, `index`, ...). `_node` picks exactly the
  model's fields out of each dict — strict about the core shape (missing
  fields → 400), tolerant about baggage.
- **History lives here, not in the agents** (locked Phase 4 decision). Two
  in-memory stores — graph chat and library chat, same `session_id` never
  cross-contaminates — persisted **only on success** (a failed answer must
  not poison the follow-up context), `<<FIG n>>` markers stripped (render
  directives, not conversation content), trimmed to
  `config.server.history_turns` pairs.
- **No availability gate on `/api/ask_sources`** (the old route 400'd when
  embeddings didn't load): retrieval self-degrades to lexical-only, and an
  empty library gets the librarian's friendly no-hits answer — a working
  degraded feature shouldn't be refused. The sources drawer's `available`
  flag still tells the UI the semantic story.
- **SSE `error` frames carry the orchestrator's message text** — like
  `SourceError`, they're the user-facing error surface (the panel needs
  something actionable); HTTP-level errors stay canned. And the module
  logger (never `current_app.logger`): the generators run after the request
  context is gone, where touching `current_app` would kill the stream
  before the `error` frame the frontend waits for.

## Who uses it, and how/why

The React frontend (Phase 6) is the only caller: the search/seed flow hits
`/api/graph`, clicking a node hydrates via `/api/paper/<ref>`, and the
detail panel lazily loads `/figures`, `/code`, and `/categories`. `<img>` tags
point at `/api/figure_proxy` URLs (both panel figures and the researcher's
inline answer figures use it). The search box fans out to `/api/local_search`
(instant) and `/api/search` (live) in parallel; the filter picker loads
`/api/taxonomy/s2` once.

## Testing

`test_graph.py` and `test_search.py` drive every endpoint through a real
test client built from `register_blueprints` (`conftest.py`), with
services/integrations monkeypatched at the route module's seams: URL/version
normalization reaching the service, the 400/404/502 taxonomy,
prefix-vs-raw paperId lookups, proxy rewriting + degradation of the
niceties, the SSRF lock, filter parsing/validation and clamps, the
never-error local search, and the taxonomy providers' shapes. The pasted-id
short-circuit is service-level behavior, tested in
`services/test_search.py`.
