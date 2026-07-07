# `integrations.huggingface`

A paper's code & artifact links from [Hugging Face Papers](https://huggingface.co/papers).

## Why it exists

Papers with Code sunset into Hugging Face Papers, so HF is now the place that
maps an arXiv id to runnable implementations: a community-linked GitHub repo,
plus the models, datasets, and Spaces that cite the paper. This is what powers
the detail panel's "code & artifacts" section — one call to
`https://huggingface.co/api/papers/{arxiv_id}` returns all of it.

## How it's structured

We use the **official `huggingface_hub` client** (`HfApi.paper_info`) rather
than hand-rolling the HTTP call. It's already in the dependency tree via
`sentence-transformers`, and an official client buys us typed results and
resilience to HF's API shape changing. A single-service, single-shape client,
still split into a package with the same transport-vs-domain shape as `arxiv` /
`semantic_scholar` so all the `integrations` packages read alike:

```
client.py     — fetch_paper: HfApi.paper_info + 404-as-None; BASE_URL, CODE_TTL
     ↓
code_links.py — normalizes the typed PaperInfo into the detail-panel envelope
```

- **`client.py`** — holds one `HfApi` handle and exposes `fetch_paper()`, which
  calls `paper_info(arxiv_id)` and translates a 404 (`HfHubHTTPError` with a
  404 response) into `None` (the "no such paper" miss `code_links` expects).
  Also `BASE_URL` (used by `code_links` to build item/page URLs) and the
  `CODE_TTL` cache lifetime.
- **`code_links.py`** — `get_code_links()` (the public entry point: cache
  lookup, fetch on miss, normalize, cache the result including a miss), backed
  by `empty_result()` (the zero-value envelope) and the private normalizers
  `_as_int()` / `_repo_items()`. Because `PaperInfo` and its `ModelInfo` /
  `DatasetInfo` / `SpaceInfo` items are typed, normalization is plain attribute
  access — no defensive dict-digging.

`__init__.py` re-exports `get_code_links` and `empty_result`.

## Design decisions worth knowing

- **We depend on `huggingface_hub` explicitly** even though
  `sentence-transformers` already pulls it in transitively — the marginal
  install cost is zero, and relying on a transitive dependency for a direct
  import is fragile.
- **No `config.s2.timeout` borrow.** The original hand-rolled version reused
  Semantic Scholar's timeout for its HTTP call (a documented quirk, shared with
  `ar5iv`). The library owns HTTP now, so that quirk is simply gone.
- **A miss is cached too**, same pattern as `ar5iv`: a paper HF has never
  indexed (`fetch_paper` → None) gets `{"available": False, ...}` cached for a
  day, so it costs one request a day rather than one per detail-panel open.
- **`empty_result()` is public** (not `_empty` as in the original) —
  `routes/graph.py` (not yet ported) reaches for it directly as a fallback when
  the main lookup fails unexpectedly, so it's genuinely cross-module, not
  single-file-private.
- **`_repo_items()` caps at 5 items per kind** (`_MAX_ITEMS`) — the `totals`
  dict still reports the *real* total count HF knows about, so the detail panel
  can show "254 models" even though only 5 are listed.
- **The spaces total is read under two names.** `paper_info` normalizes
  `num_total_models` / `num_total_datasets` but leaves the spaces total under
  the raw camelCase `numTotalSpaces` — a library inconsistency `code_links`
  papers over by looking under both keys.

## Who uses it, and how/why (traced, not yet ported)

- **`routes/graph.py`** — `GET /api/paper/<id>/code`, the detail panel's code &
  artifacts section, calls `get_code_links(arxiv_id)`. It wraps the call in a
  bare `except Exception` (deliberately broad — "HF down/slow, degrade
  gracefully, don't 500 the panel") and falls back to
  `huggingface.empty_result()` directly when something goes wrong, which is
  exactly why that function is public rather than private.

## Testing

`test_client.py` — `fetch_paper` transport: the happy path plus the
404-as-None / non-404-reraise translation, with the `HfApi` handle faked (a
stand-in whose `paper_info` returns a canned result or raises `HfHubHTTPError`).
`test_code_links.py` — envelope normalization (full / sparse / non-GitHub-URL),
empty-id, `empty_result()` shape, and caching (miss cached, hit cached,
`refresh` bypasses), with `client.fetch_paper` faked to return `SimpleNamespace`
stand-ins for `PaperInfo` and its items. No test touches the network.
