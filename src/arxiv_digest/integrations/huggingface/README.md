# `integrations.huggingface`

A paper's code & artifact links from [Hugging Face Papers](https://huggingface.co/papers).

## Why it exists

Papers with Code sunset into Hugging Face Papers, so HF is now the place that
maps an arXiv id to runnable implementations: a community-linked GitHub repo,
plus the models, datasets, and Spaces that cite the paper. This is what powers
the detail panel's "code & artifacts" section — one call to
`https://huggingface.co/api/papers/{arxiv_id}` returns all of it.

## How it's structured

A single-service, single-shape client — smaller than `ar5iv` (two genuinely
different extractions from the same render) or `semantic_scholar` (several
distinct endpoint families). It's still split into a package, the same
transport-vs-domain shape as those, so all the `integrations` packages read
alike:

```
client.py     — fetch_paper (the one HTTP call), HF_HOST / BASE_URL, CODE_TTL
     ↓
code_links.py — normalizes HF's response into the detail-panel envelope
```

- **`client.py`** — `fetch_paper()` (the raw `/api/papers` fetch, 404-as-None),
  plus `HF_HOST` / `BASE_URL` and the `CODE_TTL` cache lifetime. `BASE_URL` is
  package-public here (`code_links` builds item URLs against it) — exactly like
  ar5iv's `client.BASE_URL`. (In the original single-file version the host was
  private, because nothing referenced it across a boundary; splitting the
  package *created* that boundary, so it's legitimately public now.)
- **`code_links.py`** — `get_code_links()` (the public entry point: cache
  lookup, fetch on miss, normalize, cache the result including a miss), backed
  by `empty_result()` (the zero-value envelope) and the private normalizers
  `_as_int()` / `_repo_items()`.

`__init__.py` re-exports `get_code_links` and `empty_result`.

## Design decisions worth knowing

- **A miss is cached too**, same pattern as `ar5iv`: a paper HF has never
  indexed (`fetch_paper` → None) gets `{"available": False, ...}` cached for a
  day, so it costs one request a day rather than one per detail-panel open.
- **`empty_result()` is public** (not `_empty` as in the original) —
  `routes/graph.py` (not yet ported) reaches for it directly as a fallback when
  the main lookup fails unexpectedly, so it's genuinely cross-module, not
  single-file-private.
- **Reuses `config.s2.timeout`** for its HTTP call — the same pre-existing
  quirk as `ar5iv` (a Semantic Scholar setting borrowed for an unrelated
  external service). Left as-is rather than inventing a new per-service config
  field with no documented need yet.
- **`_repo_items()` caps at 5 items per kind** (`_MAX_ITEMS`) — the `totals`
  dict still reports the *real* total count HF knows about, so the detail panel
  can show "254 models" even though only 5 are listed.

## Who uses it, and how/why (traced, not yet ported)

- **`routes/graph.py`** — `GET /api/paper/<id>/code`, the detail panel's code &
  artifacts section, calls `get_code_links(arxiv_id)`. It wraps the call in a
  bare `except Exception` (deliberately broad — "HF down/slow, degrade
  gracefully, don't 500 the panel") and falls back to
  `huggingface.empty_result()` directly when something goes wrong, which is
  exactly why that function is public rather than private.

## Testing

`test_client.py` — `fetch_paper` transport: JSON decode, non-object-as-None,
404-as-None, non-404 reraise, and slash-id path encoding (`urllib.request.urlopen`
faked). `test_code_links.py` — envelope normalization (full / sparse-with-junk /
non-GitHub-URL), empty-id, `empty_result()` shape, and caching (miss cached, hit
cached, `refresh` bypasses), with `client.fetch_paper` faked at the module
boundary so no test touches the network.
