# `services`

Domain logic — the layer that composes the `integrations` clients and `storage`
into the app's actual features. A `services` function is what a `routes` HTTP
handler calls; the route does request parsing and error-to-status mapping, the
service does the real work.

Each feature is its own package; see each package's README:

- **`graph/`** — assemble a paper's neighborhood graph (`build`), its typed
  Pydantic `Graph` model (`model`), and the adaptive landmark-budget model
  serving (`budget`). The domain core: `/api/graph` is a thin wrapper over
  `build_graph`.
- **`search/`** — seed discovery: a live relevance search across Semantic
  Scholar plus an instant search over the local snapshot cache (`discovery`),
  and the composer's `@`-mention lookup — its merge/rank helpers in
  `discovery`, and in `naming` the resolution of an informal paper name
  ("DQN") to the paper itself. **`naming` is the one module here that reaches
  into `agents/`**, and it does so through a function-local import for that
  reason: nothing else in `services/` depends on the agent tier, and a
  top-level import would make every consumer of the search service construct
  an agent. It is there because the mapping from a nickname to a title is
  world knowledge that no text match can supply — see its own docstring for
  the measurements.
- **`sources/`** — the bring-your-own-sources subsystem: local ingestion,
  embedding, and hybrid (semantic + lexical) retrieval of the user's own
  uploaded PDFs and web pages.
- **`pdf/`** — open-access PDF mining for papers ar5iv can't serve: resolve
  a paper's OA-PDF URL (either provider), download/cache the file, and
  extract full text plus caption-anchored figures/tables/algorithms for the
  detail panel and the researcher's full reads.
