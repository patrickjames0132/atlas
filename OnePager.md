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
> artifact links via Hugging Face Papers (v1.23.0), per-seed cache-clear Refresh
> button (v2.5.0), Semantic Scholar field-of-study tags in the detail panel
> (v2.6.0), "What's evolved since" forward lecture mode (v2.7.0)
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

> A single top-to-bottom checklist, grouped by theme. **Shipped** work is up top (each item keeps its full history + version tag); **unshipped** work is the **Backlog** at the bottom. Version tags carry the true chronology — the grouping does not.

### Foundation & the v2 rewrite

- [x] **Phase 0 — One-pager** (this file)
- [x] **Phase 1 — Backend pivot to Semantic Scholar** *(v1.0.0)* —
      `semantic_scholar.py` client (batch hydration to dodge the single-GET
      throttle, 429 backoff, optional `S2_API_KEY`), `graph.py` neighborhood
      builder, thin `cache.py` (graph snapshots), new `/api/graph` & `/api/paper`
      routes. Seed accepts an arXiv id **or** a raw S2 paperId. *(The deeper
      teardown of the legacy digest backend was completed later — see
      **Phase 2.3 — Legacy teardown** below.)*

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


### Graph explorer & timeline

- [x] **Phase 2 — Graph explorer frontend** *(v1.0.0)* — force-directed canvas
      (`react-force-graph-2d`), seed via arXiv search, nodes colored by relation
      / sized by citations / edges typed & directed, detail panel with `tldr`.
      **Declutter controls:** relation filters (refs/citations/similar) with
      counts, a dual-handle **year range** slider, **drag-to-pin** (+ release
      all), **focus-on-hover** dimming, and a papers-shown readout. **Visual
      traversal:** double-click (or "Explore from here") re-seeds the graph on
      any node — journal papers included.
