# `services.sources`

Bring-your-own sources: the user's persistent, semantically-searchable library
of their own material — uploaded PDFs/books and fetched web pages. Upload a
textbook and the teaching assistant can search it through tool use, the same way
it searches Semantic Scholar, effectively becoming an expert in that subject.

> **Naming & placement.** It's `services.sources` — a domain service (it's what
> the `/api/sources` routes and the teacher call), living beside `graph` and
> `search`. The name matches the config group (`config.sources`), the routes,
> and the "Sources" drawer. It was a top-level `library/` in the original app;
> renamed so one word means one thing, and nested under `services` where it
> belongs.

## The pipeline

```
upload/URL ─▶ extract ─▶ chunk ─▶ embed (local) ─▶ store ─┐
                                                          ▼
                       query ─▶ hybrid retrieval (semantic + lexical) ─▶ passages
```

Each source is extracted to text, split into overlapping chunks (page-aware for
PDFs so a hit can cite an exact page), **embedded locally** (no API, no key — the
text never leaves the machine, which matters for copyrighted books), and stored
in a dedicated SQLite database with a vector index. Search is **hybrid** — see
below.

## Ingestion progress

`add_source` (and the `ingest_pdf`/`ingest_url` wrappers) accept an optional
`on_progress(done, total)` callback, ticked once when chunking finishes and
then per embedding batch (`_EMBED_BATCH = 64` chunks — the encoder batches
internally anyway; this only sets how often a progress UI updates).
Embedding is where ingestion's time goes, so it's what a progress bar
should measure. The sources route bridges the callback into SSE frames.

## How it's structured

```
errors.py      — SourceError                                   (leaf)
embeddings.py  — the local sentence-transformers model (lazy, degrades)
store.py       — SQLite schema, connection, sqlite-vec + FTS5 setup, record CRUD
extract.py     — PDF/URL → clean, chunked text
ingest.py      — chunk → embed → store  (add_source, ingest_pdf, ingest_url)
retrieval.py   — the hybrid search  (search, + the two rankers and RRF)
```

Dependencies flow one way (no cycles): `store`→`embeddings`; `extract`→`errors`
+ `arxiv.html_to_text`; `ingest`→`store`+`extract`+`embeddings`;
`retrieval`→`store`+`embeddings`. `__init__` re-exports the public API
(`ingest_pdf/ingest_url/add_source/search/list_sources/get_source/delete_source/
available/SourceError`), so callers use `sources.search(...)` without reaching
into submodules.

## The two search modalities, and why we use both

The library holds each chunk two ways, indexed for two very different kinds of
matching:

- **Semantic (vector) search** — every chunk is turned into an embedding (a
  vector of numbers capturing its *meaning*), stored in a **sqlite-vec** virtual
  table. A query is embedded the same way, and we find the chunks whose vectors
  are nearest (cosine similarity, via K-nearest-neighbours). This matches on
  *meaning*: "how do I stop overfitting" can find a passage about "regularization
  and dropout" even with no shared words.
- **Lexical (keyword) search** — the counterpart, matching on the *actual words*.
  This is what **FTS5** does (below). It shines exactly where the embedder is
  weak: exact terms, proper nouns, symbols, and rare jargon (`β2`, `BM25`,
  `AdamW`) that a semantic model blurs together with their neighbours.

Neither is strictly better, so we run both and fuse the results (RRF, below).

### Semantic search — the vector (meaning) half

**What it is.** Semantic search matches on *meaning* rather than words. The idea:
a neural **embedding model** turns a piece of text into a vector — a fixed-length
list of numbers (ours is 384-long) — positioned so that texts with similar
meaning land near each other in that 384-dimensional space, even if they share no
words. "How do I stop overfitting" and "regularization and dropout reduce
generalization error" end up close together. So "find relevant passages" becomes
"find the chunk vectors nearest the query vector."

**How "nearest" is measured — cosine similarity.** Closeness here is the *angle*
between two vectors, not the distance between their tips: two vectors pointing the
same direction are maximally similar (cosine = 1) regardless of length. We
sidestep the cosine arithmetic with a trick: every vector is **L2-normalized**
(scaled to length 1) at embed time, and for unit vectors the plain dot product
*equals* the cosine. So the index only has to do fast dot products. (`embeddings`
normalizes; the table below is told the metric is cosine to match.)

**How it works here.**

- **The model runs locally** (`embeddings.py`, sentence-transformers /
  MiniLM) — no API, no key, the text never leaves the machine. It's loaded lazily
  and degrades gracefully (`store.HAS_VEC` / `embeddings.available()`); if it
  can't load, semantic search is simply skipped.
- **Vectors live in sqlite-vec.** `chunks_vec` is a `vec0` virtual table (from the
  **sqlite-vec** extension) declared `float[384] distance_metric=cosine`, holding
  one embedding per chunk. sqlite-vec is a *loadable* extension — reloaded on
  every connection (see `store.connect`), and skipped if unavailable.
- **The query gets the same treatment**, then a **KNN** (k-nearest-neighbours)
  lookup pulls the `k` closest chunk vectors: `WHERE embedding MATCH ? AND k = ?`,
  ordered by distance. Those chunk ids join back to `chunks`/`sources` for the
  text. (`retrieval._vector_search`.)
- **Asymmetric models** (not our default) want a query prefixed with an
  instruction while stored passages stay bare — `embed_query` prepends
  `config.sources.embedding.query_prefix` (empty for MiniLM) to cover that.

The weakness this has — exact terms, proper nouns, and rare symbols that the
model blurs into their neighbours — is exactly FTS5's strength, which is why we
run both.

### FTS5 — the lexical (keyword) search

