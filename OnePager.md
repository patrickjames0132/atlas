# arXiv Atlas — One-Pager

> **Status:** v1.2 · living document · AI teacher shipped v1.1.0; sidebar figures
> + PDF link + dual-thumb year slider shipped v1.2.0
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

- [x] **Phase 0 — One-pager** (this file)
- [x] **Phase 1 — Backend pivot to Semantic Scholar** *(v1.0.0)* —
      `semantic_scholar.py` client (batch hydration to dodge the single-GET
      throttle, 429 backoff, optional `S2_API_KEY`), `graph.py` neighborhood
      builder, thin `cache.py` (graph snapshots), new `/api/graph` & `/api/paper`
      routes. Seed accepts an arXiv id **or** a raw S2 paperId. *(The deeper
      teardown of the legacy digest backend — old routes, `papers`/FTS/vec/pulls
      tables — is deferred; those modules still power the arXiv seed search and do
      no harm.)*
- [x] **Phase 2 — Graph explorer frontend** *(v1.0.0)* — force-directed canvas
      (`react-force-graph-2d`), seed via arXiv search, nodes colored by relation
      / sized by citations / edges typed & directed, detail panel with `tldr`.
      **Declutter controls:** relation filters (refs/citations/similar) with
      counts, a dual-handle **year range** slider, **drag-to-pin** (+ release
      all), **focus-on-hover** dimming, and a papers-shown readout. **Visual
      traversal:** double-click (or "Explore from here") re-seeds the graph on
      any node — journal papers included.
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
      full-text reading or graph-jumping yet (that's 3b).*
- [ ] **Phase 3b — Agentic teacher** — a tool-use loop so the teacher can
      **read papers' full text** (`read_paper`, via ar5iv/arXiv) and **traverse
      to off-screen papers** (`expand_node`) on demand, under hard guardrails: a
      **hop budget**, a **visited-set** (kills reference cycles), a total-step cap,
      and size-capped tool results. This is what makes Q&A actually *source the
      papers* rather than reason over titles + the seed's summary.
- [ ] **Phase 3.5 — Timeline layout** — a **Force ↔ Timeline** toggle. Timeline
      places nodes on an exact **year axis** (x) with the force sim resolving the
      y-axis into citation "threads" flowing through time — so the chronological
      lecture sweeps left→right as nodes light up. (Force layout stays the
      default; a relation-band variant is a possible later sub-toggle.)
- [x] **Sidebar enrichment** *(v1.2.0)* — under the detail panel's TL;DR, the
      paper's **own figures with their captions** (`figures.py` extracts them from
      **ar5iv** HTML, cached 30 days; images streamed through a same-origin
      `/api/figure_proxy` locked to the ar5iv host — no hotlink reliance, no open
      proxy; tables skipped; graceful fallback where ar5iv has no render), plus a
      **direct PDF link** beside the arXiv-abstract link. Shipped alongside a UI
      polish: the year filter is now a single **dual-thumb range slider** (two
      overlaid inputs on one track + fill) instead of two stacked sliders.
- [ ] **Phase 4 — Concept mindmap** — Claude concept-map JSON, "bridge two
      topics," `/api/mindmap`.
- [ ] **Phase 5 — Audio lecture** — Podcastfy integration, Edge TTS default,
      ElevenLabs optional, `/api/lecture/audio`.
- [ ] **Phase 6 — Polished media (optional)** — `autocontent.py` behind
      `AUTOCONTENT_API_KEY`; "Generate visuals" button.

Each phase is independently shippable and gets its own version bump
(test-in-browser → bump `pyproject.toml` + `uv.lock` → annotated tag → push).

---

## Deliberately dropped in v1.0

The digest era's local-first machinery is retired in favor of dynamic queries:

- Local **paper corpus** (`papers` table) — no more storing paper rows.
- **FTS5** full-text index (`papers_fts`) and **sqlite-vec** vector index
  (`papers_vec`) — search/similarity now come from Semantic Scholar.
- The **`pulls` ledger** and category-aware smart-pull — no date-range fetching.
- The **date-range digest table**, pagination, and the **Download modal**.

*(Open question: keep a lightweight "daily digest" mode anywhere, or fully commit
to the graph-first experience? See below.)*

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
  caching. Request a higher research limit if exploration feels throttled.
- **S2 coverage gaps** — arXiv CS/ML coverage is high but not total; some papers
  may have sparse citation edges. Consider OpenAlex as a later fallback.
- **AutoContent API** — ~€24/mo (1,000 credits: infographic 10, slide deck 30,
  video 50). Trial the cheap tier and judge quality by eye before committing.
- **ElevenLabs** — optional premium TTS; free tier ~10k credits/mo.
- **Paper figures for slides** (later phase) — evaluate ar5iv HTML vs. arXiv
  source tarball vs. `pdffigures2`/DeepFigures for pulling real diagrams; decide
  how to caption/attribute them. Deferred until the visuals/slides phase.