- [x] **Phase 2.2 — Timeline layout** *(v1.3.0, month granularity v1.3.1)* — a
      **Force ↔ Timeline** toggle. Timeline pins each node's x to its **publication
      date** (year + month fraction from S2 `publicationDate`, so papers sit
      *between* the yearly gridlines; the detail panel shows the full date) while
      the sim resolves y; a `d3-force-3d` **collision force** (radius-sized) spreads
      papers out within a year column, and once settled **y is frozen** so a drag
      can't re-scramble the layout. A faint **year axis** is drawn behind the
      graph (labels thinned when zoomed out); narrowing the year slider **zooms
      into that span**. So the chronological lecture sweeps left→right as nodes
      light up. Force was the default at launch (**Timeline became the
      default in v2.4.1**); switching layout releases all pins. (A
      relation-band variant remains a possible later sub-toggle.)
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
- [x] **Default to Timeline, not Force** *(v2.4.1)* — a fresh page load, going
      Home, and restoring an old saved session that predates the `layout`
      field all used to fall back to Force; all three now default to
      Timeline instead (`store/workspace.ts`'s `initialState`,
      `workspaceCleared`, and `restoreSession`'s missing-field fallback).
      Sessions that explicitly saved a layout — Force or Timeline — are
      unaffected; this only changes what happens when there's no stored
      preference at all.
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
- [x] **Optional per-seed cache clear** *(v2.5.0)* — a **Refresh** button in the
      graph controls (beside Release / Fit) busts the cached graph snapshot
      (`data/digest.db`'s `cache` table) for the current seed on demand, rather
      than only living with the 1-day TTL — useful when S2's data for a paper
      visibly changes mid-session. Reuses the backend's existing `refresh=1`
      path (bypass read → rebuild from S2 → upsert the snapshot), which was
      wired end-to-end but never triggered from the UI. Frontend-only: the
      workspace slice now records the **exact seed reference** the graph was
      loaded with (`seedRef`) so Refresh replays the same string and busts the
      *right* cache key — a double-click re-seed keys by S2 paperId, a search by
      arXiv id — rather than a stale duplicate. *(From the `todos.md` inbox,
      2026-07-07.)*

### Search & seeding

- [x] **Phase 2.4 — Cache-first seed search** *(v1.6.0)* — seed-search results
      served from the **local snapshot cache instantly**, before (and independent
      of) the live arXiv search: `/api/local_search` scans cached graph snapshots
      by title/authors, ranks phrase matches → explored seeds → citation count,
      and flags papers whose own neighborhood is freshly cached (an **instant**
      badge — those explore without touching the rate-limited API). Live arXiv
      results append below when they land; if arXiv is unreachable, the cached
      papers still work. Born of a real rate-limited evening.

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
- [x] **Filter popover stays open after Explore** *(v1.18.1)* — the seed-search
      filter popover didn't close when a search fired; `Search`'s form `onSubmit`
      now collapses it (`setOpen(false)`) before running the search.

### Detail panel & paper enrichment

- [x] **Phase 2.1 — Sidebar enrichment** *(v1.2.0)* — under the detail panel's
      TL;DR, the paper's **own figures with their captions** (`figures.py`
      extracts them from **ar5iv** HTML, cached 30 days; images streamed through
      a same-origin `/api/figure_proxy` locked to the ar5iv host — no hotlink
      reliance, no open proxy; tables skipped; graceful fallback where ar5iv has
      no render), plus a **direct PDF link** beside the arXiv-abstract link.
      Shipped alongside a UI polish: the year filter is now a single
      **dual-thumb range slider** (two overlaid inputs on one track + fill)
      instead of two stacked sliders.
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
- [x] **S2 categories as detail-panel tags** *(v2.6.0)* — alongside the v2.3.0
      arXiv category pills, the detail panel now surfaces Semantic Scholar's own
      field-of-study classification (`s2FieldsOfStudy`, falling back to the
      coarser `fieldsOfStudy`) as tags. Rendered as **two provider-labeled
      sections** (styled like "Code & artifacts") — an **arXiv tags** section
      and a **Semantic Scholar tags** section (accent-tinted) — so it's clear
      who tagged what; a non-arXiv paper shows the S2 section alone. No new
      endpoint: S2 already returns these on the paper object, so the fields ride
      along with the existing detail hydration (`DETAIL_FIELDS`) — light on
      graph neighbors, filled in on click like the abstract/TL;DR. The normalized
      node gained a `fields_of_study` list (deduped, order-preserving), defaulted
      on the `Node` model so snapshots cached before it still validate.
      *(From the `todos.md` inbox, 2026-07-07.)*
- [x] **Proper subscripts & math notation** *(v3.2.0)* — paper text surfaces
      (titles, abstracts, TL;DRs, lecture beats, answers, search hits, figure
      captions) now render **delimited LaTeX** (`$…$`, `$$…$$`, `\(…\)`,
      `\[…\]`) with **KaTeX**, via a shared `frontend/src/notation/` package:
      `<MathText>` for the DOM surfaces, `latexToUnicode` for graph node labels
      (canvas — KaTeX can't reach it, so β₂ is a best-effort Unicode
      approximation). Scoped to *delimited* math only — bare "CO2"/"H2O" is left
      alone (auto-subscripting digits misfires on "GPT4", "COVID19"). Shipping
      it surfaced a backend bug: ar5iv figure captions arrived as tripled MathML
      soup (`subscriptitalic-ϵ…`); the fix emits each `<math>`'s clean `alttext`
      LaTeX instead — see [Bugs](#bugs--notable-found--fixed). Deferred to a later ticket:
      user-uploaded source titles and researcher trace chips.
      *(From the `todos.md` inbox, 2026-07-08; shipped 2026-07-08.)*

### AI teacher & lectures

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
      **Retired in v3.0.0** — lectures no longer expand the graph (see
      "Lectures never expand the graph" under Enhancements); the history
      lecture now narrates the visible ancestors, ending at the seed.

- [x] **Phase 3f — "What's Evolved Since" lecture mode** *(v2.7.0)* — a **third
      lecture button** alongside "How We Got Here" (history) and "This Paper's
      Intuition" (intuition), completing the **past → present → future**
      triptych. It's the exact **mirror of the history backfill**: the shared
      walk was refactored into one `_walk(direction=…)`, and evolution runs it
      *forward* — launching from the **newest visible descendants** (launching
      from the seed itself just re-finds its already-shown citations and
      stalls), hopping **citations** (each hop reaches strictly newer work),
      keeping the most-cited new papers, and marching toward the present with no
      year ceiling (nothing can be cited by the future). The orchestrator runs
      `forward_backfill` before narrating (same enrich-then-lecture path as
      history); discoveries merge as descendants (dashed rings, far-**right** in
      Timeline). `BackfillTrace` gained `direction`/`newest` (a forward hop
      reports the newest year reached), rendered as **"⏩ Traced forward to
      \<year\>"**; a new EVOLUTION mode-intent tells the lecturer to start at the
      seed and move forward to the current frontier. Kept deterministic and
      LLM-free like the history walk — the roadmap's optional `search_papers`
      frontier-grab was deferred. *(From the `todos.md` inbox, 2026-07-07.)*
      **Walk retired in v3.0.0** — lectures no longer expand the graph; the
      mode (button, intent, seed-onward scoping) lives on, narrating the
      descendants the even-by-year citation spread puts on screen (see
      "Lectures never expand the graph" under Enhancements).

- [x] **Lectures never expand the graph — backfill walks removed** *(v3.0.0)* —
      a doctrine change: a lecture narrates the graph **as the user built
      it**; only the researcher (explicit Q&A) may pull new papers onto the
      canvas. The deterministic history/evolution backfill walks (Phase
      3e/3f) were removed end-to-end — `orchestrator/backfill.py` + tests
      deleted, the lecture intent is pure delegation, `BackfillTrace` left
      the event vocabulary, the `graph.backfill` config knobs are gone, and
      the panel's "⏳/⏩ Traced…" chips + the saved-session `hist_trace`
      field were retired (old saves still restore; the field is ignored).
      The **directional modes are also scoped to their side of the seed**
      (`_story_nodes`): "How we got here" receives only the seed + papers
      published in or before its year — the story ends AT the seed — while
      "What's evolved since" receives the seed onward; intuition/bridge see
      everything (undated papers sit out of the clamped modes; an undated
      seed disables the clamp). **Scoping reworked in v4.8.0** — modes are now
      pinned to a graph *relation* (references / landmark citers / latest), not
      a year clamp (see "Lectures tightened" above).
- [x] **Lectures tightened: per-relation scoping, a PDF-reading intuition, and
      full-span guardrails** *(v4.8.0)* — each lecture is now pinned to one graph
      relation instead of a slice of the timeline (`_story_nodes`): "How we got
      here" narrates the seed's **references**, "Summarize the landmark papers
      since" (renamed from "What's evolved since") the **landmark citers**, "The
      current frontier" the **Latest Publications**, and "This paper's intuition"
      the **seed alone** — so the four stories no longer overlap and
      loosely-`similar` work never leaks into a directional lecture. **Intuition
      now reads the PDF:** the ar5iv reader preserves equations as LaTeX
      (`keep_math` lifts the MathML `alttext`, KaTeX-rendered), and the intuition
      lecture pulls the seed's full text to teach it in detailed chapters with
      real math. **Full-span guardrails** stop a lecture clustering on the
      oldest, most-cited papers: the numbered list is sorted oldest-first and
      banded by era (`node_lines_by_era`), a concrete YEAR₁–YEAR₂ span line plus
      the `_SPAN_NUDGE` tell the model to reach both ends, and beat counts
      widened 5–9 → 7–12. The current frontier stays a **thematic** survey
      (grouped into current threads) but oriented forward in time. `frontier_
      window_months` no longer filters nodes (the `latest` relation already is
      the recent frontier) — it only frames the FRONTIER narration now. Closes
      "Lectures should span the whole publication history." *(Patrick's asks,
      browser-tested 2026-07-10.)*
- [x] **Lecturer knobs: configurable frontier window + beat-count bounds**
      *(v4.2.0)* — the lecturer gained an `extras` staging area in its
      `config.llm.agents` entry (the researcher's budget pattern — unknown
      keys fail at import). **`frontier_window_months`** (default 60) widens
      "The current frontier"'s recency window from the hardcoded 12 months
      to **~5 years**: since the v4.0.0 OpenAlex hybrid, the light-green
      Latest Publications nodes span the newest years plus the
      `latest_band_years` per-year bands below them, so a 12-month lecture
      narrated almost none of what the graph actually shows as "latest."
      The FRONTIER mode-intent phrases the same window into the prompt
      (`_window_phrase`) so the narration and the `_story_nodes` filter
      can't drift, and the year-only fallback for OpenAlex's coarse dates
      now errs toward inclusion (the cutoff's year, not a hardcoded
      `today - 1`). **`min_beats` / `max_beats`** (default 5–9) make the
      lecture's bubble count tunable — phrased into the system prompt
      ("exactly N" when both ends pin to the same value); a prompt bound,
      not a hard output cap. *(Patrick's asks, browser-tested 2026-07-09.)*
- [x] **Refocus "This paper's intuition" on the seed itself** *(v3.0.0)* — the
      intuition lecture no longer reads like a second "How we got here": its
      mode-intent now walks the paper's own components (the problem, the core
      idea, how the method actually works, what the results showed, why it
      works), naming surrounding papers only in passing for contrast. It's
      also **grounded in the seed itself, deterministically** (the lecturer
      stays tool-free): the seed's own **ar5iv figures** are fetched before
      the run and listed by caption — the model attaches the most
      illuminating one to the beat it belongs to (a `figure` number resolved
      to a proxied image on the beat; hallucinated numbers just mean no
      figure) and the panel renders it inline under the beat (click to
      enlarge) — and, when a **local library** exists, hybrid retrieval on
      the seed's title supplies passages the lecture may draw on, attributed
      inline. **History and evolution are illustrated too:** their figure
      pool draws from the seed plus the story's landmark papers (the 4
      most-cited arXiv papers on the mode's side of the seed, 3 figures
      each, source-paper attributed on the card); bridge stays figure-free.
      *(From the `todos.md` inbox, 2026-07-07.)*
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
- [x] **"Powered by Claude"** *(v1.11.0)* — subtle top-bar credit (Anthropic
      sunburst mark + "Powered by Claude", linking to anthropic.com/claude);
      names the model the AI teacher actually runs on, not the build tool.

### Bring-your-own sources

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
- [x] **Windows PDF upload fix** *(v1.10.1)* — source ingest used a
      `NamedTemporaryFile` whose exclusive lock on Windows made the reopen fail
      with `[Errno 13] Permission denied`; switched to `mkstemp` + manual cleanup.

### Citation graph — landmark/latest & mega-papers

A reframe of the mega-paper citation story, decided with Patrick after we shelved
the stratified-sampling + velocity WIP. **Drop stratified offset windows
entirely.** One newest-≤1000 citation fetch does double duty, splitting citations
into two relations with distinct meaning, colour, filter, and (later) slider:

- **Landmark citations** (keep green `#4ade80`) — the most-cited papers citing the
  seed, "the giants that built on this." Reachable citation list ranked by citation
  count for normal papers; **mining-first** for mega papers (mine reachable citers'
  reference lists → verify → rank by citations, pruned to ≤ last year). No
  stratified windows → a mega build is ~3 S2 requests (1 fetch + 2 mining batches).
- **Latest citations** (NEW, light green `#86efac`) — citers from the **rolling
  last 12 months** (via `pub_date`), from the same fetch. "The frontier, right now."

- [x] **Adaptive latest-band boundary — a trained model sizes the Latest span
      per seed** *(v4.6.0)* — Field Landmarks are a seed's all-time most-cited
      citers (any year); *Latest Publications* fills recent years evenly, one
      `cited_by_count` query per year, from the band start **up to the current
      year** (this ship also **retired the separate newest-date window** — latest
      is now uniform per-year bands the whole way, so every recent year gets its
      own fair slice). The band's lower edge was a **fixed** `latest_band_years`
      offset (5 → start 2020). For an *old* seed whose landmark cluster tails off
      years before that, the timeline showed a dead stretch between the last
      landmark and the first band. Now the band start is chosen **per seed** from
      the recent edge of the landmark distribution: `citation_relations` hands the
      shipped landmarks' years to `bands.earliest_band_year`, which places the
      start at the **density tail edge** — the most recent year still holding ≥
      `tau` of the peak year's landmark count — floored by a `max_span` cost cap.
      No only-widen clamp, so a young seed whose cluster edge is recent gets a
      *tight* frontier too (Hawking → start 2020 / 7 bands; QMIX → 2024 / 3 bands).
      **Derived from data, not hand-tuned:** a new `ml_pipelines/latest_gap/`
      pipeline reuses the `cite_budget` seed sample, pulls each seed's
      shipped-landmark year distribution, and fits `tau` on **misdate-robustness**
      (**tau=0.25, max_span=7**; only ~1/64 seeds' boundary movable by a two-citer
      misdate), serialized to `ml_pipelines/models/latest_gap.joblib`; the app
      loads it in `services/graph/bands.py` and degrades to the fixed span when it
      can't. The rule is injected as a callable so `integrations/openalex` stays
      below `services`. Findings: **seed features can't predict the boundary** —
      a regression on age + log-citations (as `cite_budget` uses) scored a
      *negative* CV R²; and a **quantile is the wrong detector** — it's mass-based,
      so a large old bulk drags it years before the cluster's visible edge
      (Hawking's 0.85 quantile is 2013, but the cluster stays dense to ~2020). The
      density tail edge tracks where the count actually falls off.
      `research/latest_gap/analyze.ipynb` is the write-up. Config:
      `graph.adaptive_latest_band` (on by default). *(Backend heuristic; anchors
      eyeballed by Patrick, 2026-07-10.)*
- [x] **Adaptive landmark budget — a trained model sizes `cite_limit` per seed**
      *(v4.5.0)* — the flat landmark budget showed the same node count for every
      seed; now the ship count is **predicted from the seed's age + citation
      count**, so an old classic (Hawking) keeps a large, map-like set (~160)
      while a young, hot paper (DQN ~60, Attention ~30) gets a tight one — its
      top citers are same-era pile-on rather than a legible map. **Derived from
      data, not hand-tuned:** a new `ml_pipelines/cite_budget/` pipeline pulls
      ~60 OpenAlex seeds stratified by year × citations and labels each with its
      "density budget" n* — the longest citation-ranked citer **prefix** (first N
      from the top) before any single publication year floods past `K=12`, i.e.
      where temporal clutter sets in — then fits a scikit-learn
      `LinearRegression` (5-fold CV R²≈0.68), serialized to
      `ml_pipelines/models/cite_budget.joblib`. The app **loads the model** and
      calls `.predict()` per build (`services/graph/budget.py`), clamped to
      `[floor, cite_limit]`, sharing `compute_features` with training so there's
      no train/serve skew; a missing/broken artifact degrades to the flat
      `cite_limit`. `research/cite_budget/analyze.ipynb` is the exploratory
      write-up. Config: `graph.adaptive_cite_limit` (on by default; `cite_limit`
      is the ceiling). Finding: **age carries the signal** (r≈0.84); the "more
      citations → tighter budget" intuition didn't survive controlling for age
      (the citation term came out mildly *positive*). *(Backend heuristic;
      anchors eyeballed by Patrick, 2026-07-10.)*
- [x] **OpenAlex hybrid citation source** *(v4.0.0 — major; supersedes the
      S2 mining/stratified-sampling approach for citations)* — the culmination of
      the OpenAlex spike (below, now retired). **OpenAlex owns the citation
      relations; S2 keeps the seed resolve, references, *Similar*, and TL;DRs**,
      matched by DOI / arXiv id. A new `integrations/openalex/` package (client →
      nodes → traversal) mirrors `semantic_scholar/`; `services/graph/build.py`
      calls it via `_citation_relations`, **falling back to S2** when OpenAlex
      can't resolve the seed (so the graph is never worse). The whole S2
      landmark-**mining + verification** apparatus (`_mined_landmarks`,
      `_cites_seed`, `citation_mining` config) is **deleted** — OpenAlex's sorted
      `cites:` queries make it dead code. Highlights, each validated live and the
      graph now builds **far faster** (no deep-paging + 429 backoffs):
      - **Field Landmarks** = the all-time most-cited citers
        (`cites:<id>&sort=cited_by_count:desc`) — the historic giants, returned
        directly, no mining, edge guaranteed by the filter. Fixes the landmark
        recency bias at the root (Hawking's 1974 early band — Page '76,
        Gibbons–Hawking '77, Unruh '81 — surfaces immediately).
      - **Latest Publications** = recent citers: a newest-window query plus
        **per-year bands** (`latest_band_years`×`latest_per_year`) for even
        coverage, excluding anything that's already a landmark. The split
        self-adjusts per seed and leaves no gap between the relations.
      - **Split by publication YEAR, not exact date** — OpenAlex dating is coarse
        (year-only works default to `<year>-01-01`), so a rolling *date* window
        silently drops recent citers (DQN: 1 vs 30). See Bugs.
      - **Cross-source node identity** — OpenAlex citer nodes carry
        S2-resolvable ids (`DOI:` / `ARXIV:` / bare `W…`), so the existing paper
        routes hydrate their TL;DRs (via S2) and re-seed them unchanged.
      - **Metered pricing handled** — free API key $1/day, keyless $0.10/day,
        id/DOI lookups free; a per-seed build is a handful of filter calls.
        `OPENALEX_API_KEY` optional (`config.providers.openalex`). *(Browser-tested on
        hawking radiation / attention / dqn, 2026-07-09.)*
- [x] **Latest Publications slider reveals oldest-first** *(v4.1.0)* — the
      reveal slider used to surface the newest citers first and work *backward*
      into the banded years; inverted so rank 0 is the **oldest** banded-year
      paper and the slider walks forward through time toward the present
      (reads naturally left→right in Timeline). Selection is untouched — a
      `latest_limit` still keeps the **newest** N; only the shipped order of
      the survivors flips (pinned by a dedicated test). Backend-only (the
      slider is a pure `rank < value` reveal): the flip lives in the OpenAlex
      traversal **and** the S2 fallback, so both citation sources agree.
      *(Patrick's browser observation, 2026-07-09.)*
- [x] **Even citation spread across the years** *(v3.0.0 — supersedes "Recency
      preference for citations")* — instead of a user-facing older/newer knob,
      the seed's citations are now **always** selected **evenly across
      publication years**: the pool is bucketed by year (most-cited first
      within each) and round-robined, so sparse early years surface and no
      busy year monopolizes the count. For mega-cited seeds (beyond the
      1000-paper page), the pool is built by **stratified offset sampling**
      across S2's newest-first citation list (5 windows from the newest to the
      deepest reachable under S2's ~9k offset ceiling; windows S2 rejects
      degrade gracefully), so the spread covers the seed's whole descendant
      era instead of just the recent tip. No toggle shipped — even-by-year is
      simply how graphs build now (references keep the most-cited ranking; a
      reference list is naturally year-spread already). This is what gives
      "What's evolved since" a real timeline to narrate. **Known limit:** on
      truly mega-cited papers (≳10-20k citations, e.g. "Attention Is All You
      Need") the ~10k offset ceiling traps every stratum in the newest few
      months — see "Mega-paper citation coverage" in the unfinished items
      below.
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
- [x] **Ship A — backend split + `latest` relation** *(v3.3.0)*. New `latest`
      edge type through `model.py`/`build.py`/counts; `citation_relations()`
      splits one newest-page fetch into mining-first landmark selection + a
      12-month `latest` partition (dropped the `_STRATA`/`_STRATUM_LIMIT`/
      `_MAX_OFFSET` sampling). Frontend: light-green colour + an on/off **filter
      chip** for latest (no slider — deferred to Ship C). **Mining hardened
      while testing:** budgets made operator-tunable (`graph.citation_mining.
      sources`/`.candidates`), candidate ranking switched from raw citations to
      **co-citation frequency** (so off-topic giants don't burn verification
      slots), and verification **chunked + best-effort per chunk** (survives a
      429, and `candidates` may exceed the 500-id batch cap). Flow documented in
      `integrations/semantic_scholar/README.md`. *Known ceiling: hyper-cited
      seeds (DQN ~16 landmarks) are capped by S2 truncating nested `references`
      arrays + the "invisible unless a source cites it" limit — see README.*
- [x] **Ship D — page deeper to complete the latest window + fill the landmark
      middle band** *(v3.4.0)*. `_fetch_citers(deep=True)` pages the citer list
      (offsets 0, 1000, 2000…), stopping at the first page with no in-window
      citer, the list end, or the `_MAX_OFFSET` (~10k) ceiling. `latest` now
      covers the *whole* rolling window; the citers just past the boundary fill
      the landmark middle band. **Verified on DQN: ~3k citers paged, landmark
      relation went 16 → the full `cite_limit` (60) of real 2016–2024 citers,
      evenly spread.** For hyper-cited seeds (AIAYN) the past-ceiling tail still
      comes from mining — complementary. Graph expansion (`citations()`) stays
      one page. Paired **429 hardening**: `client.request` default `tries` 4 → 6
      (backoff to 16s) so a mega build's ~10 pages ride out sustained 429s;
      `min_interval` is the further lever. *(From the `todos.md` inbox, 2026-07-08.)*
- [x] **Ship B — "The current frontier" lecture** *(v3.5.0)*. New
      `LectureMode.FRONTIER` ("The current frontier"); `_story_nodes` scopes it to
      seed + any-relation nodes from the last ~12 months (absolute recency, not
      relative to the seed) — so it **folds in recent `similar` nodes too**,
      alongside the `latest` citers. `MODE_INTENTS` intent (survey the newest work
      as current threads, distinct from EVOLUTION's full arc), figure pool wired,
      frontend mode button + `LectureMode` type. Completeness guard added
      (`set(MODE_INTENTS) == set(LectureMode)`). **Window configurable since
      v4.2.0** (`frontier_window_months` lecturer extra, default ~5 years —
      see "Lecturer knobs" under AI teacher & lectures). **Rescoped in v4.8.0**
      to the `latest` relation only (no longer folds in `similar` nodes, and
      the window stopped filtering nodes — see "Lectures tightened" above).
- [x] **Ship C — live per-relation count sliders** *(v3.6.0)*. Each `Edge`
      carries a `rank` (its index in the relation's order — references/citations by
      influence, latest by recency, similar by S2); the backend ships the whole
      ranked set per relation (the `*_limit` config values became **ship counts =
      each slider's max**, and are now **nullable** — `null` ships *everything* the
      paper has, so the slider maxes to the full count) and the frontend slider is
      a **pure client-side reveal** of `rank < value`, defaulting to 25, no
      re-query. UI: a clean aligned grid (dot+label toggle · slider · `N/max`) —
      references/**Field Landmarks**/**Latest Publications**/**Similar** (chip
      relabel folded in). The **agent-grounding fix** rode along (it had to —
      sliders hide nodes, so grounding is now visible ∪ discoveries, via
      `visibleNodeIds`). Salvaged the slider UI + `rank`/grounding mechanics from
      `stash@{0}`; dropped its `pool_limit` cap per the new design. *(Slider from
      the `todos.md` inbox, 2026-07-06; fetch-everything + relabel + nullable limits
      2026-07-08.)*

  **→ Phase complete (A → D → B → C shipped, v3.3.0–v3.6.0).** The mega-paper
  citation story is now: deep-paged landmark/latest split, co-citation mining for
  the past-ceiling tail, a current-frontier lecture, and live per-relation
  sliders over the whole ranked pool.

  - **Shelved WIP — `stash@{0}`** ("WIP v3.3.0-candidate: velocity reveal-order +
    configurable citation_pool …"), sitting on top of the earlier
    sliders/grounding/clutter stash — **superseded by the plan above** but kept
    for cherry-picking. Reusable bits: the **agent-grounding fix** (`GraphExplorer`
    publishes `visibleNodesSet`; `selectGroundingNodes` → visible ∪ discoveries —
    was browser-verified), the **clutter retune** (Timeline day-of-year spread via
    `withinYearFraction`), the **pool_limit/rank slider mechanism** (for Ship C),
    and a **`_velocity` helper** (`citation_count / (age + 1)`). Patrick chose to
    keep the grounding fix + clutter retune out of Ship A for now — revisit.
- [x] **Mega-paper citation coverage — beat the ~10k offset ceiling**
      *(v3.1.0)* — the
      v3.0.0 even-by-year citation spread has a known blind spot on truly
      mega-cited papers. S2's `/citations` endpoint returns citing papers
      **newest-first**, offers **no server-side sort**, and **rejects any
      request past `offset + limit` ≈ 10k** (hence `_MAX_OFFSET = 9000` in
      `_stratified_pool`). The stratified fetch can therefore only sample
      inside the newest ~9.2k citations — for **"Attention Is All You Need"
      (~150k citations, tens of thousands per year)** that's the top ~6% of
      the list, i.e. the last few months, so every stratum lands in 2026 and
      the even-by-year selection has exactly one year-bucket to spread over.
      Even a landmark 2019 citer (BERT-class famous) sits ~100k entries deep
      — S2 will simply never return it through this endpoint. (DQN at ~15k
      citations is only partly affected: offset 9000 reaches ~60% of its
      list, back to the mid-2010s, but its oldest citers are past the
      ceiling too.) **Decided design — the heuristic as a pool-builder, not
      a replacement.** The final even-by-year selection stays (pure
      most-popular would re-clump in the hot years, losing the frontier);
      the heuristic only enriches the *pool* it selects from. Three-tier
      dispatch in `citations()`: **≤1000** citations → single page (the
      complete list, exact); **1k–ceiling** → stratified offset windows
      (unchanged); **past the ceiling** → stratified windows for the
      reachable slice PLUS **landmark mining**: harvest the reference lists
      of the pool's most-cited recent citers (surveys are goldmines — they
      cite every landmark), rank candidates by their own citation count, and
      **verify each candidate actually cites the seed** before keeping it —
      a candidate merely co-appearing in reference lists is NOT proof, and
      the graph must never invent a citation edge (verification via one
      batched `references.paperId` lookup). Verified landmarks join the pool
      (influential flag unknowable → False) and even-by-year does the rest:
      BERT-class 2018-2020 landmarks AND the 2026 frontier, honestly edged.
      Mining is best-effort — either batch failing just degrades to the
      reachable pool, never fails the build. (A first cut also carried a
      `deep_citations` retry mode and adaptive client pacing, built against
      one congested S2 night; the congestion turned out to be transient, so
      both were dropped as overkill — the ship is mining + stratified
      windows + even-by-year, nothing more.)
      Alternatives kept on file: year-filtered citation queries *if* S2 ever
      adds them (trivial then), or the S2 Datasets bulk dump (full
      enumeration, but against the "no local corpus" philosophy). *(From a
      live v3.0.0 session on 1706.03762, 2026-07-07; design settled same
      day.)*

### Saved sessions & workspaces

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

### Infrastructure, quality & tooling

- [x] **Phase 2.3 — Legacy teardown** *(v1.4.0)* — retired the digest-era backend
      now that Atlas stands on its own: deleted `store.py`, `pipeline.py`,
      `summarizer.py`, `embeddings.py`; slimmed `search.py`/`arxiv_client.py` to
      just the seed search; removed 8 legacy `app.py` routes + 8 unused `api.ts`
      functions; trimmed dead `config.py`/`.env.example` settings; `run.py` is now
      `serve`-only. `taxonomy.py` kept **dormant** for near-term features. (See
      "Deliberately dropped" below for the what/why.)
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
- [x] **No single-letter identifiers** *(v2.4.2)* — swept the whole codebase
      (backend `src/atlas`, `frontend/src`, **and** `test/`) clean of
      single-letter variable / parameter / loop / comprehension / generic-type
      names, renaming each for what it holds: `node` not `n`, `event` not `e`,
      `query` not `q`, `top_k` not `k` (threaded through the public
      `sources.search(...)` kwarg and its callers/tests), `Item` not `T`,
      `(prev) =>` in setState updaters, `catch (error)`. Left the genuinely
      non-single-letter shorthands already in the code (`ctx`, `fg`, `lo`/`hi`,
      `err`, `msg`, `buf`, `frac`) and external property names we don't own
      (react-force-graph's `node.x`/`.y`, the `_s`/`_t` endpoint fields, the
      `"q"` API keys). Made it a **standing convention** in `CLAUDE.md`
      ("Code conventions") so it doesn't drift back. Behavior-neutral: the whole
      quality gate (ruff, strict mypy, 277 tests, tsc + oxlint) stays green.
      *(From the `todos.md` inbox, 2026-07-06.)*
- [x] **CLI → `click`** *(v1.11.0)* — replaced the hand-rolled `argparse` in
      `run.py` with a `click` group (same command names: `serve`, `ingest`,
      `sources`, `search-sources`, `forget`).
- [x] **Session bootstrap scripts + pinned toolchain via mise** *(2026-07-09,
      no version bump — dev tooling, not the app)* — a session that opened on a
      stale env used to fail confusingly (v3.8.0's markdown deps missing from
      `node_modules` broke the frontend build; trivy absent meant nox silently
      skipped the security scan). Now `.tool-versions` pins the toolchain
      (python 3.14.0, uv 0.11.25, nodejs 24.18.0, trivy 0.72.0) and
      **`bin/setup.bat`** (Windows) / **`bin/setup.sh`** (macOS/Linux) — the
      mandated first step of every Claude session, per `CLAUDE.md` — runs
      `mise install` + `reshim`, `uv sync`, and `npm install` + `npm run build`
      for the frontend. **mise** was chosen over asdf deliberately: asdf has no
      Windows support at all (Patrick's primary machine), while mise runs on
      Windows *and* macOS and reads the same asdf-format `.tool-versions`, so
      the pin file stays portable either way.
- [x] **Config reorg: data APIs grouped under `providers`** *(v4.3.0)* — the
      top-level `s2` and `openalex` config groups moved into one
      **`providers`** object (`config.providers.s2.*`,
      `config.providers.openalex.*`), mirroring how `llm.providers` groups
      the LLM vendors — connection settings (keys, URLs, timeouts,
      throttles) now live together per external data API, and adding a
      future source is a field, not a redesign. The LLM vendor model was
      renamed `ProvidersConfig` → `LLMProvidersConfig` so the two
      "providers" concepts can't collide in code. Mechanical rename across
      ~10 consumer modules + tests + docs (`docs/configuration.md` gained a
      `providers` section with an OpenAlex subsection). **Breaking for
      `config.json`** (it's gitignored and single-user, so shipped as a
      minor by agreement): move your `s2`/`openalex` blocks under
      `"providers": { ... }` — values unchanged.
- [x] **Frontend package nesting + full README coverage** *(v4.3.1 — prep
      for the "Frontend quality" backlog)* — `GraphCanvas` and
      `GraphControls` moved into nested sub-packages **`graph/canvas/`**
      and **`graph/controls/`** (Legend joined `controls/` — same
      single-parent DOM-chrome layer), each with its own README;
      `graph/README.md` refactored down to the package overview + the
      cross-cutting RFG identity contract, with the component/hook
      deep-dives relocated into `canvas/`, `controls/`, and `hooks/`
      READMEs. A full-frontend sweep against the hybrid structure rule
      found no other nesting warranted but four folders missing READMEs —
      `graph/hooks/`, `teacher/figures/`, `teacher/transcript/`, `ui/` —
      all written, so `src/README.md`'s "every folder has its own README"
      claim is now true. Zero behavior change (the production bundle hash
      is byte-identical). **New standing convention in `CLAUDE.md`**: every
      new package ships with a README; code changes refactor the affected
      READMEs in the same change. *(Patrick's ask, 2026-07-09.)*
- [x] **Frontend pre-commit (format + lint)** *(2026-07-09, no version
      bump — dev tooling, not the app)* — **prettier** (3.8.4, pinned exact)
      added as the formatter, configured to the existing house style
      (`semi: false`, single quotes, printWidth 100) so the one-time sweep
      stayed small (23 files, +166/−159, render-equivalent JSX whitespace
      reflows only); scoped to `src/**/*.{ts,tsx,css}` + `test/` +
      `vite.config.ts` — deliberately not the hand-formatted READMEs or the
      JSONC tsconfigs.
      Two **local pre-commit hooks** (prettier then oxlint, both running the
      frontend's own npm scripts) join the existing gate, so
      `uv run nox -s precommit` now enforces frontend hygiene the same way
      it does backend hygiene — prettier fixes in place like ruff `--fix`
      (verified with a negative test: a deliberately mangled file failed the
      run and came back formatted). New npm scripts `format` /
      `format:check`. *(From the `todos.md` inbox, 2026-07-07.)*
- [x] **Frontend tests — Vitest + React Testing Library** *(v4.4.0;
      completes the "Frontend quality" backlog section, promoted here)* —
      the frontend now has a real offline test surface: **Vitest 4** (+
      jsdom + RTL), configured in `vite.config.ts`'s `test` block, with the
      suite in **`frontend/test/`** mirroring `src/` the way the backend's
      `test/` mirrors `src/atlas/`. Seven files / **54 tests** cover the
      pure logic with real edge cases — `graph/model` helpers (incl. the
      `ID_RE` pasted-id fast path), `notation/splitMath` (math vs. currency
      vs. mid-stream unclosed delimiters) and `latexToUnicode`, the
      `<<FIG n>>` interleaver (streaming-tail holdback, invented slots,
      leftovers), `remarkCite` on hand-built mdast — plus a jsdom/RTL pair
      (`Legend`'s conditional agent entries, `useResizablePanel`'s
      seed/clamp/drag/persist). Node environment by default, per-file
      `@vitest-environment jsdom` opt-in, no test globals (everything
      imported from `vitest` explicitly). A new **`vitest` nox session**
      joins the default gate — `uv run nox` is now the whole-repo gate
      (backend 328 + frontend 54; skips cleanly without npm, the Trivy
      pattern) — and prettier's scope covers `test/`. Next natural target
      (per `frontend/test/README.md`): `useConversation` driven by scripted
      SSE events, the `fake_claude` idea client-side. *(From the `todos.md`
      inbox, 2026-07-07.)*

## Backlog — not yet shipped

### Teacher & agent reach

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
- [ ] **General non-arXiv full text** — S2's `openAccessPdf` + the existing
      pymupdf pipeline as a fallback reader for `read_paper` on journal
      papers (text only; figures stay ar5iv-quality-or-nothing).

- [ ] **Agent surfaces figures proactively (no explicit ask)** — today the
      agentic Q&A only calls `show_figure` when the question explicitly asks for
      a picture; you have to request an image every time to get one. It should
      **decide on its own** when a figure would answer the question better and
      pull one in unprompted — e.g. a question about a model's architecture
      should surface the architecture diagram without being told to. Likely a
      prompt nudge (make `show_figure` a default reflex when a read paper has a
      relevant figure, not a last resort), and bumps up against the broader
      **agent-reliability** item above — the model already skips `show_figure`
      even when asked, so "show more often, unprompted" needs the tool-call
      compliance to be solid first (stronger `AGENT_MODEL` / sub-agent
      decomposition). *(From the `todos.md` inbox, 2026-07-07.)*
- [ ] **GPU embedding on Windows without shared memory** — the local sentence-
      transformer embedder (`library/embeddings.py`, all-MiniLM / bge-small)
      runs on CPU. On Windows machines with a discrete GPU (no shared/unified
      memory), moving the model + inference to **CUDA** would speed up ingest
      embedding meaningfully. Detect an available device and use it when present,
      falling back to CPU cleanly; keep it optional/degrading like the rest of
      the library stack (`available()`). *(From the `todos.md` inbox,
      2026-07-07.)*
- [ ] **Figures from uploaded PDFs in answers** — extend the v1.20.0 figures
      feature to the user's **own library**: pull images out of an ingested PDF
      (via `pymupdf`, which we already use for text) and let the agent surface a
      relevant one when it cites a source passage — the library analogue of
      `show_figure`, which today only covers arXiv papers (ar5iv). Needs page →
      image extraction at ingest (or on demand), a way to reference an image from
      a retrieved passage, and a `show_source_figure`-style tool + `figure` event
      reusing the existing answer-figure rendering. *(From the `todos.md` inbox,
      2026-07-03.)*

### Citations & graph data

- [ ] **Budget-cap the Similar nodes with a trained model** — the *Similar*
      relation ships a flat `similar_limit` count, the same one-size problem the
      landmark budget solved for citations (v4.5.0). Give it its own budget
      model: cap how many SPECTER2 neighbors to show per seed, trained the same
      way as `cite_budget` (a new `ml_pipelines/<study>/` producing a loadable
      artifact the app calls at serve time, degrading gracefully). Decide the
      right label/signal for "how many similar papers are worth showing" (density
      of similarity scores? a drop-off / knee in the ranked similarity? seed
      features?) during the study. Mirrors the `cite_budget` / `latest_gap`
      pattern. *(From the `todos.md` inbox, 2026-07-10.)*
- [ ] **Even Latest-Publications spread via citation velocity** — the
      stratified/per-year band approach has been tried several times and the
      spread still isn't even. Revisit **citation velocity** as the ranking
      instead: balance citation count against recency, which are inversely
      proportional (newer papers haven't had time to accumulate citations), so
      neither extreme dominates the selection. The shelved WIP's
      **`_velocity` helper — `citation_count / (age + 1)`** (`stash@{0}`, see
      the mega-papers phase notes) is the starting formula; may need tuning so
      the balance point lands where the spread looks even. *(Patrick's
      brainstorm, 2026-07-10.)*
- [x] **Duplicate nodes for the same paper (cross-source identity)**
      *(v4.5.1)* — Patrick's browser observation: seeding on DQN showed two
      instances of "Continuous control with deep RL". Investigation found it
      was actually **three** (an OpenAlex `ARXIV:` citer + an OpenAlex
      `DOI:` citer from a duplicate work + an S2-paperId similar hit), and
      24/11/43/30 duplicate-title groups across the four cached graphs. Fix:
      **node identity resolves through the arXiv id** in
      `build.py::add_neighbor` — the one id both sources agree on — with
      `add_neighbor` returning the canonical id for edges, later sightings
      upgrading fields they know better (`_upgrade_node`: max
      `citation_count`, since S2's counts are far more complete; fill-if-None
      for summary/date fields), `add_edge` skipping self-loops + duplicate
      `(source, target, type)` triples, ranks staying compact, and `counts`
      becoming post-dedupe edge counts. The seed registers its own arXiv id,
      so a citer that IS the seed under another id merges instead of
      self-looping. Known residual (deliberate): a journal-DOI record vs.
      its preprint twin where neither carries the arXiv id can't merge —
      title matching was rejected as too risky (same-title distinct papers
      exist, e.g. Living Reviews editions). Two pinned tests. *(From the
      `todos.md` inbox, 2026-07-10.)*
- [x] **Verify slider reveal order is most-cited-first** *(2026-07-10 —
      verified correct, no fix needed)* — audited all four cached graph
      snapshots (DQN, Attention, QMIX, Hawking; up to 500 edges/relation):
      **references and Field Landmarks reveal perfectly most-cited-first**
      (zero rank inversions everywhere), **Latest Publications is perfectly
      date-ascending** (the v4.1.0 oldest-first reveal, zero inversions),
      and **Similar reveals by S2 similarity** — not citations — which is
      that relation's intended semantics (most-similar first); Patrick
      accepted this as correct. *(From the `todos.md` inbox, 2026-07-09.)*
- [ ] **Latest Publications is thin on arXiv-only seeds — OpenAlex data
      gaps, not S2 offset paging** *(investigated 2026-07-10; the original
      suspicion is settled, the underlying problem is real and still open)* —
      **Verified: latest DOES come from OpenAlex** (every latest node in all
      four cached graphs carries an OpenAlex id; the logs show zero S2
      fallback engagements). But the instinct that something was off was
      right: **latest is badly truncated for arXiv-only seeds** — DQN's
      stops at 2025-08 (nothing from the last ~11 months), QMIX shipped just
      11 latest nodes. Two verified causes: (1) **OpenAlex splits papers
      into duplicate works** and `resolve_work` picks one — for QMIX we
      resolved the 352-citation twin while a same-DOI sibling holds 479, so
      `cites:` queries see half the paper; (2) **OpenAlex's citation linkage
      lags hard for preprint-only works** — even both QMIX works combined
      show ~34 citers since 2025 where S2 knows thousands (well-linked
      records like Attention/Hawking span cleanly to the build date).
      Remedies to build: union the `cites:` filter across all works sharing
      the seed's DOI/arXiv id (`cites:W1|W2`), and/or a per-relation S2
      supplement when the latest pool comes back suspiciously thin (the
      fallback is currently all-or-nothing on seed resolution). *(From the
      `todos.md` inbox, 2026-07-09; findings 2026-07-10.)*
- [ ] **Prune ghost similar papers (no citations AND no publication
      history)** — Patrick doesn't want to see them on the graph: an S2
      recommendation with zero citations and no year/date is unverifiable
      noise. Filter them out of the similar relation at build time (keep the
      filter server-side so the slider's pool is honest). *(From the
      `todos.md` inbox, 2026-07-10.)*
- [ ] **Search nodes as a graph filter chip** — topic-search hits (the pink
      `search` relation from the researcher's `search_papers` tool) are
      currently **always shown** with no filter chip of their own (see the
      `enabled` set in `GraphExplorer.tsx`, seeded with `[...REL_TYPES,
      'search']`, and `GraphControls` renders chips only for `REL_TYPES`).
      Give them their own toggle alongside references / citations / similar so
      the user can hide/show them like any other relation. *(From the
      `todos.md` inbox, 2026-07-07.)*
- [ ] **Search cache refresh override** — seed-search results are served from
      the whole-result cache (v2.0.0) with no way to bypass a stale entry; add
      a refresh/override button to the search surface, mirroring the graph's
      per-seed **Refresh** button (v2.5.0) that busts the snapshot cache.
      *(From the `todos.md` inbox, 2026-07-08.)*

### UI & rendering polish

- [x] **Clickable reference numbers in agent answers** *(v3.8.0)* — inline `[n]`
      markers are now clickable chips that spotlight the paper they cite (the
      `highlightIds` glow); click the same marker again to clear it. Works on
      **both** surfaces: researcher answers (resolved frontend-side against the
      grounding list + idx-tagged discoveries) and **lecture beats** (resolved
      server-side by `prompts.refs_from_text`, emitted on the beat's new `refs`
      field — a lecture numbers the mode-filtered `_story_nodes` the frontend
      never sees). The resolved `[n]`→node-id map persists per message/beat, so
      it survives a saved-session reload. *(From the `todos.md` inbox, 2026-07-07.)*
- [x] **Adjustable side panels** *(v3.7.0)* — both docked panels (detail +
      assistant) are now user-resizable: a drag handle on each panel's inner
      edge (`ui/useResizablePanel.ts`), width clamped 280–680px and remembered
      across sessions in localStorage (`atlas.detailWidth` / `atlas.teacherWidth`).
      *(From the `todos.md` inbox, 2026-07-08.)*
- [x] **Q&A answers need full Markdown + LaTeX rendering** *(v3.8.0)* — agent
      prose now renders through **react-markdown** (`AnswerMarkdown.tsx`):
      remark-gfm (headers, **bold**, lists, tables) + remark-math + rehype-katex
      (the KaTeX the app already uses), with a small `remarkCite` plugin for the
      clickable `[n]` markers above. Reused for **both** researcher answers and
      lecture beats; `MathText` stays for the detail panel, search hits, and beat
      headings. The user's own question bubble stays plain (no Markdown
      surprises). *(From the `todos.md` inbox, 2026-07-08.)*
- [x] **Multi-number citation markers now highlight** *(v4.9.1)* — an agent
      answer that wrote a combined marker like `[14, 29]` used to be inert
      (clicking it highlighted nothing): the whole `[n]` pipeline matched single
      numbers only, so a combined marker never became a chip. Fixed **both**
      ways the ticket floated — the marker regex is now
      `\[(\d+(?:[\s,]+\d+)*)\]` (comma- and/or space-separated) in all three
      places that must agree (`remarkCite` render, `useConversation.resolveRefs`,
      backend `prompts.refs_from_text`), splitting a combined marker into **one
      clickable chip per index** (each resolving to its own paper); **and** the
      `numbered-papers.md` skill now tells agents to emit separate `[14][29]`
      markers, not combined, so the split rarely even fires. Verified with a new
      RTL test that renders the real `AnswerMarkdown` and clicks each chip.
      *(From the `todos.md` inbox, 2026-07-10.)*
- [x] **Lecture buttons: cached toggles, tidied grid, parallel loading**
      *(v4.9.0)* — the lecture-mode buttons were reworked end-to-end (shipping
      the "tidy the buttons" and "cache each lecture" asks together):
  - **Cached show/hide toggles** — each of the four modes caches its beats on
    first play (`store/transcript.ts`: `lectures` = mode → beats, plus
    `activeMode`); re-clicking the shown mode hides it (cache kept), clicking a
    played-but-hidden mode reloads instantly with no re-fetch. Save persists the
    whole per-mode cache (a restore brings every played lecture back, not just
    the visible one; a pre-caching save's flat `beats` folds into `history`).
  - **Everything streams in parallel** — the single "teaching" flag/shared abort
    controller became one controller per in-flight lecture (`Map<mode, ctrl>`)
    plus one for the chat, so a lecture keeps generating in the background when
    you deselect it, ask a question, or start another mode — nothing interrupts
    anything else. `beatAdded` carries its mode so a background stream fills the
    right slot; `onBeat` only drives the graph highlight for the shown mode.
  - **Tidied 2×2 grid** — even equal-height cells (long labels wrap cleanly), a
    **filled periwinkle** selected state, a small dot on a cached-but-hidden
    mode, and **hopping "loading" dots** (cascade animation, honors
    `prefers-reduced-motion`) on a streaming button.
  - **Soft periwinkle palette** — the panel's hard `#ffd166` yellow (buttons,
    active-beat/answer tints, trace chips) swapped for a soft periwinkle
    (`--lecture` / `--lecture-solid` in `teacher.css`), easier on the eyes and
    in the app's blue-accent family. *(Browser-caught + fixed: hover was washing
    out the filled `.active` fill on specificity — scoped hover off `.active`.)*
  - **Contextual Clear**, relocated to a **transcript toolbar** (top-right of
    the content zone, out of the lecture controls): a shown lecture → clear just
    that lecture (`lectureDropped`); no lecture shown → clear the Q&A chat
    (`chatCleared`) and mint a fresh session. The button relabels accordingly.
  - **"The landmark papers since"** — the evolution mode renamed from
    "Summarize the landmark papers since".
  - **Grounding-scope caption** — a quiet note under the grid tells the user a
    lecture covers exactly the papers currently shown on the graph (so filtering
    the graph scopes the lecture). Verified in the browser via Playwright on the
    cached DQN seed. *(Patrick's asks, browser-tested 2026-07-11.)*
- [ ] **Group graph nodes by relation type in the Force layout** — the force
      layout currently mingles every relation into one undifferentiated cloud;
      nodes should **cluster into visual groups by their relation to the seed**
      (references / Field Landmarks / Latest Publications / Similar) so the
      neighborhood reads at a glance. Likely a per-relation grouping force (a
      cluster centroid per relation, or a radial/sector layout keyed on
      `link.type`) in the force-graph config; Timeline already separates by date,
      so this is the Force-layout counterpart. *(From the `todos.md` inbox,
      2026-07-10.)*
- [x] **Drop the per-relation count sliders; filter by citation count instead**
      *(v4.7.0)* — the four per-node-type count sliders are gone; the **relation
      filter chips** (restyled back to the bubbly v2–v3 pills) are now the only
      node-*type* filter. In their place, a **dual-knob citation-count window
      slider** sits beneath the year slider: two thumbs bound a min…max citation
      window on a **log scale** (`model.ts` `citationThreshold`, `log1p`/`expm1`),
      bounded by the graph's *actual* min…max neighbor citation counts — like the
      year slider's real-range bounds — so neither knob idles. It's a pure
      *display* filter over the already citation-budgeted pool (`cite_budget`
      model), not a fetch control; hidden when the neighbors share one citation
      count (nothing to window). **Config cleanup, resolved: keep**
      `graph.cite_limit` / `adaptive_cite_limit`. The OnePager's "(slider max)"
      was a misread — they're the ceiling for the adaptive landmark-budget model
      (`services/graph/budget.py`, `build.py`), independent of the retired
      frontend sliders, so nothing was redundant. *(From the `todos.md` inbox,
      2026-07-10.)*
- [x] **Determinate "Building graph…" progress** *(v3.7.0)* — the build notice
      now shows a real filling bar + live stage label, not just a spinner. As
      predicted, this took a streaming build route: new SSE `GET
      /api/graph/stream` bridges `build_graph`'s five coarse stages (resolve →
      references → citations → similar → assemble) into `progress`/`done`/`error`
      frames via a worker thread + queue (the Sources-ingest pattern), and
      `loadGraph` consumes them into a `buildProgress` store field. A cache hit
      streams no frames, so it stays instant. Covers **both** load paths — a
      fresh build from an empty workspace and a re-seed over an existing graph
      (a restored save rebuilds locally, so it needs no bar). The blocking
      `GET /api/graph` stays for compatibility. *(From the `todos.md` inbox,
      2026-07-08.)*
- [ ] **Remove the "Powered by Claude Code" attribution** from the UI. *(From the
      `todos.md` inbox, 2026-07-08.)*


### Enhancements & tech debt

- [ ] **Rename `digest.db` → `cache.db`** — the ephemeral graph-snapshot store
      is still named `digest.db`, a leftover from the retired daily-digest era;
      it's really the 1-day graph/artifact **cache** now. Rename the file (and
      the `storage.data_dir`-relative path + any `config`/docstring references,
      e.g. `storage/sessions.py`'s note contrasting it with `sessions.db`) so the
      name matches what it holds. A cosmetic rename — old `digest.db` files can be
      left to age out or deleted, since it's a regenerable cache. *(From the
      `todos.md` inbox, 2026-07-11.)*
- [x] **`atlas serve` takes `--port` and `--host`** *(v4.10.0)* — the CLI serve
      command gained `--host`/`--port` options that override
      `config.server.host`/`port` per invocation (a second instance, or when 5000
      is busy, no longer needs a config edit). Both default to `None` and fall
      back to config, so existing behavior is unchanged; `app.main(host, port)`
      applies the fallback. Verified live (`serve --port 5055` binds there, 5000
      untouched). *(From the `todos.md` inbox, 2026-07-11.)*
- [x] **Enforce docstrings in the gate, both languages** *(2026-07-10, no
      version bump — quality tooling; the whole sweep is runtime-invisible,
      bundle hash unchanged)* —
      - **Backend:** ruff's pydocstyle **`D` rules on (Google convention)**
        — a missing module/class/function docstring now fails the gate
        (D205 deliberately ignored: the house style opens with flowing
        multi-sentence paragraphs). **pydoclint** evaluated and adopted for
        *completeness*: Args must match the signature, Returns must exist
        where a value comes back (new pre-commit hook + `[tool.pydoclint]`;
        type-matching and raises-checks off — types live in annotations,
        and the house style rightly documents *propagated* exceptions,
        which pydoclint's lexical raises-check would outlaw). Sweep fixed
        ~45 gaps: 20 auto-fixed quote placements, 7 undocumented params
        (incl. every researcher tool's `ctx` and ingest's `on_progress` —
        the exact complaint), 5 tool Returns sections, missing
        `__init__`/method docstrings, `_figure_pool`/`resolvable_id` Args.
      - **Frontend:** oxlint's **jsdoc plugin on** (`require-param` with
        `checkDestructured: false` — component props stay documented on
        their Props interfaces, not duplicated as tags — `require-returns`,
        description/name/tag rules; off for `test/**`, mirroring the
        backend's per-file-ignores). Fixed all 96 completeness findings and
        swept JSDoc onto the 17 still-undocumented functions (components,
        selectors, reducers, hooks), so every function is documented with
        backend-style structure. **Caveat:** oxlint has no `require-jsdoc`,
        so *presence* on brand-new functions stays a convention (CLAUDE.md);
        completeness of anything documented is machine-enforced.
      *(From the `todos.md` inbox, 2026-07-09.)*
- [ ] **Move `ml_pipelines/` into `src` and split `models/` per model** — the ML
      training pipelines live at the repo root today, outside the src-layout
      package; move `ml_pipelines/` under `src/atlas/` (updating the artifact
      load paths in `services/graph/budget.py` + `bands.py`). And **break the
      shared `ml_pipelines/models/` package** — currently a single home for both
      `.joblib` artifacts + metadata + one README — **into per-model
      sub-packages named for their model**, folding each artifact into its
      existing pipeline package (`cite_budget/`, `latest_gap/`) so a model's
      training code, corpus, artifact, and README live together. Each keeps its
      own README (both already have one); **delete the `models/` README** as the
      package dissolves. Matches the per-package-README rule. *(From the
      `todos.md` inbox, 2026-07-10.)*
- [ ] **Drop the retired per-relation count caps from config** — remove
      `graph.ref_limit`, `graph.cite_limit`, `graph.adaptive_cite_limit`,
      `graph.latest_limit`, and `graph.similar_limit` from `config.json` /
      `config.example.json` and the Pydantic `graph` config. Resolved plan (per
      Patrick, 2026-07-10):
  - **`cite_limit` + `adaptive_cite_limit`** → gone: the **landmark-budget model
    always determines the cite limit** — no toggle, no config ceiling. The budget
    model owns its own upper bound (`services/graph/budget.py`) rather than
    clamping to a config `cite_limit`.
  - **`ref_limit`** → gone: **show all references** (no cap).
  - **`latest_limit`** → gone: Latest Publications is already **banded by year**
    (`latest_band_years` × `latest_per_year`), so the flat cap is redundant.
  - **`similar_limit`** → **staged behind** the *Budget-cap the Similar nodes with
    a trained model* ticket (under Citations & graph data): that ticket replaces
    the flat `similar_limit` with a trained per-seed budget, so remove the config
    key as part of / after it, not before. *(From the `todos.md` inbox,
    2026-07-10.)*
- [ ] **Dynamic OpenAlex latest-window sizing** — the "Latest Publications"
      per-year bands + newest window (`config.graph.latest_band_years` /
      `latest_per_year`) are a **fixed** span today. But how far back the recent
      band needs to reach depends on the seed: a heavily-cited or older seed's
      landmarks peter out sooner, so the latest window should extend nearer/wider
      to meet them, while a lightly-cited seed needs a shorter one. Size the
      window (and maybe the per-year cap) **dynamically** from the seed's
      publication year + total citation count, so the landmark↔latest handoff
      lands in the right place for every seed instead of a one-size default.
      *(From the v4.0.0 hybrid build sessions, 2026-07-09.)*
- [ ] **Swap the hand-rolled `urllib` clients for `httpx`** — S2, arXiv
      (`client`/`fulltext`/`figures`), and OpenAlex all hand-roll stdlib
      `urllib` (manual `Request`/`urlencode`/`HTTPError` plumbing); only HF uses
      a library, and that's the `huggingface_hub` *SDK*, not a generic HTTP lib.
      The original "no third-party HTTP dep, tiny deploy" rationale (baked into
      the S2 client docstring) is now **moot**: `httpx` (0.28.1) is already in
      the tree transitively via anthropic/pydantic-ai, so adopting it for our
      clients adds **zero new install** — and it's more readable
      (`client.get(url, params=…).json()`, `raise_for_status()`,
      `resp.status_code`), gives connection pooling, and makes the three REST
      clients consistent with each other and with the httpx the app already
      runs on. **Keep** our own throttle-lock + backoff + error-taxonomy
      wrappers (the load-bearing logic a library doesn't replace — so the win is
      readability/consistency, not less retry code). **Don't** adopt provider
      SDKs (`pyalex`, `semanticscholar`): they'd hide the throttle/cache/paging
      control we deliberately own. Before building, pin to the real `httpx` and
      check what's pulling the odd `httpx2` (2.5.0) in the lockfile. *(From a
      session design question, 2026-07-09; staged behind the OpenAlex hybrid
      ship.)*
- [x] **~~Iterative (multi-round) landmark mining to beat recency bias~~ —
      RETIRED** *(v4.0.0)* — this was an idea to loop S2 reference-list mining to
      fill the sparse early-landmark band. The **OpenAlex hybrid** (shipped)
      recovers that band directly with a sorted `cites:` query — no mining, no
      verification, no loop — and the whole S2 mining apparatus it built on was
      deleted. Kept only as a tombstone; the live fallback path is plain deep
      paging.
- [ ] **Tune the agents' citation-count weighting via a skill** — today a strong
      preference for highly-cited papers is *implicit*: the graph hands both
      agents a pool already ranked by citations (references/citations most-cited
      first in `build.py`; `expand_node` pulls landmark/most-cited neighbors; the
      lecturer's figure pool is `sorted(by citation_count)[:4]`), while the
      prompts only *show* the count (`node_lines`) and `teaching-voice` pushes
      "why it matters" over popularity — no explicit rule either way. Add an
      optional skill that makes the weighting **explicit and adjustable** (favor
      or deliberately de-emphasize citation count in what the agents select and
      narrate), so we can experiment with surfacing under-cited but important
      work. Low-effort: a skill-file addition wired into the researcher/lecturer
      `SKILLS` tuples. *(From a session side-question, 2026-07-08.)*
- [ ] **Cached papers don't match the query agent's expanded query** — papers
      served from the local sources cache don't seem to line up with the query
      the query-analyst expanded to, so the researcher may ground on the wrong
      cached hits. Investigate the retrieval/cache-key path vs. the expanded
      query (query_analyst → researcher/retrieval). *(From the `todos.md` inbox,
      2026-07-08.)*
- [ ] **Graph build should survive S2 being down without trapping the user** —
      if Semantic Scholar is unavailable mid-build, the error message should be
      **dismissible** and the graph currently on screen restored (it must not stay
      greyed out). Frontend error handling around `fetchGraph`/`GraphExplorer`.
      *(From the `todos.md` inbox, 2026-07-08.)*


### Larger phases

- [ ] **Phase 5 — Concept mindmap** — Claude concept-map JSON, "bridge two
      topics," `/api/mindmap`.
- [ ] **Phase 6 — Audio lecture** — Podcastfy integration, Edge TTS default,
      ElevenLabs optional, `/api/lecture/audio`.
- [ ] **Phase 7 — Polished media (optional)** — `autocontent.py` behind
      `AUTOCONTENT_API_KEY`; "Generate visuals" button.


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

## Bugs — notable, found & fixed

A running log of bugs worth remembering — the ones with a non-obvious root
cause, a surprising reproduction, or a lesson that outlives the fix. Everything
here is already **fixed and shipped**; open work lives in the Roadmap/Backlog
above and the `todos.md` inbox. The point is institutional memory: when a
symptom recurs or someone touches the same code, the story is one grep away
instead of buried in a diff.

Keep it newest-first. One entry per bug, with **Symptom** (what was visibly
wrong), **Root cause** (the actual mechanism, not the surface), **Fix** (what
changed, and where), and **Lesson / guard** (what keeps it from coming back — a
test, an invariant). Small, obvious bugs don't need an entry — the commit
message is enough. This section is for the ones you'd want to re-read a year
later.

### The same paper as two (actually three) nodes — cross-source identity in the hybrid graph

*Found & fixed in v4.5.1 (2026-07-10).*

- **Symptom.** Seeding on DQN showed "Continuous control with deep reinforcement
  learning" as **two** node instances, each with a partial view of the paper
  (different rels, wildly different citation counts). An audit of the four
  cached graphs found 24/11/43/30 duplicate-title groups — the graph had been
  quietly double-counting papers since the v4.0.0 hybrid.
- **Root cause.** The node table was keyed by raw id, but the hybrid ships
  **two id schemes**: S2 relations (references, similar) carry bare paperIds
  while OpenAlex citers carry `DOI:`/`ARXIV:`/`W…` ids. The "duplicate" was
  actually **three** sightings — an OpenAlex `ARXIV:` citer, an OpenAlex `DOI:`
  citer from a *duplicate OpenAlex work* (verified live: two QMIX works share
  one DOI), and an S2-paperId similar hit — each minting its own node.
- **Fix.** `build.py::add_neighbor` resolves identity through the **arXiv id**,
  the one id both sources agree on: first sighting wins the node slot, later
  sightings append their rels and upgrade fields they know better
  (`_upgrade_node`: max `citation_count` — S2's counts are far more complete —
  fill-if-None for summary/date fields). `add_neighbor` returns the canonical
  id and the edge loops use it; `add_edge` skips self-loops and duplicate
  `(source, target, type)` triples with ranks staying compact; `counts` are
  post-dedupe. The seed registers its own arXiv id, so a citer that IS the seed
  under another id merges instead of self-looping. Two pinned tests.
- **Lesson / guard.** A graph fed by two sources needs an explicit **identity
  key**, not "whatever id arrived". The known residual is deliberate: a
  journal-DOI record vs. its preprint twin where neither side carries the arXiv
  id can't merge — title matching was rejected as riskier than the rare leftover
  duplicate (same-title distinct papers exist, e.g. Living Reviews editions).

### OpenAlex misdates "Attention Is All You Need" to 2025 — nearly broke the cite-budget model

*Found & handled during the v4.5.0 adaptive-budget build (2026-07-10).*

- **Symptom.** While fitting the landmark-budget model (`ml_pipelines/cite_budget`),
  a **sqrt-age** variant that scored *better* on cross-validation (CV R² 0.73 vs
  0.68) predicted a budget of **~2 landmarks** for "Attention Is All You Need" —
  absurd for one of the most-cited ML papers.
- **Root cause.** OpenAlex's canonical record for that paper reports
  `publication_year: 2025` (it resolves to a low-citation duplicate work,
  `W2626778328`, not the 2017 original), so the model saw **age ≈ 1**. The
  sqrt-age transform is steep near zero, so a wrong age of 1 collapsed the
  prediction; plain-age is linear and far more forgiving there (~30, the right
  ballpark).
- **Fix.** Chose the **plain-age linear model** over the higher-CV sqrt variant
  precisely *because* it survives this dating noise (documented in
  `ml_pipelines/cite_budget/train.py` and the notebook). `compute_features` also
  floors age at 0 so a future-dated seed can't go negative. A test pins the
  misdated anchor (`year=2025 → 30`) so a future "improvement" that reintroduces
  the fragility fails loudly.
- **Lesson / guard.** OpenAlex publication years are **not trustworthy** for
  individual works — anything age-based (this model, and the queued
  landmark→latest date-distribution work) must degrade gracefully on a wildly
  wrong year, and CV score alone can hide a catastrophic failure on a single
  important point. Always eyeball the anchors, not just the aggregate metric.

### OpenAlex's coarse dates emptied the "Latest Publications" relation

*Found & fixed during the v4.0.0 OpenAlex hybrid build (2026-07-09).*

- **Symptom.** For the DQN seed, the graph showed **1** "Latest Publications"
  node — obviously wrong for a paper with hundreds of recent citers.
- **Root cause.** The latest relation used a rolling 12-month **date** window
  (`from_publication_date:<today − 12mo>`), ported from the S2 path. But OpenAlex
  dating is **coarse**: a large fraction of works carry a *year-only*
  `publication_date` that OpenAlex defaults to `<year>-01-01`. So a paper
  "published in 2025" is stamped `2025-01-01` and falls *outside* a window that
  starts mid-2025 — the filter silently excluded almost every recent-year citer.
  Confirmed live: DQN had **1** citer via `from_publication_date:2025-07-09`
  but **30** in `publication_year:2025` (6 of them dated exactly `2025-01-01`).
- **Fix.** Split landmark/latest by **publication year**, not an exact date:
  `latest` filters from `<first latest year>-01-01`, robust to the Jan-1 default
  (`integrations/openalex/traversal.py`, `citation_relations`). DQN latest: 1 → 30.
- **Lesson / guard.** Don't assume cross-source date precision. OpenAlex trades
  exact dates for coverage; any *date*-range filter against it must be
  year-granular (or tolerate `-01-01`) or it quietly drops year-only records.
  Pinned by `test_latest_uses_year_window_not_exact_date`.

### Tripled MathML soup in ar5iv figure captions

*Found & fixed v3.2.0 (2026-07-08), while shipping "Proper subscripts & math
notation".*

- **Symptom.** Figure captions in the detail panel and in the teacher's
  answers rendered as garbled, tripled math — e.g. the Double Q-Learning paper
  (arXiv 1509.06461) showed
  `…the action values are Q(s,a)=V*(s)+eaQsasubscriptVssubscriptitalic-ϵaQ(s,a)=V_{*}(s)+\epsilon_{a} and the errors…`.
  The new frontend KaTeX renderer couldn't help — the caption *string itself*
  was already corrupt, and the LaTeX in it wasn't even `$`-delimited.
- **Root cause.** ar5iv renders each formula as a `<math>` element whose
  children are **three redundant text renderings** of the same formula:
  presentation MathML (`<mi>`, `<msub>`…), a content-MathML / semantic
  annotation (the source of the literal words `subscript`, `superscript`,
  `italic-ϵ`), and a LaTeX annotation. `_FigureParser` in
  `src/atlas/integrations/arxiv/figures.py` stripped tags and accumulated **all
  of it**, concatenating the three into soup. The clean LaTeX was sitting
  unused in each element's `alttext` attribute the whole time.
- **Fix.** `_FigureParser` now tracks `<math>` nesting: on entering the
  outermost `<math>` inside a caption it emits the element's `alttext` wrapped
  in `$…$`, and suppresses the subtree's own text nodes. Captions come out as
  clean, KaTeX-ready `$V_{*}(s)+\epsilon_{a}$`. Covers every figure surface at
  once (detail panel, teacher `FigCard`, lightbox) because they all fetch
  through `get_figures`.
- **Lesson / guard.** When scraping rendered LaTeX (ar5iv/MathJax/KaTeX
  output), prefer the source-carrying attribute (`alttext`, `data-tex`,
  `<annotation encoding="application/x-tex">`) over the visual subtree — the
  subtree is *display* markup, often duplicated for accessibility, and
  text-stripping it is lossy. Two regression tests pin this
  (`test_get_figures_math_becomes_delimited_latex_not_tripled_mathml`,
  `…math_without_alttext_is_dropped_not_garbled`). Note the 30-day figure cache:
  a parser fix doesn't reach already-cached captions until they re-fetch —
  clear `figures:*` from the `cache` table to re-test immediately.

---

## Open questions & costs

- **Daily digest mode?** — Decide whether to keep any date-range "what's new
  today" view, or go fully graph-first. Leaning fully graph-first for v1.0.
- **Semantic Scholar rate limits** — free key ~1 req/sec; need polite batching +
  caching. Key application submitted 2026-07-03 (S2 requires an academic /
  corporate email — used the old academic address, approval pending). Keyless
  429s are painful enough that **OpenAlex** was under consideration as a fallback
  backbone — now **decided**: the 2026-07-09 spike landed on a hybrid (OpenAlex
  for citation/landmark traversal, S2 for enrichment; see the Next-up backlog
  section). Cache-first seed search (Phase 2.4) softens browsing in the meantime.
- **S2 coverage gaps** — arXiv CS/ML coverage is high but not total; some papers
  may have sparse citation edges. Addressed by the OpenAlex hybrid (Next up).
- **AutoContent API** — ~€24/mo (1,000 credits: infographic 10, slide deck 30,
  video 50). Trial the cheap tier and judge quality by eye before committing.
- **ElevenLabs** — optional premium TTS; free tier ~10k credits/mo.
- **Paper figures for slides** (later phase) — evaluate ar5iv HTML vs. arXiv
  source tarball vs. `pdffigures2`/DeepFigures for pulling real diagrams; decide
  how to caption/attribute them. Deferred until the visuals/slides phase.
