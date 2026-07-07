# `services`

Domain logic — the layer that composes the `integrations` clients and `storage`
into the app's actual features. A `services` function is what a `routes` HTTP
handler calls; the route does request parsing and error-to-status mapping, the
service does the real work.

Each feature is its own package; see each package's README:

- **`graph/`** — assemble a paper's neighborhood graph (`build`) and its typed
  Pydantic `Graph` model (`model`). The domain core: `/api/graph` is a thin
  wrapper over `build_graph`.
- **`search/`** — seed discovery: a live relevance search across Semantic
  Scholar plus an instant search over the local snapshot cache (`discovery`).
- **`sources/`** — the bring-your-own-sources subsystem: local ingestion,
  embedding, and hybrid (semantic + lexical) retrieval of the user's own
  uploaded PDFs and web pages.
