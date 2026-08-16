# `src/api`

The typed client for the arXiv Atlas backend — one module per backend
concern, re-exported through the `index.ts` barrel so components import
everything from `./api`. This is the only layer that knows URLs, wire
shapes, and SSE frames; components above it deal in types.

```
api/
  sse.ts       — the shared text/event-stream reader (internal plumbing)
  agents.ts    — streaming lecture / Q&A / library chat  (routes/agents.py)
  search.ts    — direct search (SSE), field vocabulary (routes/search.py)
  graph.ts     — graph, paper detail, figures, code links, category tags (routes/graph.py)
  sessions.ts  — saved workspaces                          (routes/sessions.py)
  settings.ts  — the settings modal's config read/write     (routes/settings.py)
  sources.ts   — the local semantic library                (routes/sources.py)
  index.ts     — the barrel
```

## Design decisions worth knowing

- **Two failure philosophies, mirroring the backend routes.** Load-bearing
  calls (`fetchGraph`, `searchLive`, `getSession`, ingestion) throw with the
  server's message for the UI to surface. Niceties and fallbacks
  (`fetchFigures`, `fetchCodeLinks`, `fetchCategories`,
  `listSessions`, `getFields`) **never throw** — they degrade to
  empty/unavailable shapes so a flaky upstream can't break a panel.
  `searchLive` throws only on a genuine break: a rate-limited provider is a
  normal result whose summary says so, because the scout behind it degrades
  internally rather than failing the request.
- **One paper type everywhere.** `GraphNode` mirrors the backend's
  `services.graph.Node` and is also the shape of a direct-search hit and a
  discovered paper — graph neighbors, search results, and agent discoveries
  merge into one canvas because they are literally the same type. (The old
  app had a separate `ArxivHit` with different fields; it died with arXiv
  search.)
- **Request bodies carry FULL node shapes.** The old app sent a trimmed
  `TeacherNode` ("only what feeds the prompt"); the new backend's typed
  boundary requires the core `Node` fields and 400s otherwise. Strict
  backend, simple frontend — the payload cost at ~65 nodes is negligible.
- **Ingestion streams progress**: `uploadSource`/`ingestUrl` consume an SSE
  stream (`progress` → callback, `done` → the record, `error` → thrown with
  the server's user-facing message) instead of one long silent POST.
- **Graph builds stream progress too**: `fetchGraphStream` (used by
  `loadGraph`) reads the SSE `/api/graph/stream` endpoint the same way —
  `progress` → callback (coarse build stage), `done` → the graph, `error` →
  thrown — so the "Building graph…" overlay shows a real bar. `fetchGraph` (the
  plain GET) remains for non-streaming callers.
- **`sse.ts` exists because `EventSource` is GET-only.** The three agent
  streams are POSTs answering `text/event-stream`, so the reader hand-decodes
  frames from `fetch`. Malformed frames are skipped, never fatal; a non-OK
  response throws with the server's JSON `error` before any streaming.
- **The SSE vocabulary is the backend's event vocabulary.** Frame name =
  the typed event's `type` tag; payloads are `model_dump` shapes. Deltas
  from the old app, absorbed here so components stay oblivious:
  `nodes` frames → `discovery`; error frames carry `{message}` (was
  `{error}`); the `discard` frame is **gone** (pre-answer narration is never
  streamed, so nothing is disavowed); traces always carry their `action`
  tag. `RetrieveEvent` keeps `action` optional only so sessions saved by
  the pre-rewrite app still type-check on restore. Lecture streams carry
  beats only — lectures never expand the graph, so no trace/discovery
  frames appear (old saves' `hist_trace` field is tolerated and ignored).
- **`searchLive` streams, and its filters are promises.** It reads an SSE
  body rather than a JSON one: a `cached` frame (papers already on disk,
  instantly), `trace` frames as the scout issues each lookup, `papers` frames
  as each one lands, then the authoritative `result`. The `SearchOptions` it
  sends are enforced in the scout's deps server-side, so they cannot be
  widened by anything the model writes — which is why the same object is also
  sent on `/api/ask` (one filter set for the whole chat bar, not one per
  mode).
- **The detail-panel category tags are server-labelled.** `fetchCategories`
  hits a dedicated per-paper endpoint (`/api/paper/<ref>/categories`) that
  returns each arXiv tag already labelled, so the client does no code→name
  lookups of its own. (`getFields` — the *search* filter's vocabulary — is a
  separate concern: it fetches `/api/taxonomy/<provider>` for the selected
  provider's `{id, name}` fields. The `/api/taxonomy/arxiv` provider was retired
  in v5.1.0.)

## Who uses it, and how/why (traced from the old app; components port next)

- **`Atlas.tsx`** — `fetchGraphStream` (seed/re-seed, via the `loadGraph`
  thunk), session save/restore via `sessions.ts`.
- **`search/`** — `useDirectSearch` calls `searchLive` on submit (an SSE
  stream: `trace` frames as the scout works, then one `result`); `getFields`
  fills the filter picker once, lazily.
- **`teacher/Teacher.tsx`** — the three `agents.ts` streams; `Discovery`
  payloads flow up to the graph via `useDiscovery`.
- **`detail/DetailPanel.tsx`** — `fetchPaperDetail`, `fetchFigures`,
  `fetchCodeLinks`, `fetchCategories` on node click (lazy, degradable).
- **`library/Sources.tsx`** — `sources.ts` CRUD; **`shell/useSessions.ts`** —
  `sessions.ts` CRUD, including `renameSession` (`PATCH`), which exists
  because re-saving to change a name means holding the whole workspace blob
  and so only works for the session you have open.

## How it's verified

`tsc --noEmit` under `"strict": true` (new in the rewrite — the old frontend
never enabled strict mode; this is the TS counterpart of the backend's
strict mypy). No unit tests — this layer is thin I/O; the browser-test
milestone at the end of Phase 6 exercises it end-to-end against the real
backend.
