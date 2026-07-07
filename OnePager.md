# Atlas — One-Pager

> **Status:** v1.23 · living document · AI teacher (v1.1.0), sidebar figures + PDF
> link + dual-thumb slider (v1.2.0), Timeline layout (v1.3.0, month granularity
> v1.3.1), legacy digest backend retired (v1.4.0), agentic Q&A with full-text
> reading (v1.5.0), cache-first seed search (v1.6.0), agentic graph traversal
> `expand_node` + clickable answer highlights (v1.7.0), agentic topic search
> `search_papers` (v1.8.0), local semantic library for your own PDFs/URLs
> (v1.9.0), teacher searches your uploaded books in Q&A (v1.10.0), offline library
> chat (v1.12.0), per-source scoping + stronger embed model (v1.13.0), "how we got
> here" time-travel (v1.14.0), saved sessions & workspaces (v1.15.0), seed-search
> date/category filters + result dates (v1.16.0), teacher source-scope selection
> (v1.17.0), unified assistant panel (v1.18.0), parallel upload + multi-select
> source scope (v1.19.0), figures in agent answers (v1.20.0), hybrid lexical +
> semantic library search (v1.21.0), quality hardening — strict mypy, src-layout,
> 105-test offline suite (v1.21.1–.3), inline answer figures (v1.22.0), code &
> artifact links via Hugging Face Papers (v1.23.0)
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
  - **3d.3 — polish** *(scoped)* — remaining source-library polish:
    - [x] **per-source scoping in the UI** *(v1.13.0)* — the offline library chat
      gets an "All sources / one source" picker (shown at 2+ sources) that scopes
      retrieval; `source_id` flows question → `/api/ask_sources` →
      `answer_from_sources` → `sources.search`.
    - [x] **optional stronger embed model** *(v1.13.0)* — swap in `bge-small`
      (also 384-dim, so `ARXIV_EMBED_DIM` is unchanged) via `ARXIV_EMBED_MODEL`,
      with a query-only instruction prefix (`ARXIV_EMBED_QUERY_PREFIX`, empty by
      default) for asymmetric retrieval; re-ingest sources to apply.
    - [x] hybrid **FTS5 + vector (RRF)** for exact-term / proper-noun lookups
      *(v1.21.0)* — `sources.search` now fuses a **semantic** ranking (sqlite-vec
      cosine KNN) and a **lexical** one (FTS5 BM25) via **Reciprocal Rank Fusion**,
      so an exact term / proper noun / hyperparameter the embedder blurs together
      (e.g. "β2", a dataset or author name) still surfaces. An external-content
      `chunks_fts` index is kept in sync by insert/delete **triggers** (so
      ingest/delete needed no changes; cascade-deletes purge it too) and
      **back-fills existing libraries** on first connect — no re-ingest. Degrades
      cleanly: no FTS5 → pure vector (prior behavior), no embed model →
      lexical-only, neither → empty. Config `ARXIV_SOURCE_HYBRID` (default on) /
      `ARXIV_SOURCE_RRF_K` (60). Verified: on an exact-term query hybrid lifts the
      right passage from a razor-thin vector-only lead to a decisive win.
    - [ ] figure/image handling — **OCR for scanned PDFs** *(deferred — needs a
      system Tesseract dep, fiddly on Windows)*.
- [x] **Phase 3e — "How we got here" time travel** *(v1.14.0)* — the history
      lecture no longer starts mid-stream: before narrating, `history_backfill`
      walks **backward through references** to a field's older roots. It launches
      from the **oldest papers already on the graph** (expanding the seed just
      re-finds its visible refs), each hop adding the most-cited new ancestors and
      carrying the oldest into the next hop, bounded by a hop budget
      (`LECTURE_HISTORY_HOPS`) and a **year floor** (`LECTURE_HISTORY_LOOKBACK`
      years before the seed). Discovered ancestors merge into the live graph
      (dashed rings; far-left in Timeline) and join the node set the lecture
      narrates over; the panel shows the hops live (`⏳ Traced back to <year>`).
      Deterministic, so it runs on both teacher backends, reusing the Phase 3c
      `_s2_neighbors` machinery. Shipped with an **S2 request throttle** (~1 req/s,
      `S2_MIN_INTERVAL`) so the backward burst — and graph build / agent expansion
      — don't 429. *(Browser-tested — reaches genuinely older foundational work; a
      specific origin paper can still be missed since additions rank by citations
      over a narrow frontier — future tweak: prefer `influential` edges.)*

