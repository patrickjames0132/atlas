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
- **Why arXiv ids at all, when the data all comes from S2?** Because the
  arXiv id is how *humans* hand us papers — recognizing it is input
  handling, not an arXiv dependency. The chain: (1) **paste-recognition** —
  the dominant flow for ML papers is copying `arxiv.org/abs/...` from a
  browser or a tweet; unrecognized, that string would fall through to S2's
  lexical search as junk keywords and find nothing, while a recognized id
  is a statement of intent that skips search and lands on that exact paper.
  (2) **S2 addressing** — S2's own lookup API takes `ARXIV:<id>` as an
  external identifier, so normalization is just translating the reference a
  human gave us into the key S2 wants (accepting an ISBN without being a
  printing press). The version strip belongs here too: `v5` and `v2` are
  the same paper to S2 and to our cache keys. (3) **ar5iv rendering** —
  a node's `arxiv_id` is the ticket to figures and full text. (4)
  *(future)* the arXiv **category tags** planned for the detail panel.
  Retiring arXiv *search* removed none of these.
- **`/api/graph` serializes the typed `Graph`** via `model_dump()` — the
  route is the model-to-JSON boundary (Phase 3 decision: the graph is a
  Pydantic model everywhere inside the app).
- **The figure proxy is an SSRF chokepoint.** `is_ar5iv_url` allowlists the
  ar5iv host before any fetch, so `/api/figure_proxy` can't be used as an
  open relay; responses carry a day-long `Cache-Control`. This is the
  same-origin contract behind both the detail panel's figure strip and the
  tutor's `show_figure` payloads.

## `search.py` — finding a seed paper

| Endpoint | Job |
| --- | --- |
| `GET /api/search?q=&limit=&year_from=&year_to=&fields=` | live seed search across Semantic Scholar |
| `GET /api/local_search?q=&limit=&year_from=&year_to=` | instant search over the local snapshot cache |
| `GET /api/taxonomy/<provider>` | a provider's subject vocabulary (`s2` fields / `arxiv` categories) |

Design decisions worth knowing:

- **`/api/search` replaced `/api/arxiv_search`** when seed search moved to
  S2 (wider coverage: 200M+ papers across venues, not just arXiv
  preprints). Papers come back as S2 node dicts — the same shape as graph
  nodes, and the same shape `local_search` returns.
- **A pasted arXiv id/URL short-circuits inside the service** (`live_search`):
  detected id → exact `ARXIV:<id>` lookup, skipping query expansion (an id
  isn't vocabulary — an "improved" id could only be a wrong one) *and* the
  filters (they never apply to an explicit lookup). The query analyst fires
  only on real free-text queries. An id S2 doesn't know returns nothing
  rather than falling through to a junk lexical search of the id text.
- **Filters degrade, never error.** A non-numeric year becomes "no filter";
  unknown `fields` values are silently dropped against
  `semantic_scholar.vocab.valid_fields()` (they can only come from a
  stale/forged client). Blank queries return an empty 200 — the box starts
  empty; that's not an error.
- **Two error philosophies again:** `/api/search` maps S2 failure to a
  canned 502 (details in the log, matching `graph.py` — the old route
  leaked `str(exc)` to the client); `/api/local_search` **never errors** —
  it degrades to zero hits, because the instant local results must not
  block the live search running alongside them.
- **`/api/taxonomy/<provider>` returns each provider's natural shape** —
  `{fields: [...]}` for s2 (~20 fields of study, the live-search filter),
  `{groups: [...]}` for arxiv (~155 categories in 8 areas, reserved for the
  future detail-panel tags) — rather than forcing a common envelope; the
  pickers they feed are different controls. Unknown provider → 404.

### Planned: LLM title resolution (not yet built)

Query expansion fixes the *vocabulary* gap ("DQN" → "…deep Q-network…"),
but there's a stronger play for famous papers. Google resolves "DQN"
straight to the Mnih et al. paper because the web is full of pages that say
"DQN" and link to it — Google resolves the *association*, not the string.
Claude internalized those same associations in training: asked what paper
"DQN" refers to, it names the exact titles from parametric knowledge — no
retrieval, no built-in RAG needed (a bare API call retrieves nothing;
Anthropic's opt-in web-search tool would be real grounding but is
latency/cost overkill per keystroke). And S2 has the perfect receiving end:
a **title-match endpoint** (`/paper/search/match`) that resolves a
near-exact title to a paper. So the plan: grow the analyst's structured
output to `Expansion{expanded_query, known_titles}` ("name the papers this
query most likely refers to *only if confident*") — still one Haiku call —
then `live_search` becomes: pasted id? → exact lookup → **known titles? →
S2 title-match, prepend verified hits** → expanded lexical search. The
hallucination risk defuses itself: an invented title simply doesn't match
on S2 and we fall back to the lexical search we'd have run anyway — the
failure mode is "no better than today," never worse. Post-cutoff papers
degrade to plain expansion the same way.

## Who uses it, and how/why

The React frontend (Phase 6) is the only caller: the search/seed flow hits
`/api/graph`, clicking a node hydrates via `/api/paper/<ref>`, and the
detail panel lazily loads `/figures` and `/code`. `<img>` tags point at
`/api/figure_proxy` URLs (both panel figures and the tutor's inline answer
figures use it). The search box fans out to `/api/local_search` (instant)
and `/api/search` (live) in parallel; the filter picker loads
`/api/taxonomy/s2` once.

## Testing

`test_graph.py` and `test_search.py` drive every endpoint through a real
test client built from `register_blueprints` (`conftest.py`), with
services/integrations monkeypatched at the route module's seams: URL/version
normalization reaching the service, the 400/404/502 taxonomy,
prefix-vs-raw paperId lookups, proxy rewriting + degradation of the
niceties, the SSRF lock, filter parsing/validation and clamps, the
never-error local search, and the taxonomy providers' shapes. The pasted-id
short-circuit is service-level behavior, tested in
`services/test_search.py`.
