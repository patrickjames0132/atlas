# `storage`

SQLite persistence for the app. Two independent stores with two very
different lifecycles, sharing one small connection helper.

## Why it exists

arXiv Atlas fetches everything live and stores no paper corpus — but two
things still need to persist locally: a **disposable cache** of what's
already been fetched (so repeat exploration doesn't hammer Semantic
Scholar's rate limit) and **durable explorations** (a reader's own
conversations, saved automatically as they work). Same technology (SQLite),
opposite lifecycles, so they're two modules and two separate database
files.

That split is exactly why an exploration cannot simply *be* a cache row: the
cache expires after a day and Settings can wipe it outright, so a history
list backed by it would work all afternoon and then quietly empty overnight.

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
- **`sessions.py`** — the durable **exploration** store, in its own
  `sessions.db`. One table, `saved_sessions`: most of the payload is an
  opaque JSON blob (`data` — the conversation, the lectures, and a
  *reference* to the graph that was open), but a few fields (`name`,
  `seed_id`, `seed_title`, `n_nodes`) are lifted into real columns so the
  rail's list view can render without deserializing every blob.

## Design decisions worth knowing

- **An exploration stores the conversation, not the graph** (Patrick,
  2026-08-29). The blob carries a `graph_ref` — the seed reference, provider
  and layout — and reopening rebuilds the graph, instantly while the snapshot
  cache is warm and from the provider when it is not. The trade is deliberate
  and worth stating so nobody "fixes" it later: rows stay small and the chat
  history is the spine, at the cost of rate-limited calls on a cold reopen and
  a rebuilt graph that can differ from the one you left, because citation data
  moves. **The agent's discoveries are the one exception and *are* stored** —
  no cache holds them and no rebuild reproduces them, since they are a product
  of the conversation rather than of the seed.
- **Legacy blobs are read, never migrated.** Rows written before the reference
  shape carry the whole graph inline; `get_session` hands the blob back
  verbatim and the frontend uses whichever shape it finds. An old save
  therefore keeps the exact papers it was stored with, which a rebuild would
  silently swap for whatever the provider says today. `_count_nodes` reads
  both shapes for the same reason.
- **`n_nodes` is a list-view hint, not a guarantee.** For a reference-shaped
  row nothing in the process has fetched the graph, so the count is whatever
  the reference recorded plus the stored discoveries. A rebuild can come back
  a different size; nothing depends on the number being exact.
- **TTL lives with the caller, not the row.** `cache.get(key, max_age)`
  takes the freshness window as an argument each time; the table itself has
  no opinion on expiry. That's why five unrelated features can share one
  schema — "how stale is too stale" is each integration's own decision.
- **Lazy expiration, deliberately — not a gap.** Expired cache rows are
  never actively deleted; `get()` just refuses to return them past
  `max_age`. This was a specific, discussed decision: `cache.scan(prefix)`
  (which powers direct search's instant list — papers you've already
  explored) takes no age filter at all and deliberately returns stale entries
  too. Actively
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
- **`rename_session` edits metadata without rehydrating the thing it
  describes** (v7.8.0). `save_session` overwrites the whole blob, so renaming
  used to require holding the entire workspace — fine for the session you have
  open, impossible for the other twelve in a list. It moves the name in *both*
  places (the column and the copy inside the stored blob), or the next save
  would put the old one back; and it deliberately leaves `updated_at` alone,
  since the list sorts by it and renaming a session is not working on it.
- **`cache.clear()` empties the table, and is safe by construction** (v7.6.0,
  behind the settings modal's "Drop cache"). Everything in here is *derived* —
  snapshots, searches, hydration — so the worst outcome is a slower next few
  minutes. That is the whole reason a one-click button can exist, and the
  reason it lives nowhere near session deletion: a session is the only copy of
  something the reader made, and it is in a different table. `clear()` returns
  the row count it removed so the UI can report a real number rather than
  claiming success blankly.
- **A prefix scan is a *silent* reader — see `docs/bugs.md`.** `scan()` can't
  fail loudly: when the shape of a key changes under it, it doesn't raise, it
  just stops matching, and "nothing cached" is exactly what a healthy empty
  cache looks like. That is how `local_search` went blind for two releases
  after graph snapshots gained a `v2:` segment. Anything that both writes and
  prefix-scans a key must get the format from one place (graph snapshots now
  use `services.graph.snapshot_prefix`).
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
  1:1 onto the storage functions (list/save/get/rename/delete), backing the
  rail's list/restore/rename/delete UI and the autosave's writes directly.

## Testing

`test_cache.py` (11 tests) and `test_sessions.py` (11 tests) — neither had
a dedicated test file in the original app; both were previously exercised
only indirectly through whatever called them. TTL expiry is tested by
backdating rows directly via raw SQL rather than sleeping.