**Beyond the teacher**

- [x] **Phase 4 — Saved sessions & workspaces** *(v1.15.0)* — persistence,
      deliberately dropped at the v1.0 pivot, reintroduced as opt-in. A **🗂
      Sessions drawer** saves the current workspace — the full graph as it stands
      (every node/edge, **including the papers the agent discovered / expanded /
      searched in**, with their flags), the layout mode, and the teacher
      transcript (chat + lecture beats + history trace) — into a dedicated
      persistent store (`sessions.py`, `data/sessions.db`; own lifecycle, never
      TTL-evicted). Reopening rebuilds the graph **directly from the save — no
      Semantic Scholar rebuild**, so a restore costs zero rate-limited calls and
      the exact discovered papers come back; the teacher remounts with the saved
      conversation (restored answers/beats still re-light their nodes on click).
      **Save-as-new** or **Update** an existing session in place (overwrite by id),
      plus delete. Shipped with the bundled lighter control: **clear chat on
      demand** — a **Clear** button in the teacher header, and re-seeding via
      "Explore from here" now auto-starts a fresh conversation (the panel remounts
      per graph). New routes `GET/POST /api/sessions`, `GET/DELETE
      /api/sessions/<id>`. *(Known limit: the server-side Q&A memory is ephemeral,
      so a follow-up after reopening starts without the earlier turns as context —
      it still answers against the fully restored graph. Deliberately left as-is.)*
- [ ] **Phase 5 — Concept mindmap** — Claude concept-map JSON, "bridge two
      topics," `/api/mindmap`.
- [ ] **Phase 6 — Audio lecture** — Podcastfy integration, Edge TTS default,
      ElevenLabs optional, `/api/lecture/audio`.
- [ ] **Phase 7 — Polished media (optional)** — `autocontent.py` behind
      `AUTOCONTENT_API_KEY`; "Generate visuals" button.

**The v2 rewrite** *(shipped)*

- [x] **v2.0.0 — the readability rewrite** *(2026-07-06)* — the whole app
      rebuilt file-by-file in a walkthrough (explain → refactor → test → sync),
      with a README in every package. Backend: `config.json` + Pydantic config
      (no env vars), strict mypy, typed `Graph` models, the teacher reborn as a
      **PydanticAI agent crew** (query_analyst / librarian / lecturer /
      researcher behind a deterministic orchestrator; typed event stream;
      everything streams for real — required Anthropic's eager tool-input
      streaming). Search moved **arXiv → all of Semantic Scholar** with LLM
      query expansion + title resolution and whole-result caching; the `arxiv`
      package and the claude-CLI backend retired. Frontend: strict TS, Redux
      Toolkit (3 slices: workspace/transcript/highlight), the 743-line
      Teacher.tsx and 577-line Atlas.tsx decomposed along the hybrid structure
      rule, ingest progress bars, a Home button, and the **"Atlas"** rebrand
      (in-app copy; repo name unchanged).
- [x] **`atlas` package rename** *(v2.0.1)* — the backend catches up to the
      in-app rebrand above: `src/arxiv_digest/` → `src/atlas/`,
      `test/arxiv_digest/` → `test/atlas/`, every import updated, and the
      console script `arxiv-atlas` → `atlas` (`uv run atlas serve`).
      `pyproject.toml` has no remaining `arxiv` references. GitHub repo name
      unchanged (`arxiv-digest`) — a separate, un-requested action.

