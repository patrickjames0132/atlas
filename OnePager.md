# arXiv Atlas — One-Pager

> **Status:** v1.10 · living document · AI teacher (v1.1.0), sidebar figures + PDF
> link + dual-thumb slider (v1.2.0), Timeline layout (v1.3.0, month granularity
> v1.3.1), legacy digest backend retired (v1.4.0), agentic Q&A with full-text
> reading (v1.5.0), cache-first seed search (v1.6.0), agentic graph traversal
> `expand_node` + clickable answer highlights (v1.7.0), agentic topic search
> `search_papers` (v1.8.0), local semantic library for your own PDFs/URLs
> (v1.9.0), teacher searches your uploaded books in Q&A (v1.10.0)
>
> This file tracks the product vision, feature stack, and roadmap for the major
> rewrite — and preserves the history of the v0.x.x "digest" era so we don't lose
> the record. Keep it up to date as phases ship.

---

## Vision

**arXiv Atlas** turns a research paper into an explorable *map* and puts an AI
teacher beside it. Drop in a paper (say *Attention Is All You Need*) and Atlas
renders a **Connected-Papers-style interactive graph** of how it links to the
literature — the papers it built on, the papers it spawned, and its nearest
neighbors by meaning. Then hit **"Teach me how we got here"** and Claude narrates
the *history and intuition* of the field — the problem each seminal paper solved,
why it mattered, how each idea made the next possible — **while the graph lights
up node-by-node in sync with the story.** And like any good teacher, it takes
questions: **interrupt and ask a follow-up**, and it answers grounded in the
papers on screen, highlighting the nodes it draws from. It's the storytelling
magic of NotebookLM (narrative, a teacher's voice, and audio), self-hosted and
Claude-driven, married to an interactive citation graph NotebookLM never had.

We **leave the storage to the ecosystem** (Semantic Scholar / arXiv) and connect
dynamically — no local corpus of millions of papers, just a thin cache of the AI
artifacts we generate.

---

## The layered feature stack

Presented in build order. `[core]` = part of the v1.0 experience; `[flag]` =
optional, behind a key.

1. **Citation graph** `[core]` — the structural map. Nodes = papers; edges =
   references / citations / similarity. Built on **Semantic Scholar** (the same
   data backbone Connected Papers uses). Color by year, size by citation count,
   edge weight by similarity. Click to expand a node's neighborhood.

2. **AI teacher — "how we got here"** `[core]` — Claude generates a chronological
   lecture over a paper's lineage: ordered beats, each tied to a node, explaining
   intuition and significance. The **graph is the synchronized visual** — nodes
   highlight as the narrative advances. Secondary modes: *explain this paper's
   intuition*, *bridge these two topics*.

3. **Ask the teacher — Q&A** `[core]` — interrupt the lecture and ask follow-ups
   ("why did attention replace RNNs?", "how does this node differ from that
   one?"). Claude answers **grounded in the papers currently on the graph** — the
   visible neighborhood is the retrieval scope, so no separate vector store is
   needed — and **highlights the nodes it cites**, keeping every answer anchored
   to the map. Conversational, so you can go back and forth; questions that reach
   past the neighborhood expand the graph or pull that paper from S2 on demand.

4. **Concept mindmap** `[core]` — Claude emits a concept map (ideas as nodes,
   relationships as edges) rendered in the same graph library. A **"Bridge these
   topics"** action cross-links unrelated fields (e.g. astrophysics ↔
   reinforcement learning) — pure reasoning, built by us, not outsourced.

5. **Audio lecture** `[core]` — **Podcastfy** (open-source, self-hosted) turns
   the same lecture script into a two-host podcast. Free **Microsoft Edge TTS** by
   default; **ElevenLabs** voices optional. The "listen on a walk" experience,
   with no NotebookLM dependency.

6. **Polished media** `[flag]` — optional **AutoContent API** integration
   (~€24/mo) for glossy artifacts we don't cheaply DIY: **slide decks,
   infographics, explainer video, timelines**. Additive, behind a feature flag +
   API key. Trial before committing; never load-bearing.
   *Later idea:* leverage the papers' **own figures** — pulled via
   [ar5iv](https://ar5iv.org) HTML, the arXiv source tarball, or a
   figure-extractor (`pdffigures2` / DeepFigures) — so slides embed the real
   diagrams from the papers, not just generated graphics.

---

## Data & tech

- **Academic graph:** [Semantic Scholar Academic Graph + Recommendations API](https://api.semanticscholar.org/api-docs/)
  — free, maps arXiv IDs directly (`ARXIV:<id>`), exposes references, citations,
  SPECTER2 embeddings, `tldr` summaries, and related-paper recommendations.
  ~1 req/sec on the free key (higher limits available on request).
- **Seed discovery:** the existing arXiv search (`arxiv` package) finds the seed
  paper, then hands its id to the graph builder.
- **Graph renderer:** [`react-force-graph-2d`](https://github.com/vasturiano/react-force-graph)
  (chosen for speed; canvas force-directed with custom node painting). Sigma.js +
  graphology remains the fallback if we ever need very large graphs.
- **AI narration:** Claude via the existing **dual backend** (Claude CLI under
  the Pro/Max subscription, or the Anthropic API) — reused from the digest era.
- **Audio:** [Podcastfy](https://github.com/souzatharsis/podcastfy) (Python lib) +
  Edge TTS (free) / ElevenLabs (optional).
- **Polished media:** [AutoContent API](https://autocontentapi.com/) (optional).
- **Storage:** thin SQLite cache only — AI artifacts (summaries, lecture scripts)
  + short-lived graph snapshots. Kilobytes, not TB.

---

## Roadmap

> Grouped by **theme**, not ship order — renumbered 2026-07-03 once features
> started landing out of sequence (the explorer polish now under 2.x shipped
> *after* Phase 3a). **Version tags are untouched** and carry the true
> chronology. Old → new names: *Phase 3.5* → **2.2**, *Sidebar enrichment* →
> **2.1**, *Legacy teardown* → **2.3**, *Phase 3b.1* → **3b**, *Phase 3b.2* →
> **3c.1**.

**Foundation**

- [x] **Phase 0 — One-pager** (this file)
- [x] **Phase 1 — Backend pivot to Semantic Scholar** *(v1.0.0)* —
      `semantic_scholar.py` client (batch hydration to dodge the single-GET
      throttle, 429 backoff, optional `S2_API_KEY`), `graph.py` neighborhood
      builder, thin `cache.py` (graph snapshots), new `/api/graph` & `/api/paper`
      routes. Seed accepts an arXiv id **or** a raw S2 paperId. *(The deeper
      teardown of the legacy digest backend was completed later — see
      **Phase 2.3 — Legacy teardown** below.)*

**The graph explorer**

- [x] **Phase 2 — Graph explorer frontend** *(v1.0.0)* — force-directed canvas
      (`react-force-graph-2d`), seed via arXiv search, nodes colored by relation
      / sized by citations / edges typed & directed, detail panel with `tldr`.
      **Declutter controls:** relation filters (refs/citations/similar) with
      counts, a dual-handle **year range** slider, **drag-to-pin** (+ release
      all), **focus-on-hover** dimming, and a papers-shown readout. **Visual
      traversal:** double-click (or "Explore from here") re-seeds the graph on
      any node — journal papers included.
- [x] **Phase 2.1 — Sidebar enrichment** *(v1.2.0)* — under the detail panel's
      TL;DR, the paper's **own figures with their captions** (`figures.py`
      extracts them from **ar5iv** HTML, cached 30 days; images streamed through
      a same-origin `/api/figure_proxy` locked to the ar5iv host — no hotlink
      reliance, no open proxy; tables skipped; graceful fallback where ar5iv has
      no render), plus a **direct PDF link** beside the arXiv-abstract link.
      Shipped alongside a UI polish: the year filter is now a single
      **dual-thumb range slider** (two overlaid inputs on one track + fill)
      instead of two stacked sliders.
- [x] **Phase 2.2 — Timeline layout** *(v1.3.0, month granularity v1.3.1)* — a
      **Force ↔ Timeline** toggle. Timeline pins each node's x to its **publication
      date** (year + month fraction from S2 `publicationDate`, so papers sit
      *between* the yearly gridlines; the detail panel shows the full date) while
      the sim resolves y; a `d3-force-3d` **collision force** (radius-sized) spreads
      papers out within a year column, and once settled **y is frozen** so a drag
      can't re-scramble the layout. A faint **year axis** is drawn behind the
      graph (labels thinned when zoomed out); narrowing the year slider **zooms
      into that span**. So the chronological lecture sweeps left→right as nodes
      light up. Force stays the default; switching layout releases all pins. (A
      relation-band variant remains a possible later sub-toggle.)
- [x] **Phase 2.3 — Legacy teardown** *(v1.4.0)* — retired the digest-era backend
      now that Atlas stands on its own: deleted `store.py`, `pipeline.py`,
      `summarizer.py`, `embeddings.py`; slimmed `search.py`/`arxiv_client.py` to
      just the seed search; removed 8 legacy `app.py` routes + 8 unused `api.ts`
      functions; trimmed dead `config.py`/`.env.example` settings; `run.py` is now
      `serve`-only. `taxonomy.py` kept **dormant** for near-term features. (See
      "Deliberately dropped" below for the what/why.)
- [x] **Phase 2.4 — Cache-first seed search** *(v1.6.0)* — seed-search results
      served from the **local snapshot cache instantly**, before (and independent
      of) the live arXiv search: `/api/local_search` scans cached graph snapshots
      by title/authors, ranks phrase matches → explored seeds → citation count,
      and flags papers whose own neighborhood is freshly cached (an **instant**
      badge — those explore without touching the rate-limited API). Live arXiv
      results append below when they land; if arXiv is unreachable, the cached
      papers still work. Born of a real rate-limited evening.

**The AI teacher**

- [x] **Phase 3a — AI teacher + Q&A (grounded)** *(v1.1.0)* — `teacher.py` with
      the dual Claude backend (Anthropic API **or** the `claude` CLI subscription)
      **streamed** so narration reveals beat-by-beat. `/api/lecture` (SSE) emits
      ordered lecture **beats**, each bound to graph nodes that **light up in
      sync**; modes: *history* ("how we got here") and *intuition* (bridge mode
      exists in the backend, no UI button yet). `/api/ask` (SSE) answers
      conversational, **session-scoped** questions grounded in the on-screen
      graph, streaming tokens then highlighting the **cited nodes**. Frontend:
      the `Teacher.tsx` panel + a `highlightIds` glow/dim path reusing the
      focus-on-hover machinery. *Grounded in the visible neighborhood only — no
      full-text reading or graph-jumping yet (that's 3b/3c).*
- [x] **Phase 3b — Agentic Q&A: full-text reading** *(v1.5.0)* — the Q&A agent
      now runs a **tool-use loop** (`read_paper` tool, via ar5iv full text or
      abstract+TL;DR summary) before answering. Hard guardrails: 4 full-text reads,
      12 summary reads, 12 agent steps, 90 s wall-clock. Each read emits a live
      **trace event** (`📖 Read <title> · full text`) in the chat before the answer
      streams. `fulltext.py` extracts readable body text from ar5iv HTML (math,
      scripts, and figures stripped; 30-day cache). Requires the Anthropic API;
      falls back gracefully to the Phase 3a grounded answer with the CLI backend.
- [ ] **Phase 3c — Agentic reach beyond the graph** — the Q&A agent escapes the
      visible neighborhood, in two steps:
  - [x] **3c.1 — Graph traversal (`expand_node`)** *(v1.7.0)* — the agent fetches
    papers **not yet on the graph** (one hop of references / citations / similar
    from a paper already in context) and auto-merges them as new nodes (distinct
    dashed **"discovered" ring**, anchored near their source so they don't fly in
    from the origin), with a **hop budget** (5) and **visited-set** to kill
    reference cycles; each hop emits a live **trace event** (`🔗 Expanded
    references of <title> · N new`) and discoveries feed back into the grounding
    context for follow-up questions. Q&A answers are now **clickable sections**
    like lecture beats — click to re-light the papers an answer was grounded in,
    click again to clear. *(Shipped 2026-07-03; browser-tested. OpenAlex keyless
    fallback still an open question — see below.)*
  - [x] **3c.2 — Topic search (`search_papers`)** *(v1.8.0)* — traversal alone is
    lineage- and embedding-biased, not recency-biased: a 2026 paper citing a 2017
    seed has had no time to accumulate citations of its own, so questions like
    *"what's the latest transformer architecture in 2026?"* can't be reached by
    hops from an old seed. The agent now has a `search_papers(query, year_from?,
    year_to?)` tool hitting S2's paper-search endpoint directly (**ungrounded** —
    no source node) with a **year filter** so "latest" queries bias recent. Hits
    merge in under a distinct **`search` relation** (its own pink color +
    "Found by search" legend, *not* `similar`) with its **own budget** (3 searches,
    separate from the hop budget) and its own visited-set; results **float,
    anchored near the seed** (no edge — the link is topical, not verified) and feed
    back into the grounding context. Live **trace event** (`🔎 Searched "query"
    (2024–now) · N new`). Also this cut: Q&A answers now emit the same `<<CITED>>`
    sentinel as the grounded path, so a **follow-up answered from context** (no
    re-read) still highlights the papers it drew on. *(Shipped 2026-07-03;
    browser-tested.)*
  - **CLI/MCP path + lecture enrichment** remain unscoped stretch ideas beyond
    3c.2. **OpenAlex** keyless traversal fallback is still an open question (see
    costs / open questions below) — not built; a manual `S2_API_KEY` is the
    reliable path for `expand_node` / `search_papers` under rate limits.
- [ ] **Phase 3d — Bring your own sources** — pull the user's own material into
      the teacher's reach so Q&A can draw on it alongside the papers it fetches —
      "how does this paper relate to chapter 3 of my textbook?" Books are far too
      big to stuff into context, so this is **local RAG**: chunk → embed → search.
  - [x] **3d.1 — Ingest + local semantic library** *(v1.9.0)* — uploaded **PDFs**
    (per-page text via `pymupdf`, so retrieval cites an exact page) and **web
    pages** (paste a URL; readable text via the shared `fulltext.html_to_text`)
    are split into overlapping page-aware chunks, embedded **locally** (revived
    `embeddings.py`, all-MiniLM-L6-v2, 384-dim — no API/key, so copyrighted books
    never leave the machine) and stored in a dedicated **sqlite-vec** index
    (`sources.py`, `data/sources.db`, cosine KNN). A **global persistent library**
    (survives across graphs) with CLI ingest/search/list/forget (`run.py`).
    Degrades gracefully via `available()` if the model / sqlite-vec can't load.
    *(Shipped 2026-07-03; verified on real books via CLI.)*
  - [x] **3d.2 — Agent tools + UI** *(v1.10.0)* — the agentic loop gets a
    `search_sources(query, source_id?)` tool (own budget
    `AGENT_MAX_SOURCE_SEARCHES=5`, `📚 Searched your sources` trace line), offered
    **only when a library exists** (an empty library never loads the embedding
    model). The agent sees the library listed in its context (so it can scope to
    one source) and **cites passages inline by page** — "(Deep Learning, p.243)".
    A **📚 Sources drawer** (top bar) uploads PDFs / pastes URLs and manages the
    library (`GET/POST /api/sources`, `DELETE /api/sources/<id>`; 256 MB uploads).
    Sources aren't graph nodes, so they cite rather than highlight the graph.
    *(Shipped 2026-07-03; browser-tested — the teacher pulls from uploaded books
    in Q&A with page citations.)*
  - **3d.3 — polish** *(scoped)* — hybrid **FTS5 + vector (RRF)** for exact-term /
    proper-noun lookups, per-source scoping in the UI, figure/image handling
    (OCR for scanned PDFs), and an optional stronger embed model (`bge-small`).

**Beyond the teacher**

- [ ] **Phase 4 — Concept mindmap** — Claude concept-map JSON, "bridge two
      topics," `/api/mindmap`.
- [ ] **Phase 5 — Audio lecture** — Podcastfy integration, Edge TTS default,
      ElevenLabs optional, `/api/lecture/audio`.
- [ ] **Phase 6 — Polished media (optional)** — `autocontent.py` behind
      `AUTOCONTENT_API_KEY`; "Generate visuals" button.

**Enhancements & tech debt** *(unscheduled; from the `todos.md` inbox)*

- [ ] **Offline chat mode** — query the local sources / embeddings directly in a
      chat without first opening a graph or running a seed search. The retrieval
      layer already exists (Phase 3d); needs a lightweight chat entry point +
      route that skips the graph-grounding context.
- [ ] **Frontend/backend package refactor** — break large modules into logical
      packages/groups so the code is easier to follow (e.g. `GraphExplorer.tsx`
      is 1,000+ lines; some backend grouping too).
- [x] **CLI → `click`** *(v1.11.0)* — replaced the hand-rolled `argparse` in
      `run.py` with a `click` group (same command names: `serve`, `ingest`,
      `sources`, `search-sources`, `forget`).
- [x] **"Powered by Claude"** *(v1.11.0)* — subtle top-bar credit (Anthropic
      sunburst mark + "Powered by Claude", linking to anthropic.com/claude);
      names the model the AI teacher actually runs on, not the build tool.
- [x] **Windows PDF upload fix** *(v1.10.1)* — source ingest used a
      `NamedTemporaryFile` whose exclusive lock on Windows made the reopen fail
      with `[Errno 13] Permission denied`; switched to `mkstemp` + manual cleanup.

Each phase is independently shippable and gets its own version bump
(test-in-browser → bump `pyproject.toml` + `uv.lock` → annotated tag → push).

---

## Deliberately dropped in v1.0

The digest era's local-first machinery is retired in favor of dynamic queries.
The **code** for all of this was removed in the **v1.4.0 legacy teardown** (only
`taxonomy.py` survives, dormant):

- Local **paper corpus** (`papers` table) + the `store.py` module — no more
  storing paper rows.
- **FTS5** full-text index (`papers_fts`) and **sqlite-vec** vector index
  (`papers_vec`), plus `embeddings.py` and the hybrid `search.py` — search /
  similarity now come from Semantic Scholar.
- The **`pulls` ledger**, category-aware smart-pull, and `pipeline.py` — no
  date-range fetching.
- The **date-range digest table**, pagination, the **Download modal**, and the
  **NotebookLM export** — plus `summarizer.py` (its dual-backend Claude pattern
  lives on in `teacher.py`).

*(Resolved: we committed fully to the graph-first experience — no daily-digest
mode.)*

---

## Legacy — the v0.x.x "digest" era (kept for history)

The app began as a local-first daily digest: pull arXiv papers by category into
SQLite, summarize with Claude, browse in a paginated table with hybrid search,
export to NotebookLM. Milestones:

| Version | What shipped |
|---|---|
| v0.9.0 | Search-aware NotebookLM export (export honors the active search query) |
| v0.9.1 | Category-aware smart pull — per-day/category `pulls` ledger so adding a subject re-fetches days already holding other categories |
| v0.9.2 | Category modal: taxonomy tooltips + "Clear all" |
| v0.10.0 | Live **"Search all of arXiv"** + on-the-fly per-paper **Add** |
| v0.11.0 | Separated **downloading from browsing** — unified Download modal; top-bar View range only filters |

**Enduring tech carried forward into v1.0:**
- **Dual-backend Claude summaries** — Claude CLI (Pro/Max subscription, no API
  billing) or the Anthropic API, with automatic fallback. Reused for narration.
- **arXiv taxonomy** picker/seed data.
- **arXiv search** entry point (title-phrase-boosted; id/URL detection).

**Retired with the pivot:** Gmail/OAuth ingestion (removed even earlier, in the
switch to the `arxiv` package), local hybrid search (FTS5 + sqlite-vec + RRF),
the digest table, and the smart-pull ledger.

---

## Open questions & costs

- **Daily digest mode?** — Decide whether to keep any date-range "what's new
  today" view, or go fully graph-first. Leaning fully graph-first for v1.0.
- **Semantic Scholar rate limits** — free key ~1 req/sec; need polite batching +
  caching. Key application submitted 2026-07-03 (S2 requires an academic /
  corporate email — used the old academic address, approval pending). Keyless
  429s are painful enough that **OpenAlex** (free, no key, generous limits) is
  under consideration as a fallback backbone — decision parked for a night.
  Cache-first seed search (Phase 2.4) softens browsing in the meantime.
- **S2 coverage gaps** — arXiv CS/ML coverage is high but not total; some papers
  may have sparse citation edges. Consider OpenAlex as a later fallback.
- **AutoContent API** — ~€24/mo (1,000 credits: infographic 10, slide deck 30,
  video 50). Trial the cheap tier and judge quality by eye before committing.
- **ElevenLabs** — optional premium TTS; free tier ~10k credits/mo.
- **Paper figures for slides** (later phase) — evaluate ar5iv HTML vs. arXiv
  source tarball vs. `pdffigures2`/DeepFigures for pulling real diagrams; decide
  how to caption/attribute them. Deferred until the visuals/slides phase.
