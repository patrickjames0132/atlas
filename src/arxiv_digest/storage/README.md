# `storage`

SQLite persistence for the app. Two independent stores with two very
different lifecycles, sharing one small connection helper.

## Why it exists

arXiv Atlas fetches everything live and stores no paper corpus — but two
things still need to persist locally: a **disposable cache** of what's
already been fetched (so repeat exploration doesn't hammer Semantic
Scholar's rate limit) and **durable saved workspaces** (a user's own graph +
chat transcript they explicitly chose to keep). Same technology (SQLite),
opposite lifecycles, so they're two modules and two separate database
files.

## How it's structured

- **`utils.py`** — a shared `connect(db_path, schema)` context manager: make
  sure the data directory exists, open the file with row-based access,
  create the schema if missing, commit on a clean exit. `cache.py` and
  `sessions.py` are both thin wrappers around it — each keeps its own local
  `_connect()` (genuinely single-file-private) that just supplies its own
  db path and schema. Extracted specifically to remove near-duplicate
  contextmanager boilerplate that used to exist independently in both
  files — not underscore-prefixed itself, since it's shared across sibling
  modules within the package.
- **`cache.py`** — a generic **key → JSON blob** TTL cache, in `digest.db`.
  Backs graph snapshots, ar5iv full text/figures, and Hugging Face code
  links — five very different features sharing one table.
- **`sessions.py`** — the durable **saved-workspace** store, in its own
  `sessions.db`. One table, `saved_sessions`: most of the payload is an
  opaque JSON blob (`data` — the whole graph + transcript), but a few
  fields (`name`, `seed_id`, `seed_title`, `n_nodes`) are lifted into real
  columns so the sessions-drawer list view can render without deserializing
  every saved session's full blob.

## Design decisions worth knowing

- **TTL lives with the caller, not the row.** `cache.get(key, max_age)`
  takes the freshness window as an argument each time; the table itself has
  no opinion on expiry. That's why five unrelated features can share one
  schema — "how stale is too stale" is each integration's own decision.
- **Lazy expiration, deliberately — not a gap.** Expired cache rows are
  never actively deleted; `get()` just refuses to return them past
  `max_age`. This was a specific, discussed decision: `cache.scan(prefix)`
  (which powers "instant search" — papers you've already explored) takes no
  age filter at all and deliberately returns stale entries too. Actively
  evicting expired rows would silently break that feature — most
  exploration history would vanish from instant search after a single day
  (the graph snapshot TTL). For a local single-user SQLite file, unbounded
  growth isn't a real concern either: `set()` upserts in place, so the
  table only grows with the number of *distinct* things ever looked at, not
  with usage volume.
- **`save_session`'s upsert preserves `created_at` via an explicit
  pre-`SELECT`**, not SQLite's "omit a column from `DO UPDATE SET` and it
  keeps its old value" upsert behavior — a simplification was considered
  and deliberately declined in favor of the more obviously-correct
  two-step version.
- **`cache.delete()` has no callers anywhere yet** — kept anyway (not
  deleted) as a natural, cheap-to-maintain piece of CRUD completeness for a
  key-value cache, and plausible for near-future use (e.g. invalidating a
  source's cached figures on re-ingest). `sessions.delete_session()`, by
  contrast, is real and used — and unlike the cache version, it *returns*
  whether anything was actually deleted, since it's user-facing (a delete
  button in the UI) rather than internal bookkeeping.

## Who uses it, and how/why

(Traced against the original app; these callers aren't ported yet, but the
mechanism carries over unchanged.)

`cache.py`:

- **`integrations/figures.py`** — caches ar5iv figure renders under
  `figures:<arxiv_id>`, TTL **30 days**. A paper's rendered figures never
  change, so a long TTL is safe — even a "no render available" result gets
  cached, so a paper without one isn't re-fetched every time its detail
  panel opens.
- **`integrations/fulltext.py`** — same pattern, `fulltext:<arxiv_id>`, and
  literally borrows figures' 30-day constant (`_FT_TTL = figures._FIG_TTL`)
  since both rest on the same assumption: ar5iv renders are static.
- **`integrations/huggingface.py`** — caches Hugging Face Papers code/
  artifact links under `hf_code:<arxiv_id>`, but only **1 day**. Unlike
  figures/fulltext, a paper's linked models/datasets/Spaces can grow at any
  time, so this needs to refresh far more often.
- **`services/graph.py`** — the big one: caches a *whole assembled graph*
  (seed + references + citations + recommendations, one JSON blob) under
  `graph:<seed_ref>`, TTL = `config.graph.cache_ttl` (1 day). This is what
  makes re-exploring a paper you've already mapped cost zero Semantic
  Scholar calls.
- **`teacher/neighbors.py`** — two uses, both backing the agentic Q&A tool
  loop: `expand:<relation>:<paper_id>` (one hop of references/citations/
  similar — the `expand_node` tool's cache, so it doesn't refetch the same
  hop twice in one session) and `search:<query>:<year_from>-<year_to>` (a
  free-text S2 search result backing the `search_papers` tool). Both share
  the graph snapshot's 1-day TTL.
- **`services/search.py`** — the odd one out: `cache.scan("graph:")` for
  "instant search," not `get()`. Scans *every* graph snapshot ever cached,
  regardless of age, to find papers you've already explored; separately
  checks each snapshot's age only to decide whether to badge it "instant"
  (fully cached neighborhood, explorable with zero API calls) versus just
  "seen before."

`sessions.py`:

- **`routes/sessions.py`** — the only caller. One Flask blueprint mapping
  1:1 onto the four storage functions (list/save/get/delete), backing the
  Sessions drawer's save/restore/delete UI directly.

## Testing

`test_cache.py` (11 tests) and `test_sessions.py` (11 tests) — neither had
a dedicated test file in the original app; both were previously exercised
only indirectly through whatever called them. TTL expiry is tested by
backdating rows directly via raw SQL rather than sleeping.