- [ ] **Graph-less research mode** — let the researcher run with no graph
      open: agentic research from scratch (search S2 + the local library, no
      seed required). Would retire the librarian in its favor — today's
      no-graph chat is deliberately single-shot RAG (retrieval-before-model:
      half the cost/latency, grounding guaranteed by construction), which is
      the right trade until real usage demands agency there.
- [ ] **Orchestrator model fan-out** — the hybrid design's model half, on the
      documented seam in `agents/orchestrator/main.py`: for ambiguous or
      multi-step asks, let an orchestrator model route or fan out across
      sub-agents and synthesize. Same trigger as above: build when usage
      shows the researcher's own tool loop isn't enough.
- [x] **Detail-panel arXiv category tags** *(v2.3.0)* — the panel now shows an
      arXiv paper's own category tags (`cs.LG` → "Machine Learning") as
      read-only pills between the meta line and the TL;DR. S2 doesn't carry
      per-paper categories, so a new `integrations.arxiv.categories` module
      hits arXiv's own export API (a different host from ar5iv) for the raw
      codes and labels them via a new `vocab.name_for` lookup, served by
      `GET /api/paper/<ref>/categories` (same degrade-to-`available:false`
      contract as figures/code) and fetched lazily in `useSelection` alongside
      them. *Fixed same day:* six pairs in the taxonomy are different codes
      that happen to share one display name (`cs.LG`/`stat.ML`, both
      "Machine Learning"; also the `cs.IT`/`math.IT`, `cs.NA`/`math.NA`,
      `cs.SY`/`eess.SY`, `math.MP`/`math-ph`, `math.ST`/`stat.TH` pairs) — a
      paper cross-listed in both of a pair showed the identical label twice
      (caught on Kingma & Welling's VAE paper, tagged both `stat.ML` and
      `cs.LG`); `get_categories` now dedupes by display name, keeping arXiv's
      first-listed code of the pair. *(From the `todos.md` inbox,
      2026-07-07.)*
