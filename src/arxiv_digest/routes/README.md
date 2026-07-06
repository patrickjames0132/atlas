# `routes`

The Flask API surface: one blueprint per concern, wired onto the app by
`register_blueprints` (called from the app factory). Every route carries its
full `/api/...` path — no blueprint URL prefixes — so the registry order is
cosmetic. Being ported module by module (Phase 5): **graph** is in;
search, sessions, sources, and agents follow.

Route modules are thin: parse/validate the request, call one service or
integration, map its outcomes onto HTTP. Anything thicker belongs a layer
down.

## `graph.py` — the canvas and the detail panel

| Endpoint | Job |
| --- | --- |
| `GET /api/graph?seed=&refresh=` | build (or re-fetch) a seed's neighborhood graph |
| `GET /api/paper/<ref>` | hydrate one paper's details for the panel |
| `GET /api/paper/<ref>/figures` | the paper's ar5iv figures, proxied |
| `GET /api/paper/<ref>/code` | Hugging Face code & artifact links |
| `GET /api/figure_proxy?src=` | same-origin relay for ar5iv images |

Design decisions worth knowing:

- **Two failure philosophies, on purpose.** The load-bearing endpoints
  (graph, paper) map failures to real HTTP: 400 (no seed), 404 (S2 knows no
  such paper), 502 (S2 down, with a user-facing "try again"). The panel
  niceties (figures, code) instead degrade to `available: false` on ANY
  upstream failure — a missing figure strip must never 500 the panel.
- **`normalize_arxiv_id` extracts; `looks_arxiv` discriminates.** The entry
  filter uses `ID_RE.search` to pull an id out of pasted text (URL-wrapped,
  version-suffixed, whatever); the S2 lookup then uses
  `arxiv.looks_arxiv()` (`fullmatch`) to decide whether the `ARXIV:` prefix
  applies. The old route prefixed unconditionally — which broke panel
  hydration for papers that exist on S2 but not on arXiv (their nodes
  hydrate by raw paperId). Fixed in this port, mirroring `build_graph`.
- **`/api/graph` serializes the typed `Graph`** via `model_dump()` — the
  route is the model-to-JSON boundary (Phase 3 decision: the graph is a
  Pydantic model everywhere inside the app).
- **The figure proxy is an SSRF chokepoint.** `is_ar5iv_url` allowlists the
  ar5iv host before any fetch, so `/api/figure_proxy` can't be used as an
  open relay; responses carry a day-long `Cache-Control`. This is the
  same-origin contract behind both the detail panel's figure strip and the
  tutor's `show_figure` payloads.

## Who uses it, and how/why

The React frontend (Phase 6) is the only caller: the search/seed flow hits
`/api/graph`, clicking a node hydrates via `/api/paper/<ref>`, and the
detail panel lazily loads `/figures` and `/code`. `<img>` tags point at
`/api/figure_proxy` URLs (both panel figures and the tutor's inline answer
figures use it).

## Testing

`test_graph.py` drives every endpoint through a real test client built from
`register_blueprints` (`conftest.py`), with services/integrations
monkeypatched at the route module's seams: URL/version normalization
reaching the service, the 400/404/502 taxonomy, prefix-vs-raw paperId
lookups, proxy rewriting + degradation of the niceties, and the SSRF lock.
