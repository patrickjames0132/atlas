# `services/search`

Seed discovery over the local snapshot cache.

```
search/
  discovery.py   — local_search (cache) + valid_fields (filter validation)
```

`__init__.py` re-exports both, so callers use `search.local_search(...)`
directly.

## What used to be here, and where it went (v7.6.0)

`live_search` lived here: query-analyst expansion, verified title matches,
then one lexical provider search, merged and cached whole. It is **gone**, and
so is the `query_analyst` agent it called.

The paper scout does all three jobs better. It reformulates instead of
expanding once (it can look at what came back and search again); it resolves
recalled titles through its own `match_title` tool; and it has a semantic
channel this never had. Keeping both would have left **two implementations of
"search papers"** — the same duplication the v7.0.0 worker split was made to
end, one level up. `/api/search` now runs the scout directly.

What stayed is the half the scout doesn't duplicate: reading the cache. And it
stayed as a *function*, not a route — `/api/local_search` went too, because
the scout calls `local_search` **inside** its own `search` tool. That placement
is the point: a tool is the model's to skip, a line inside the tool isn't, so
a rate-limited provider still answers from graphs already on disk without
depending on the model choosing to ask.

## `local_search`, step by step

Every whitespace token of the query is matched (case-insensitive substring)
against a cached paper's title + authors, across every graph snapshot in the
SQLite cache for the selected provider.

- **Scoped to one provider.** Snapshots are cached per provider
  (`graph:v2:<provider>:<seed>`), and only the selected backend's are scanned —
  so a paper surfaces here (and its `has_graph` "instant" flag is truthful)
  only when it can actually be explored under the provider currently selected,
  not merely because some other provider once cached it.
- **Deduped across snapshots**, keeping whichever record carries more detail
  (the same paper may appear as a bare neighbor in one snapshot and a hydrated
  seed in another).
- **Ranked**: whole-phrase title matches first, then papers explored directly
  as seeds, then by citation count.
- **Stale snapshots still match.** A paper's title doesn't expire; only the
  `has_graph` freshness flag consults the TTL.
- **Year filter yes, field filter no.** Cached nodes carry a year but no fields
  of study. That asymmetry is load-bearing upstream: the scout **skips the
  cache entirely** whenever a field filter is active, rather than returning
  hits that quietly ignore it. A filter with a hole in it is worse than no
  filter, because the UI promises it.
- **Never raises for the caller's benefit.** The scout wraps the call and
  degrades to zero cached hits on any failure — a broken cache read must not be
  able to break a working search.

## `valid_fields`

Field-filter values are provider-specific and the two vocabularies are
**disjoint** — S2 filters on its own field *names*, OpenAlex on numeric
`topics.field.id` values. So a value that survives a provider switch isn't
merely stale, it's meaningless.

`valid_fields(provider, values)` drops anything not in that provider's
vocabulary. Both routes that accept a filter use it (`/api/search` and the two
ask routes), so the same value is judged the same way whichever bar sent it.
Dropping beats forwarding now that the filter *binds* every search: one bogus
value would narrow a search to nothing while the UI still showed an active
chip.

## Who uses it

- **`agents/workers/search/papers`** — the scout's `search` tool calls
  `local_search` before every provider search.
- **`routes/search.py`** — `_opt_fields` validates the query arg through
  `valid_fields`; **`routes/agents.py`** — `_opt_filters` does the same for the
  ask routes' JSON body.

## How it's verified

`test/atlas/services/test_search.py` — `local_search` against the real SQLite
cache on the per-test temp DB (token matching, provider scoping, dedupe,
ranking, the year filter), plus `valid_fields`'s per-provider vocabulary and
its drop-the-unknown rule. The search itself is tested where it now lives:
`test/atlas/agents/workers/search/papers/test_main.py`.