- [x] **Fix: dateless papers in Timeline landed at the far edge** *(v2.3.1)* —
      a paper with no publication year (S2 sometimes just doesn't have one)
      was placed one slot before the earliest real year on the graph — a
      strong, usually-wrong assumption that "unknown date" means "oldest."
      `nodeTimelineX` (`useTimeline.ts`) now defaults a dateless node to the
      **seed's own exact x** — same year *and* month fraction, pixel-aligned
      with the seed's column, not just parked somewhere in its year — falling
      back to the earliest year only if the seed itself has none. (There's no
      day-level precision anywhere in this layout, only year+month, so
      "exact" tops out at whatever precision the seed has — same ceiling
      every other node on the graph is already subject to.)
- [ ] **General non-arXiv full text** — S2's `openAccessPdf` + the existing
      pymupdf pipeline as a fallback reader for `read_paper` on journal
      papers (text only; figures stay ar5iv-quality-or-nothing).

**Enhancements & tech debt** *(unscheduled; from the `todos.md` inbox)*

- [x] **Offline chat mode** *(v1.12.0)* — a graph-free RAG chat straight over the
      local library. `teacher.answer_from_sources` retrieves the top passages
      (`SOURCES_CHAT_K`) and answers grounded only in them, citing inline by page —
      retrieve-then-answer (no tool loop), so it runs on both teacher backends.
      New route `POST /api/ask_sources` (SSE, own session store) + a `LibraryChat`
      modal reachable from a top-bar "💬 Ask library" button and an empty-state CTA
      (both shown only when a library exists).
- [x] **Parallel multi-file source upload + multi-select scope** *(v1.19.0)* —
      the Sources drawer now takes **many PDFs at once** (a `multiple` picker
      **and** drag-and-drop) and ingests them **in parallel** (a 3-wide pool over
      the threaded server), with **per-file progress** rows (`embedding… → ✓ added`
      / `✕ failed` with the message). Alongside it, the assistant's source-scope
      control went from a single-select dropdown to a **checkbox popover** — a
      checked box = that source is on (defaults to all), so scoping is now a true
      **subset**, not one-at-a-time. Backend: `sources.search` `source_id` →
      `source_ids` (an `IN (…)` filter), threaded through `answer_from_sources` /
      `answer_agentic` / the `search_sources` tool and both ask routes.
      *(From the `todos.md` inbox, 2026-07-03.)*
- [x] **Unified assistant panel** *(v1.18.0 — supersedes the old "toggle to
      library-agent view" idea)* — collapsed the two overlapping chat surfaces
      (the docked `Teacher` panel and the `LibraryChat` modal) into **one
      header-toggled docked panel** whose capability levels up with context:
      **no graph, has library** → a graph-free chat over the uploaded library
      (`streamAskSources` → the backend-agnostic `answer_from_sources` path);
      **graph open** → the lecture + agentic Q&A (`read_paper` / `expand_node` /
      `search_papers` **and** `search_sources`). A **🎓 Assistant** header toggle
      opens/collapses it (active-state styled); it auto-opens on graph load. Docked
      (not a scrim-drawer) so answers still light up graph nodes; **collapsed =
      hidden but mounted**, so toggling preserves the in-progress conversation. The
      v1.17.0 source-scope selector works in both modes. `LibraryChat.tsx` +
      `library-chat.css` deleted; **backend untouched** (both endpoints already
      existed — the panel just routes by graph presence).
      *(From the `todos.md` inbox, 2026-07-03; shaped + shipped 2026-07-03.)*
- [x] **Source selection for the AI Teacher** *(v1.17.0)* — the Teacher panel
      gained the same source-scope control the library assistant has: an **All
      sources / one source** dropdown (shown when the library has >1 source) that
      **pins the agent's `search_sources` to the chosen source** — only that source
      appears in the agent's "Your library" context and every source search is
      forced to it (a scope matching nothing disables source search rather than
      silently widening). Threaded `source_id` through `/api/ask` →
      `answer_agentic`; the graph-only paths (lecture, non-agentic Q&A) ignore it.
      *(From the `todos.md` inbox, 2026-07-03.)*
      **Next:** fold this into a **single unified assistant panel** (see the
      library-view toggle item) — one header-toggled drawer that defaults to the
      library with no graph open and levels up to graph + S2 tools once one is.
- [x] **Publication date in search results + seed-search filters** *(v1.16.0)* —
      arXiv hits now show their **publication date** (from the paper's own
      submission day), and the search surface gained an optional **filter
      popover**: a dual-handle **year-range slider** (folds to no-bound at 1991 /
      the current year, so a full-width slider is the no-op state) plus an **arXiv
      category picker** fed by a new `/api/taxonomy` endpoint (server-validated
      codes, any-of match). Filters AND onto arXiv's query (`submittedDate` + `cat`
      clauses) and the local cache's year window alike; an explicit id/URL lookup
      ignores them. This is where the dormant `taxonomy.py` finally earns its keep.
      *(From the `todos.md` inbox, 2026-07-03.)*
- [x] **Frontend/backend package refactor** *(v1.15.1–v1.15.2)* — the whole
      codebase reorganized into concern packages. Backend: `app.py` → a thin
      factory over `routes/` blueprints; `teacher.py` (1,280 lines) → a
      `teacher/` package (backends, lecture, qa, agentic, tools, sources_chat);
      then (v1.15.2) the remaining flat modules grouped into role packages —
      `integrations/` (S2, arXiv, ar5iv), `services/` (graph, search),
      `storage/` (cache, sessions), `library/` (sources, embeddings) — with
      **Google-style docstrings (Args/Returns/Raises) on all 134 backend
      functions**. Frontend: `api.ts` → an `api/` module; `GraphExplorer.tsx`
      (1,244 lines) → `Atlas.tsx` (a 560-line orchestrator) over concern
      folders — `header/`, `search/`, `graph/`, `detail/`, `teacher/`,
      `library/`, `sessions/` — each owning its components, hooks, and CSS
      (the 1,000-line `atlas.css` split alongside). Everything
      JSDoc/docstring-documented.
- [x] **`src/` layout for the backend** *(v1.21.2)* — `backend/arxiv_digest/` →
      `src/arxiv_digest/` (the standard `src`-layout), with the project now a real
      **installed package** (hatchling build, uv editable install): `backend/run.py`
      folded into the package as `cli.py` behind an **`arxiv-atlas` console script**
      (`uv run arxiv-atlas serve` replaces `uv run python backend/run.py serve`;
      same subcommands), and every `sys.path` shim deleted — imports just work in
      tests, nox, and one-liners. mypy/pytest configs retargeted. The move also
      let mypy see `cli.py` for the first time, catching a **real bug**: CLI
      `search-sources` still passed the pre-v1.19 `source_id=` kwarg (a runtime
      TypeError since the multi-select rename) and printed the pre-v1.21
      `distance` field — both fixed. Paves the way for `test/` to mirror
      `src/arxiv_digest/` in the coverage push. *(From the `todos.md` inbox,
      2026-07-03.)*
- [x] **`noxfile` + CI quality backbone** *(2026-07-03)* — **`uv run nox`** runs
      four sessions from `noxfile.py` (all reusing the uv env): **`precommit`**
      (pre-commit hooks + **ruff** lint), **`mypy`** (types), **`tests`**
      (**pytest** over a new `test/`, offline smoke tests), and **`security`** (a
      **Trivy** fs scan that skips cleanly when trivy isn't on PATH, so the gate
      stays green without it). Config lives in `pyproject.toml`; `CLAUDE.md`
      documents the gate. mypy runs on a **lenient baseline** (see next item).
      *(From the `todos.md` inbox, 2026-07-03.)*
- [x] **Burn down the mypy baseline** *(v1.21.1)* — all four silenced error codes
      (`union-attr`, `return-value`, `arg-type`, `call-overload`; 141 hidden
      findings) fixed and `disable_error_code` **deleted**, plus
      `check_untyped_defs = true` turned on (so untyped function bodies are checked
      too — stricter than the original goal). The big one: `teacher/agentic.py`'s
      116 union-attr errors fell to **isinstance narrowing on the SDK's real event
      types** (`RawContentBlockStartEvent` / `RawContentBlockDeltaEvent` /
      `TextDelta` / `ToolUseBlock`) replacing `getattr(…, "type", "")` duck-typing;
      Flask views returning `(body, status)` tuples now use
      `flask.typing.ResponseReturnValue`; `_TOOLS` typed as `list[ToolParam]` via
      `TYPE_CHECKING`; the SSE generators annotated with runtime-enforcing
      `assert isinstance` narrowing on the `(kind, data)` event protocol. Verified
      behavior-neutral by driving `answer_agentic` with a stubbed client emitting
      real SDK event objects (discard, split-sentinel hiding, cited parsing).
- [x] **Expand test coverage (a lot)** *(v1.21.3)* — the suite went from 7 smoke
      tests to **105 offline tests**, in a `test/` tree that **mirrors
      `src/arxiv_digest/`**. Five layers: the **agentic loop** (driven by a
      scripted `FakeClaude` emitting *real* SDK event objects — discard,
      split-sentinel hiding, budgets, wallclock), the **tool runners** (budgets,
      visited-sets, edge directions, scope override), the **S2 client + graph
      service** (node normalization, 429 backoff, batch chunking, cache = zero
      repeat calls), the **routes** (error mapping, SSE framing, sessions CRUD,
      SSRF lock), and the **library** (chunker semantics, real in-memory PDFs via
      pymupdf incl. scanned rejection, scope semantics, delete cascade). Shared
      `conftest.py` fixtures isolate every test onto temp DBs (the real `data/`
      is untouchable) and stub embeddings deterministically (no torch load). The
      route tests **found and fixed a real bug**: all three SSE generators in
      `routes/teacher.py` logged via `current_app` during response iteration
      (outside the request context), so a mid-stream failure raised RuntimeError
      and killed the stream before the `error` event reached the panel — now a
      module logger, with the `token → error` framing locked in by a test.
      *(From the `todos.md` inbox, 2026-07-04.)*
- [x] **Papers-with-code / implementation links** *(v1.23.0)* — the detail panel
      now shows a **"Code & artifacts"** section from **Hugging Face Papers**
      (Papers with Code's successor): the community-linked **GitHub repo** (with
      stars) plus the top linked **models / datasets / Spaces** and their full
      counts, linking out to the paper's HF page. One call to
      `huggingface.co/api/papers/{arxiv_id}` (`integrations/huggingface.py`),
      day-cached in SQLite (misses too), served by `GET /api/paper/<id>/code`,
      which degrades to `available: false` on any HF failure — never 500s the
      panel. Lazily fetched per paper alongside figures; the actions row was
      restyled to fit (compact Abstract/PDF/Pin chips, full-width Explore).
      *Not done (needs one HF call per node, no batch endpoint): flagging graph
      nodes that have code.*
- [x] **Figures in agent answers** *(v1.20.0)* — the agentic Q&A can now pull a
      paper's own figures into its answer. A **full `read_paper` lists that paper's
      figures** (numbered captions) and a **`show_figure(index, figure)`** tool
      attaches one — resolved through the existing `figures.py` (ar5iv) extraction +
      the same-origin `/api/figure_proxy`, streamed as a `figure` SSE event and
      rendered (image + caption) in the answer bubble with a **click-to-enlarge
      lightbox** (backdrop / ✕ / Esc to close). Budgeted at `AGENT_MAX_FIGURES`
      (3/answer); agentic path only. A `🖼 Showed Figure N of …` trace chip marks it.
- [x] **Embed answer figures inline (not appended)** *(v1.22.0)* — each
      `show_figure` attachment now gets a 1-based **slot**, and the tool result
      instructs the agent to place a **`<<FIG n>>` marker** in its prose exactly
      where the figure belongs. The marker streams through verbatim (no SSE
      protocol change); the answer bubble **splits its text on markers and
      interleaves the figure cards** (a partial marker at the streaming tail is
      held out of the render so it never flashes). Degrades gracefully: an
      unplaced figure falls back to the old end-of-bubble strip, a marker with no
      matching figure vanishes without gluing paragraphs, and pre-v1.22 saved
      sessions render as before (new saves restore inline placement free, since
      markers live in the persisted text). Two fixes from browser testing:
      markers are **stripped from the server-side conversation history** (a model
      that saw `<<FIG 1>>` in its earlier answers skipped placing the fresh one,
      so figures degraded to end-anchoring as the chat went on), and the system
      prompt now hard-forbids the model **drawing figures itself** (ASCII art /
      box characters) — `show_figure` is the only path to visuals. *(Known limit:
      tool-call compliance is still somewhat inconsistent; see the agent-
      reliability item below.)*
- [X] **Agent reliability: stronger model or sub-agent decomposition** — even
      with the hardened prompt, the agent sometimes skips `show_figure` (or
      tools generally) and answers from context. Two levers to explore: point
      `AGENT_MODEL` at a stronger model than the default (`TEACHER_MODEL`,
      Sonnet 4.6) just for the tool loop; or **break the loop into sub-agents**
      (e.g. a researcher that reads/expands and a writer that composes) so each
      keeps a **small, focused context** instead of one long conversation
      carrying every tool result. *(Patrick's observation while testing inline
      figures, 2026-07-04.)*
- [x] **Zoom on detail-panel figures** *(v2.4.0)* — the sidebar's paper figures
      (Phase 2.1) are now click-to-enlarge, reusing the same **lightbox** the
      answer figures got in v1.20.0. Since it's now a genuine two-consumer
      component, `Lightbox.tsx` was promoted out of `teacher/figures/` to a
      new root-level `figures/` folder per the hybrid structure rule (each
      caller — `Teacher.tsx`, `graph/GraphExplorer.tsx` — still owns its own
      open/close state and instance). Caught a latent bug in the move: the
      caption line unconditionally rendered `Figure {figure.figure}`, fine
      for the teacher's always-numbered agent-cited figures but a bare
      "Figure " for the detail panel's un-numbered ones — now the label only
      shows when a number actually exists. *(From the `todos.md` inbox,
      2026-07-04.)*
- [ ] **Figures from uploaded PDFs in answers** — extend the v1.20.0 figures
      feature to the user's **own library**: pull images out of an ingested PDF
      (via `pymupdf`, which we already use for text) and let the agent surface a
      relevant one when it cites a source passage — the library analogue of
      `show_figure`, which today only covers arXiv papers (ar5iv). Needs page →
      image extraction at ingest (or on demand), a way to reference an image from
      a retrieved passage, and a `show_source_figure`-style tool + `figure` event
      reusing the existing answer-figure rendering. *(From the `todos.md` inbox,
      2026-07-03.)*
- [x] **Loading spinners for graph render + search** *(v2.2.0)* — neither the
      "Building graph…" overlay nor the "Searching Semantic Scholar…" hit-list
      note had any animated feedback, so a slow S2 fetch could read as hung.
      Added a shared `.spin` primitive (centralized in `atlas.css` — it existed
      once already, duplicated in the library upload flow; de-duped it there
      too) and wired it into both spots. *(From the `todos.md` inbox,
      2026-07-06.)*
      **Fixed in v2.2.1:** the "Building graph…" overlay was invisible whenever
      a graph was already on screen (re-seeding, or searching over an existing
      graph) — only worked on the very first load. Root cause:
      `react-force-graph-2d` sets its canvas wrapper's `position: relative`
      inline with no `z-index`, tying it with `.overlay`'s implicit
      `z-index: auto`; CSS then falls back to DOM order, and the canvas
      renders *after* `.overlay` in `GraphExplorer.tsx`, so it painted over it
      once a graph existed to render at all. Gave `.overlay` an explicit
      `z-index: 20`, comfortably above every other floating panel
      (`.controls` at 4, `.hit-list` at 5). Also, bare overlay text read poorly
      against a busy graph still on screen, so a `.canvas-scrim` now dims the
      whole canvas (graph + its controls/legend) and the overlay itself gets a
      contrasting card background — for both the loading and the graph-load
      error state (verified against a real 502 from the running server).
- [x] **File logging + honest search-failure traces** *(v2.1.0)* — `create_app()`
      now logs to a rotating file (`data/atlas.log`, 5MB × 3 backups) as well as
      the console, so agent runs survive after the terminal scrolls away.
      Diagnosing a real failure (a `search_papers` call for "BERT pre-training
      deep bidirectional transformers...") turned up two gaps: the researcher's
      `search_papers`/`expand_node` tools caught `S2Error` but never logged it
      (unlike `show_figure`/`search_sources`), and the "Tried" trace chip looked
      identical whether a search failed on an S2 error, an empty query, the
      overall step budget, or — the actual cause here — the search-specific
      budget (`BUDGETS["searches"] = 3`) already being spent by earlier calls
      in the same turn. Fixed both: added the missing `log.warning` calls, and
      gave `SearchTrace` a `reason` field (`empty_query` / `steps_exhausted` /
      `budget_exhausted` / `error`) that the chat UI now renders as a specific
      annotation instead of a bare "Tried" (older saved sessions without the
      field still fall back to the old generic wording).
      *(From the `todos.md` inbox, 2026-07-06.)*
      **Next:** sweep other silent-failure spots (other agent tools, route
      error paths) that should log before returning a user-facing message.
- [x] **Rank citations/references by citation count, not S2's default order**
      *(v2.1.1)* — a heavily-cited old seed (e.g. Hawking's "Black hole
      explosions?", 5,143 citations) was showing an almost entirely 2026,
      near-zero-citation "citations" neighborhood. Root cause: S2's
      `/paper/{id}/citations` and `/references` endpoints take no `sort` param
      and default to a genuinely chronological, newest-first order (confirmed
      by sampling `offset` across the full range) — so a small `cite_limit`
      filled up entirely with this year's obscure citing papers before a
      single famous one was ever seen. Fixed in `_neighbors()` (shared by
      `references()`/`citations()`): over-fetch up to S2's hard per-call cap
      (1000 — 1001+ returns HTTP 400) and rank the pool by `citation_count`
      locally before trimming to the configured limit. Verified against the
      Hawking paper: citing papers went from 0–1 citations each to 40–268.
      *Known limit (discussed and accepted):* a single call still only
      reaches ~1000 of the newest citations, so an extremely well-cited old
      paper's neighborhood still skews toward the last few years rather than
      spanning its full multi-decade citation history — truly reaching decades
      back would need a few extra stratified-`offset` calls per seed/expand,
      trading latency/API load for it. Shipping the single-call fix for now;
      revisit if the recency skew is still too tight in practice.
- [ ] **No single-letter identifiers** — sweep the codebase (backend +
      frontend) for single-letter variable/parameter names and rename them to
      say what they hold; add this as a standing convention, not just a
      one-time cleanup. *(From the `todos.md` inbox, 2026-07-06.)*
- [ ] **Live per-relation count sliders** — in the graph workspace, sliders to
      control how many references/citations/similar papers are shown, live
      (today's counts are fixed at build time by `ref_limit`/`cite_limit`/
      `similar_limit`). Raising a slider past what's already on screen should
      pull more from the *original* search results rather than re-querying
      from scratch — needs the backend to either over-fetch and cache a
      larger pool per seed (see the citation-ranking fix, v2.1.1, which
      already over-fetches up to S2's 1000-per-call cap) or support paging
      further into it on demand. *(From the `todos.md` inbox, 2026-07-06.)*
- [ ] **Recency preference for citations** — let the user choose whether the
      papers citing the seed skew **older** (closer to the seed's own year —
      the field's early response) or **more recent** (the current frontier),
      rather than always ranking purely by citation count (v2.1.1). Probably
      a control alongside the citation-count ranking rather than a
      replacement for it — citation count is what rescued citations from
      S2's recency-biased default order in the first place; this would be a
      second axis (age vs. count) the user tunes, not a reversion.
      *(From the `todos.md` inbox, 2026-07-07.)*
- [x] **CLI → `click`** *(v1.11.0)* — replaced the hand-rolled `argparse` in
      `run.py` with a `click` group (same command names: `serve`, `ingest`,
      `sources`, `search-sources`, `forget`).
- [x] **"Powered by Claude"** *(v1.11.0)* — subtle top-bar credit (Anthropic
      sunburst mark + "Powered by Claude", linking to anthropic.com/claude);
      names the model the AI teacher actually runs on, not the build tool.
- [x] **Deselect-all in the assistant source scope** *(v1.20.1)* — the source-scope
      popover only had **Select all**; added a **Deselect all** (shown whenever any
      source is checked) so you can clear and then pick a few, rather than unchecking
      many by hand.
- [x] **Empty source scope means "search nothing"** *(v1.20.2)* — corrects
      v1.20.1: an empty checkbox set used to fall back to "search the whole
      library" (both extremes behaved the same). Now the three states are
      distinct — all checked = whole library, a subset = just those, **none
      checked = search no sources**. Threaded a `None` (no scope → all) vs `[]`
      (explicit empty → nothing) distinction through `sources.search`, both ask
      routes, `answer_agentic`, and the `search_sources` tool.
- [x] **Filter popover stays open after Explore** *(v1.18.1)* — the seed-search
      filter popover didn't close when a search fired; `Search`'s form `onSubmit`
      now collapses it (`setOpen(false)`) before running the search.
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