**What it is.** FTS5 is SQLite's built-in **F**ull-**T**ext **S**earch engine
(version 5). It's the "search the actual words" half of retrieval — a classic
inverted-index keyword search, ranked by **BM25** (the standard relevance
formula behind most keyword search engines: a term matters more when it's rare
across the corpus but frequent in a given passage, with a dampener for very long
passages). FTS5 is a *compile-time* option in SQLite, so it may or may not be
present in a given build — we probe once (`store.HAS_FTS`) and skip lexical
search entirely if it's missing.

**How it works here.**

- **The index tracks a real table.** `chunks_fts` is an FTS5 *external-content*
  table: it doesn't store its own copy of the text, it indexes the `text` column
  of the ordinary `chunks` table. Two triggers (`AFTER INSERT` / `AFTER DELETE`
  on `chunks`) keep the index in sync automatically, so ingestion and deletion
  need no extra wiring — insert a chunk and it becomes searchable; delete a
  source and its words vanish from the index. (`store.py`'s `_FTS_SCHEMA`.)
- **The tokenizer is `porter unicode61`.** `unicode61` splits Unicode text into
  word tokens (so `β2` survives); the `porter` stemmer folds words to their root,
  so a search for "optimizing" also matches "optimizer" / "optimized".
- **Queries are sanitized first** (`retrieval._fts_match_query`). FTS5 has its
  own little query *grammar* — bare punctuation and the words `AND`/`OR`/`NEAR`
  are operators, so feeding it a raw natural-language question
  (`"What's the Adam optimizer's β2?"`) can throw a syntax error. We extract just
  the word tokens and OR them together as quoted string literals
  (`"What" OR "s" OR "the" OR "Adam" …`) — a safe, forgiving "any of these terms"
  match that never trips the grammar. Ranked by `bm25()`, best first.

### RRF — fusing the two rankings

**The problem.** We now have two ranked lists of chunks — one from vector search
(scored by cosine distance) and one from FTS5 (scored by BM25). Their scores live
on **completely different scales** that aren't comparable, so you can't just add
them. Normalizing the two scales into a common range is fiddly and fragile.

**Reciprocal Rank Fusion (RRF)** sidesteps that entirely by throwing the scores
away and using only each chunk's **rank** (its 1-based position) in each list.
Each list contributes to a chunk's fused score:

```
score(chunk) = Σ over lists of   1 / (rrf_k + rank_in_that_list)
```

- A chunk near the **top** of a list (small rank) contributes a lot; one near the
  bottom contributes little. A chunk absent from a list contributes nothing from
  it.
- A chunk that both rankers rank highly gets contributions from *both* and rises
  to the top — so **agreement between semantic and lexical is rewarded**, which
  is exactly the signal we want.
- **`rrf_k`** (we use **60**, the value from the original RRF paper) is a damping
  constant. Larger `rrf_k` flattens the difference between ranks (rank 1 vs rank 2
  matters less); smaller sharpens it. 60 is a well-tested default.

Only ranks matter, so no score normalization is ever needed — that's the whole
appeal. (`retrieval._rrf_fuse`.)

## Graceful degradation

Nothing here is a hard dependency; the subsystem narrows instead of crashing:

| available | behaviour |
|---|---|
| embedder + sqlite-vec + FTS5 | full hybrid search |
| FTS5 missing (or `hybrid` off) | pure semantic (vector) search |
| embedder/sqlite-vec missing | lexical-only search |
| neither | `search()` returns `[]` |

Ingestion requires the embedder + sqlite-vec (there's nothing to store a vector
in otherwise), and raises `SourceError` with a clear message when they're
missing. `available()` reports the full-capability state up front.

## Design decisions worth knowing

- **Local embeddings, on purpose.** Chunks are embedded with a local
  sentence-transformers model, never an API — the text (which may be a
  copyrighted book) never leaves the machine.
- **Its own connection helper**, not the shared `storage.connect`. This DB needs
  per-connection extension loading (sqlite-vec), capability probing, and
  conditional virtual-table creation that the generic helper doesn't do.
- **Character-based chunking.** Cheap and model-agnostic, but it must respect the
  embedder's token limit (MiniLM truncates at ~1000 chars) — see
  `config.sources.chunking`.
- **`html_to_text` is borrowed from the `arxiv` package.** `extract.fetch_url` is
  its one non-arXiv consumer; not worth extracting into a standalone module for a
  single caller, so it's imported as-is.
- **Over-fetch when scoped.** A scoped search over-fetches each ranker 8× so the
  `source_id` filter can still yield `k` hits from the chosen subset (and gives
  RRF a deeper pool).

## Who uses it, and how/why (traced, not yet ported)

- **`teacher/tools.py`** — the `search_sources` agent tool calls `search()`; an
  uploaded textbook becomes a searchable knowledge source the assistant can cite.
- **`teacher/sources_chat.py`** — the graph-free "chat with your sources" mode
  retrieves passages via `search()` and answers grounded in them.
- **`routes/sources.py`** — the `/api/sources` CRUD endpoints (`ingest_pdf` /
  `ingest_url` / `list_sources` / `delete_source`).
- **`cli.py`** — `ingest` / `sources` / `search-sources` commands.

## Testing

`test_extract.py` — `chunk_text` (overlap, space-breaking, whitespace) and
`extract_pdf` against **real in-memory PDFs** built with pymupdf (including the
scanned/image-only rejection). `test_ingest.py` — the full ingest→search
pipeline and multi-source scope semantics, on the `stub_embeddings` hash embedder
(no torch) with real sqlite-vec. `test_retrieval.py` — the FTS5 query sanitizer
and RRF fusion as pure functions, plus the lexical path and FTS-purge-on-delete
driven through the real `search()` with the vector side stubbed off. All offline;
the FTS tests skip cleanly if FTS5 isn't compiled into the SQLite build.
