# `src/api`

The typed client for the arXiv Atlas backend — one module per backend
concern, re-exported through the `index.ts` barrel so components import
everything from `./api`. This is the only layer that knows URLs, wire
shapes, and SSE frames; components above it deal in types.

```
api/
  sse.ts       — the shared text/event-stream reader (internal plumbing)
  agents.ts    — streaming lecture / Q&A / library chat  (routes/agents.py)
  search.ts    — live + local seed search, field vocabulary (routes/search.py)
  graph.ts     — graph, paper detail, figures, code links  (routes/graph.py)
  sessions.ts  — saved workspaces                          (routes/sessions.py)
  sources.ts   — the local semantic library                (routes/sources.py)
  index.ts     — the barrel
```

## Design decisions worth knowing

- **Two failure philosophies, mirroring the backend routes.** Load-bearing
  calls (`fetchGraph`, `searchLive`, `getSession`, ingestion) throw with the
  server's message for the UI to surface. Niceties and fallbacks
  (`fetchFigures`, `fetchCodeLinks`, `searchLocal`, `listSessions`,
  `getFields`) **never throw** — they degrade to empty/unavailable shapes so
  a flaky upstream can't break a panel or block the live search.
- **One paper type everywhere.** `GraphNode` mirrors the backend's
  `services.graph.Node` and is also the shape of a live-search hit and a
  discovered paper — graph neighbors, search results, and agent discoveries
  merge into one canvas because they are literally the same type. (The old
  app had a separate `ArxivHit` with different fields; it died with arXiv
  search.)
- **Request bodies carry FULL node shapes.** The old app sent a trimmed
  `TeacherNode` ("only what feeds the prompt"); the new backend's typed
  boundary requires the core `Node` fields and 400s otherwise. Strict
  backend, simple frontend — the payload cost at ~65 nodes is negligible.
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
  tag. `BackfillTrace`/`RetrieveEvent` keep `action` optional only so
  sessions saved by the pre-rewrite app still type-check on restore.
- **`searchLive` rides the analyst invisibly.** Free-text queries are
  expanded (and famous papers title-resolved) server-side; a pasted arXiv
  id/URL resolves to exactly that paper with filters skipped. The client
  just sees better-ordered `papers`.
- **No arXiv-categories client function yet.** The backend serves
  `/api/taxonomy/arxiv`, but nothing consumes it until the detail-panel
  category-tags feature lands — no dead exports.

## Who uses it, and how/why (traced from the old app; components port next)

- **`Atlas.tsx`** — `fetchGraph` (seed/re-seed), session save/restore via
  `sessions.ts`.
- **`search/`** — `searchLive` + `searchLocal` fan out in parallel per
  keystroke; `getFields` fills the filter picker once.
- **`teacher/Teacher.tsx`** — the three `agents.ts` streams; `Discovery`
  payloads flow up to the graph via `useDiscovery`.
- **`detail/DetailPanel.tsx`** — `fetchPaperDetail`, `fetchFigures`,
  `fetchCodeLinks` on node click (lazy, degradable).
- **`library/Sources.tsx`** — `sources.ts` CRUD; `sessions/Sessions.tsx` —
  `sessions.ts` CRUD.

## How it's verified

`tsc --noEmit` under `"strict": true` (new in the rewrite — the old frontend
never enabled strict mode; this is the TS counterpart of the backend's
strict mypy). No unit tests — this layer is thin I/O; the browser-test
milestone at the end of Phase 6 exercises it end-to-end against the real
backend.
