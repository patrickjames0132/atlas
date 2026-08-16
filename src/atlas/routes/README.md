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
| `GET /api/search?q=&provider=&limit=&year_from=&year_to=&fields=` | direct search (SSE): the paper scout, run alone |
| `GET /api/taxonomy/<provider>` | a provider's field vocabulary (`s2` / `openalex`) |

Design decisions worth knowing:

- **`/api/search` is the paper scout now** (v7.6.0) — the same worker the
  researcher sends out, with the orchestration layer skipped. It replaced
  `services.search.live_search` (query-analyst expansion → verified titles →
  one lexical search), which was a second implementation of a thing the scout
  already did better: it reformulates rather than expanding once, and it
  resolves recalled titles through its own `match_title` tool. Two paths to
  one source is the bug, not the feature. `query_analyst` was retired with it.
  Skipping the *researcher* is equally deliberate: a reader who knows what
  paper they want shouldn't pay for an agent that writes prose about it.
- **It streams.** A scout run is several seconds, and a blocking response left
  the transcript blank for all of them — the reader couldn't tell a slow
  search from a dead one. The route yields a `trace` frame per lookup **as the
  scout issues it** (`on_lookup` → a thread-safe queue the generator drains
  while the agent runs on the shared loop via `streams.submit`), then one
  `result` frame, then `done`. A chip on issue says what is happening now; a
  chip on completion only reports what already happened.
- **The filters bind, and they are not prompt text.** `year_from` / `year_to`
  / `fields` go into `ScoutDeps`, so every lookup is already restricted and no
  wording the model chooses can widen them (it may narrow further inside the
  window). The same filters ride on `/api/ask` and `/api/ask_sources`
  (`routes/agents.py`'s `_opt_filters`), because they belong to the chat bar
  rather than to one of its modes — one set of filters, both destinations.
- **A pasted arXiv id/URL never reaches this route.** The frontend routes it
  straight to the graph: an id is exact, so resolving it needs a regex, not a
  model. (It used to short-circuit *inside* `live_search`; with a model on
  this path, keeping the fast path client-side is what stops a paper you
  already identified costing an agent run.)
- **Repeated lookups answer instantly** — caching moved down a layer with the
  search itself: `traversal.search` caches each query whole for a day (query +
  year window + limit + fields keyed). The scout still costs its one Haiku
  call; the provider calls behind it are free on a repeat.
- **Filters degrade, never error.** A non-numeric year becomes "no filter";
  unknown `fields` values are dropped against the **selected provider's**
  vocabulary (`services.search.valid_fields`, shared with the ask routes) — so
  an S2 field name left over after switching to OpenAlex is simply ignored.
  Blank queries return an empty `result` frame — the box starts empty; that's
  not an error.
- **A provider outage is NOT an `error` frame.** The scout degrades
  internally, so a rate-limited S2 arrives as a normal result whose `summary`
  says why (and, when the local cache has matches, with papers in it anyway).
  `error` is reserved for a genuine break, and the stream always terminates
  with `done` either way — a stream that simply stops is indistinguishable
  from one still working.
- **`/api/taxonomy/<provider>` returns one unified shape** —
  `{fields: [{id, name}]}` for both `s2` (~20 fields of study; id == name) and
  `openalex` (26 top-level fields; id == the numeric `topics.field.id`) — so the
  frontend field picker is provider-agnostic (show `name`, send `id`). Unknown
  provider → 404. (The `arxiv` taxonomy provider was retired in v5.1.0 — it fed
  the long-dead arXiv-category search filter; the detail panel's per-paper tag
  labels come from `arxiv.vocab.name_for`, not this endpoint.)

### LLM title resolution — the idea, and where it lives now

Worth keeping, because it explains a tool that otherwise looks redundant.

A lexical search fixes nothing for famous papers: "DQN" appears in no title or
abstract of the paper it names. Google resolves it anyway, because the web is
full of pages that say "DQN" and *link* to the Mnih et al. paper — Google
resolves the **association**, not the string. Claude internalized those same
associations in training: asked what paper "DQN" refers to, it names the exact
title from parametric knowledge, no retrieval needed. And both providers have
the receiving end — S2's title-match endpoint (`/paper/search/match`) and
OpenAlex's `resolve_work` — which turn a near-exact title into a paper.

The hallucination risk defuses itself: an invented title simply doesn't match,
costing one lookup and returning nothing, so the failure mode is "no better
than a plain search", never worse. Post-cutoff papers degrade the same way.

This shipped as the `query_analyst` agent, called from `live_search`. Both are
gone (v7.6.0) and the idea is now the paper scout's **`match_title` tool** —
strictly better placed, because the scout *chooses* when to spend a lookup on
a name it recognizes, instead of every query paying for a recall attempt
whether or not it names anything.

## `settings.py` — the settings modal's backend

| Endpoint | Job |
| --- | --- |
| `GET /api/settings` | the active config file's path + parsed contents |
| `PUT /api/settings` | replace the file's contents (validated first) and apply live |
| `PUT /api/settings/location` | repoint the app at another config file (`""` = default) |
| `POST /api/settings/pick` | open the OS file chooser server-side, return the picked path |
| `POST /api/settings/drop_cache` | empty the derived-data cache; returns `{removed}` |

The modal is a **config-file editor**, so the file stays the single source of
truth: PUT validates the whole body as a `Config` *before* writing anything
(a rejection returns the Pydantic field error as the 400 body and changes
nothing), then rewrites the file **in the example template's canonical key order**
(stable saves, readable diffs — Flask's default alphabetical JSON sort is
also off for the same reason) and folds the fresh values into the running
app's shared `config` object in place (`config.reload_config` — every
consumer reads fields late, so no restart). The raw file JSON is what GET
returns and PUT accepts, so values round-trip byte-for-byte. The location
endpoint validates the target file before switching the `.config-location`
sidecar (see `config.py`).

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
| `GET /api/sources/<id>/figure/<n>` | one figure mined from the source's stored PDF, as PNG |

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
| `POST /api/ask_sources` | `research` | chat with no graph open (library + search) |

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
- **Both research routes carry a `provider`.** `/api/ask` takes it from the
  graph it's grounded in; `/api/ask_sources` has no graph, so it takes the
  header dropdown's choice straight off the request. Leaving it off — as
  `ask_sources` did until v6.14.0 — doesn't leave the agent backend-less, it
  silently pins it to the default, so a chat under OpenAlex searched Semantic
  Scholar and handed back ids no OpenAlex build could resolve. Both go
  through `resolve_provider`, which degrades anything unrecognized to the
  configured default rather than erroring.
- **No availability gate on `/api/ask_sources`** (the old route 400'd when
  embeddings didn't load): retrieval self-degrades to lexical-only, and an
  empty library just means the agent's source search finds nothing — a working
  degraded feature shouldn't be refused. The sources drawer's `available`
  flag still tells the UI the semantic story.
- **SSE `error` frames carry the orchestrator's message text** — like
  `SourceError`, they're the user-facing error surface (the panel needs
  something actionable); HTTP-level errors stay canned. And the module
  logger (never `current_app.logger`): the generators run after the request
  context is gone, where touching `current_app` would kill the stream
  before the `error` frame the frontend waits for.

`drop_cache` is the one endpoint here that isn't about the config file. It
lives in this module because it is app maintenance rather than graph work, and
it is safe by construction: everything in the cache table is derived and
refetches on demand. Saved sessions are in a different store and are not
touched — a fact the UI's confirmation states outright, and a test pins.

## Who uses it, and how/why

The React frontend (Phase 6) is the only caller: the search/seed flow hits
`/api/graph`, clicking a node hydrates via `/api/paper/<ref>`, and the
detail panel lazily loads `/figures`, `/code`, and `/categories`. `<img>` tags
point at `/api/figure_proxy` URLs (both panel figures and the researcher's
inline answer figures use it). The chat bar's **Find papers** toggle streams
`/api/search`; the Filters popover loads `/api/taxonomy/<provider>` once,
lazily. (`/api/local_search` is gone — the scout reads that cache itself.)

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
