# Atlas — shipped history

> The complete record of what has shipped, split out of
> [OnePager.md](../OnePager.md) on 2026-07-16 so the one-pager stays a working
> document. Grouped by theme; each item keeps its full story and version tag —
> **the tags carry the true chronology, the grouping does not.** When a Backlog
> item in the OnePager ships, its entry moves here (into the matching theme
> section) as part of the ship's doc step. Notable bugs live in
> [bugs.md](bugs.md).

## Roadmap — shipped

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

- [x] **General non-arXiv full text — and figures** *(v5.27.0)* — papers
      without an ar5iv render (journal papers, failed LaTeX conversions) now
      get **full text and figures mined from their open-access PDF**. The
      ticket's original scope was "S2's `openAccessPdf` + the existing pymupdf
      pipeline as a fallback reader for `read_paper` (text only; figures stay
      ar5iv-quality-or-nothing)" — it shipped considerably wider on Patrick's
      call: **both providers** resolve the OA URL (S2 `openAccessPdf` — added
      to `DETAIL_FIELDS`; OpenAlex location `pdf_url`s, which in practice know
      OA copies S2's records miss — both surfaced as the node shape's new
      `oa_pdf` field), and a caption-anchored extractor
      (**`services/pdf`**, new package) mines **figures, tables, AND algorithm
      boxes** from the PDF for the detail panel's figure strip, the
      researcher's `show_figure`, and a real **PDF ↗ link for journal papers**
      in the panel actions. Extraction is caption-first (spiked on JMLR-LDA /
      Attention / PPO: 33 of 35 real floats with correct captions): `Figure N:`
      regions grow from image rects + vector-drawing clusters with
      subfigure/film-strip chaining, `Table N:` via `find_tables` → same-width
      booktabs **rule spans** → widened drawing skeletons, `Algorithm N`
      between its bounding rules (which doubles as the in-prose-mention
      filter; the `[:.]` in the caption regex kills "Figure 2 provides…"
      false positives). Mined floats are served as on-demand page-region
      renders (`/api/pdf_figure/<token>/<n>`, opaque server-minted tokens — no
      open proxy) with nothing pixel-cached server-side; the PDF itself is the
      cache (`data/oa_pdfs/`, LRU-capped) with text + figure manifest memoized
      in SQLite — design rationale written up in **`docs/pdf-mining.md`**.
      Known limitation: floats made purely of text (no image/drawing/rule
      anywhere, e.g. blei03a's Figure 6) have no geometric anchor and are
      skipped. New `config.pdf` section (size cap, timeout, cache size, float
      cap, render dpi); verified live end-to-end on the PLOS "Why Most
      Published Research Findings Are False" PDF via OpenAlex resolution.
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
      LaTeX instead — see [Bugs](bugs.md). Deferred to a later ticket:
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
- [x] **Phase 3c — Agentic reach beyond the graph** — the Q&A agent escapes the
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
    3c.2. **OpenAlex** keyless traversal fallback was later
    resolved by the v5.0.0 provider split — not built; a manual `S2_API_KEY` is the
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
      **Removed in v5.3.1** (see "UI & rendering polish").

- [x] **Feed already-played lectures into the researcher's context** *(v4.12.0)* —
      the Q&A researcher now **draws on lectures already played this session**
      instead of re-deriving the same ground (cheaper — fewer tool calls/tokens —
      and consistent with what the lecture said). The frontend packs the
      transcript cache's lectures (trimmed to each beat's heading + text, titled
      via the shared `LECTURE_TITLES`) into `streamAsk`'s new `lectures` field;
      the route parses them defensively into typed `PlayedLecture` models
      (`agents/models.py`), threads them through `orchestrator.run` →
      `researcher.answer`, and `_prompt` folds them in under a "build on these,
      don't repeat them" header, **budgeted** by `_LECTURES_MAX_CHARS` (6000) so a
      full set of four can't blow the prompt. A **🎓 scope picker** — the sources'
      `ScopePicker`, generalized to serve both scopes via a `labels` config —
      filters which played lectures are fed (tracked by exclusion, so a
      newly-played lecture is included by default), with a one-line note above the
      ask bar showing how many are in play. *(From the `todos.md` inbox,
      2026-07-11; browser-tested.)*

### Bring-your-own sources

- [x] **Phase 3d — Bring your own sources** — pull the user's own material into
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
    - figure/image handling — **OCR for scanned PDFs** — still open; moved to
      the Backlog in [OnePager.md](../OnePager.md).
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
- [x] **GPU embedding on Windows without shared memory** *(v5.8.0)* — the local
      embedder ran on CPU; on a Windows box with a discrete GPU (dedicated VRAM,
      no shared/unified memory) CUDA should make ingest much faster. It did:
      **~19×**, 80 → 1497 chunks/s on an RTX 3070 Ti (2000×900-char chunks,
      25.1s → 1.34s); a real 40-page PDF ingests in 0.33s.

      The ticket assumed the fix was device-detection code. It wasn't — that was
      the **wheel**. sentence-transformers *already* auto-selects CUDA; PyPI's
      Windows torch is simply a CPU-only build, so there was no CUDA runtime to
      find. `pyproject.toml` now declares torch directly (uv sources only apply
      to direct deps) and routes it to PyTorch's `cu130` index behind a
      `sys_platform == 'win32'` marker, keeping the 1.8GB wheel off macOS/Linux,
      where this repo is also worked on. `explicit = true` stops that index
      shadowing anything but torch. Detection code alone would have shipped a
      no-op that *looked* like a feature.

      What the code adds is control and visibility, not detection:
      `config.sources.embedding.device` (default `auto`) resolves to `None` and
      lets sentence-transformers choose — it already handles cuda/mps/xpu and
      stays right as torch grows backends, so a hand-rolled
      `torch.cuda.is_available()` ladder would be strictly worse. An explicit
      device overrides; one that won't load falls back to CPU with a logged
      warning (slow beats unavailable), verified against the real library with a
      bogus `cuda:7`. The load logs the device it landed on. Also folded in the
      sentence-transformers 5.x `get_sentence_embedding_dimension` →
      `get_embedding_dimension` rename (the old name emitted a `FutureWarning`
      and will eventually go), raising the nominal `>=3.0` floor to the `>=5.6`
      we actually lock. *(Shipped 2026-07-16; browser-tested on a real PDF
      upload. From the `todos.md` inbox, 2026-07-07.)*

### Citation graph — landmark/latest & mega-papers

- [x] **Corpus ingest degrades ~3x across a release — the partitioned write
      re-examines what's already on disk** *(v5.13.1 — patch; the ticket's
      hypothesis **refuted**, the real cause found and fixed)* — v5.6.0 fixed
      the *file explosion*, but per-shard cost still climbed across the
      2026-07-07 ingest: 26.5 s/shard for the first ten, 76.0 for the last
      (2.9x), ~5.7h actual against the ~2.2h a single-shard benchmark
      predicted. The suspected mechanism — `OVERWRITE_OR_IGNORE` +
      `FILENAME_PATTERN '<stem>_{i}'` re-scanning the ~400k accumulated files
      to resolve `{i}`, with DuckDB's newer `APPEND` mode as the fix — was
      **benchmarked and refuted**: writing into the *real* end-of-release
      399,360-file tree costs the same as into an empty directory, in both
      modes. What the marker-mtime forensics + five benchmarks actually found:
      (1) the "step" in the curve sits exactly at the export-batch boundary
      because batch-2 shards carry **39% more edge rows** (83.1 vs 59.7 MB
      Parquet out) — data mix, not degradation; (2) the remaining climb is the
      partitioned write slowing down **per process** — reproduced 3.04x in 8
      minutes with output *deleted* every iteration, surviving a DuckDB
      reconnect, indifferent to tree state, thermal (perf counters flat) and
      Defender (0 CPU), sparing single-file COPYs of the identical
      sorted+zstd payload, and resetting to cold speed with every fresh
      process — allocator/heap wear from the 1024 per-partition writers.
      **Shipped:** the citations shard loop routes through a single-worker
      `ProcessPoolExecutor` recycled every `_SHARDS_PER_WORKER = 16` shards
      (markers still written by the parent, after the rows are on disk); runs
      with no more pending shards than one quota stay in-process, keeping
      tests and resume-tails spawn-free. A/B through the real `ingest_release`:
      in-process climbs 2.42 → 4.70 s over 20 synthetic shards, recycled saws
      back to 2.48 s at shard 17 — sub-linear scaling restored, worth roughly
      5.7h → ~3h on a full release. Full story in **Bugs** (with the "benchmark
      against a populated tree" lesson upgraded: the tree was never the
      variable — the *process age* was). Suite 510 → 511. *(Filed 2026-07-15
      while ingesting the first full release; shipped 2026-07-17.)*
- [x] **Every landmark budget is computed now — the model retires from serving,
      and a fully-reachable live pool gets the corpus shape** *(v5.13.0)* — born
      from Patrick re-deriving the budget design in conversation (2026-07-17)
      and landing on the destabilizing question: *"do we really need the budget
      model at all?"* The answer was no — but not for his proposed reason, and
      the correct reason was better. Pulling OpenAlex's whole pool would cost
      ~150 requests (~30k citers for DQN — correcting both his "13k", which is
      S2's count, and the docstrings' "130k", a typo). What kills the model is
      that **the STOP rule is prefix-local**: it never reads past the first year
      to overflow, and OpenAlex serves the ranking sorted, so everything the
      rule will ever read sits in the first 200-row page — the same single
      request the *predicted* path already made. `predict-vs-compute.md`'s
      "predict" regime rested on an unexamined premise ("computing needs the
      whole pool"), and checking what the rule actually *reads* emptied it.
      **What shipped:**
      **(1) OpenAlex computes** (`openalex._budgeted_landmarks`): probe one
      ranked page, run `budget.computed_cite_limit` over its years, trim to the
      count; a seed whose top-200 never overflows pays one ceiling-sized refetch
      and re-measures. Deletes the model's ~21-citer per-seed error and — a
      bonus — restores the `PER_YEAR_CAP` invariant on this path, which a
      size-only prediction never could enforce (a blockbuster year could exceed
      12; a STOP prefix cannot).
      **(2) A complete live S2 pool ships the corpus shape** — Patrick's other
      catch: the live path treated *every* pool as a recency sliver, but a seed
      whose citer list ends before the ~9k offset ceiling (most seeds) is a
      *whole history*, and the sliver arguments evaporate. `_fetch_reachable_pool`
      now reports completeness (S2's own `next` flag — a page can run short
      mid-list when S2 fails to resolve papers, so page length can't be the
      signal; a full raw page is belt-and-suspenders continuation), and a
      complete pool gets STOP-prefix landmarks + tau-banded per-year Latest
      (`_complete_pool_relations`, mirroring the corpus source
      decision-for-decision). STOP alone would have recreated the 18-month hole
      against the rolling window — the tau bands are what close it. Truncated
      pools keep SKIP + the window; the offset-ceiling wall is now a per-seed
      caveat, not a path-wide one.
      **(3) The model is retired from serving, not deleted**:
      `budget.adaptive_cite_limit` and `build._adaptive_cite_limit` are gone;
      `predicted_budget`/`load_model` and the artifact remain as the
      `latest_gap` collector's dependency and the label's derivation record (a
      follow-up ticket weighs folding them into `ml_pipelines`). The STOP rule's
      "only ever a training label" story — already stale since v5.11.0 —
      is rewritten everywhere: it is the serving rule for every whole-history
      pool, and the label second. `predict-vs-compute.md` gains an epilogue
      ending: *predict only what you can't observe — and check "can't observe"
      against what the rule reads, not the size of the pool it's defined over.*
      Also filed: the SKIP-rule spike (is per-year banding what a truncated
      sliver should even ship, or is honest provenance labelling the real fix?).
      Suite 499 → 510; browser-verified on OpenAlex, a parked-corpus live build
      (QMIX showing per-year bands), and a corpus sanity build.
- [x] **Cold corpus builds take ~47s — the `papers` dataset is unsorted, so
      nothing prunes** *(v5.12.0; diagnosed 2026-07-17, the original prime suspect
      **refuted** — see below)* — a cache-miss graph on the s2 provider takes ~47s
      against the live path's ~15s. **It is not the citations bucket.** Measured on
      DQN (bucket 372, 390 files, 29 MB):

      ```
      scan the bucket (390 files), filter, group by      0.07s   -> 31,902 rows
      open all 390 parquet footers                       0.01s
      the same query + JOIN papers                       2.03s   -> 96% of the cost
      ```

      Hash-partitioning + `ORDER BY citedcorpusid` are doing exactly their job; the
      390 files are free. **Compacting buckets would buy nothing** — the old ticket
      spent its whole argument on a suspect that costs 0.07s. (The small-files point
      may still matter for the *ingest* scaling ticket, and for Athena. Just
      not for this.)

      **The real cause is projection width against an unsorted `papers`.** Parquet
      is columnar, so every column projected is more bytes off the disk, and the
      same join at four widths:

      ```
      1 column   (corpusid)                              0.73s
      3 columns  (+ year, citationcount)                 1.09s
      8 narrow   (everything but authors)               20.64s
      9 columns  (what the app selects, incl. authors)  39.24s
      ```

      `authors` alone — a JSON blob per paper — costs **+18.6s**. And the app reads
      all nine columns for **31,878** citers to ship **63**.

      **But fetching fewer rows doesn't help, and that's the finding.** Hydrating
      those 9 columns for just the 63 winners still took **33.28s** — the same as
      for all 31,878. Why: **every one of `papers`' 1,946 row groups spans 100% of
      the corpusid range** (728 … 289,920,059 out of 0 … 289,923,617). The rows
      landed in arrival order, so every zone map says "maybe" and **nothing prunes**.
      Any corpusid lookup is a full scan of 24.8 GB, whether it wants 63 rows or 31k.

      **The ingest asymmetry that caused it** (`corpus/ingest.py`): the citations
      COPY ends `ORDER BY citedcorpusid` and partitions by bucket. The papers COPY
      does **neither** — no ordering, no partitioning. One missing `ORDER BY` is the
      whole 20–40s.

      **The fix is two changes that only work together** — each is useless alone,
      which is why the obvious single fixes were measured and rejected:

      **(a) Cluster `papers` by `corpusid`** — **and it must be *global*, not
      per-shard.** Adding `ORDER BY corpusid` to the existing per-shard papers COPY
      would NOT work: every shard holds ids spanning the whole 0–290M range, so
      sorting inside one still leaves each of its row groups covering ~1/32 of the
      range, and scattered ids hit them all. It needs either a post-ingest
      compaction pass over the whole dataset (`COPY (SELECT * FROM
      read_parquet(papers/*) ORDER BY corpusid) TO …`, so each output row group owns
      a contiguous slice) or `PARTITION_BY (corpusid % NBUCKETS)` + sort within,
      mirroring what citations already does. **Tested on a 4-file, 1.8 GB subset**
      (written as one globally-sorted output): row groups' average id-range width
      collapsed from
      **289,918,845 (the whole range) to 2,027,421**, and a 63-id lookup went
      1.65s → 0.65s. The subset *understates* it — 63 ids hit ~44% of that
      subset's 143 row groups, but only ~3% of the full dataset's 1,946, so the
      full-scale win should be ~30x. Keeps the Parquet/Athena endgame — Athena
      prunes on the same stats. **Alone it is not enough:** the *ranking* query
      genuinely needs all ~31k citers, so it touches every row group regardless.

      **(b) Two-phase fetch** — rank on `(corpusid, year, citationcount)` (the
      budget rule only reads years), trim to the budget, then hydrate the wide
      columns for the ~63 winners. **Alone it does nothing:** measured, hydrating 63
      ids took **33.28s**, the same as all 31,878, because on an unsorted layout
      DuckDB must scan to find them. It only pays off once (a) makes small lookups
      cheap.

      **Together:** rank narrow (~1.1s) + hydrate 63 from a clustered `papers`
      (~1s) ≈ **2s against today's 39s**.

      **(c) If (a) disappoints**, the honest fallback is that **Parquet has no index
      and point lookups want one**: a DuckDB *native* table with an index on
      `corpusid` would make this milliseconds — but it abandons the Athena-over-S3
      story, so it's an architectural fork, not a tune-up. *(Patrick noticed
      fetching citations is slow, 2026-07-16; re-diagnosed and the fix tested
      2026-07-17, after he asked the obvious question — "I thought DuckDB was
      supposed to be fast? Do we need to index the db or something?" — which was
      closer to right than the ticket's own prime suspect.)*

      **Shipped (v5.12.0), both halves, (c) not needed.** (a) became a
      **compaction pass at the end of every papers ingest** — the global variant,
      as tested: shard files land as before (the incremental resume unit), then
      one `ORDER BY corpusid` sort rewrites them as `clustered_*` files. The swap
      is crash-safe (staged in `_compacting/`, committed by a `MANIFEST.json`,
      resumed *before* the shard loop so an interrupted swap can never
      double-ingest) and `_done/` markers keep reruns idempotent. The
      subset-extrapolated "≈3 minutes" was optimistic — the full 24.8 GB exceeds
      DuckDB's memory cap, spills (`_spill/`), and ran **~10–15 minutes** on the
      real release; a DuckDB progress bar now shows during the sort (added after
      Patrick sat through the gap with no feedback). `atlas corpus compact`
      migrates a pre-v5.12.0 corpus in place off the parquet root alone. (b) is
      the query shape in `source.py`: both citer queries rank narrow
      (`corpusid, year, isinfluential`), the landmark budget rule now travels
      *into* `landmark_citers` and trims **between the phases** — it still
      measures the full ranked pool, the v5.11.0 invariant — and only the winners
      are hydrated wide. Browser-verified on the real corpus: cold s2 builds
      dropped from ~47s to roughly the live path's ~15s. 8 new tests (clustered
      layout + global sort, no re-sort on rerun, legacy migration,
      interrupted-swap resume) take the suite to 499.
- [x] **The corpus path stops predicting and starts measuring — and gets a real
      frontier** *(v5.11.0)* — the corpus served real all-history citers but used
      neither trained model properly: `cite_budget` was *predicting* a number the
      local pool could just be asked for, and `bands.earliest_band_year` was never
      wired in at all, so Latest Publications was the **flat rolling 12-month
      window** inherited from the live fallback. The one provider with every edge
      and every date had the least honest frontier.
      **Both halves are now measured, not argued** (`live_pool_validation`'s
      verdict — see the entry below):
      **Landmarks compute.** The model's premise *did* hold here (R² **0.644** on
      corpus pools against its own cross-validated **0.680** — a −0.037 transfer
      gap; nothing was wrong with the model). It came off anyway, because the reason
      to predict was cost and **the cost wasn't there**: timed on DQN, warm,
      `landmark_citers(limit=63)` took **22.08s** and `limit=None` — all **28,732**
      citers — took **22.28s**. The `LIMIT` saved **0.9%**; the scan, dedupe and
      200M-row papers join dominate either way, so the query had already paid for
      the pool and was discarding it. `budget.computed_cite_limit` now runs the STOP
      rule over the real years: DQN **63** where the model said 60, Hawking **176**
      where it said 160 — the model's own answer, minus ~21 mean absolute error.
      The trained model now serves **OpenAlex alone**, the one path whose pool would
      have to cross a network to be counted — exactly where
      [predict-vs-compute.md](predict-vs-compute.md) predicted it would end up.
      **Latest bands.** `bands.band_start_rule` is wired in, and the flat window is
      gone. On the real corpus: Hawking's bands start **2020** (7 bands, reaching
      back to meet a cluster dense to 2024), DQN's start **2023** (a tight 4-year
      frontier where the fixed span would have said 2020). One windowed DuckDB query
      (`ROW_NUMBER() OVER (PARTITION BY year …)`) does what OpenAlex needs one HTTP
      call per year for.
      **The subtle part, and Patrick's catch.** The first cut gave the corpus the
      *live* path's banded selector — 12 landmarks per year — on the reasoning that
      "compute, don't predict" implied "SKIP, not STOP". Two different claims: the
      0.9% measurement settles where the *number* comes from, not which *rule*
      applies, and the rule turns on the **pool's shape**. Patrick pushed back that
      he preferred the model's band, and was right twice over: banding forces
      `PER_YEAR_CAP` nodes out of *every* year (the best of a thin 1970 over the
      13th-best of a blockbuster year), and — by the verdict's own finding — it
      flattens the year distribution the tau rule reads, which would have **broken
      the Latest bands on this very path**. A prefix of a *whole-history* ranking is
      what a Field Landmark is; the live path bands only because its pool is a
      recency sliver with no all-time ranking to prefix. Same cap, same invariant,
      different pools, different rules.
      **What it cost to switch:** the s2 provider's landmark/latest split no longer
      means the same thing live vs corpus — a deliberately abandoned symmetry. The
      corpus and OpenAlex (both whole-history) now agree, and the live path is the
      odd one out because it structurally cannot join them.
- [x] **Live-path landmarks & Latest: the age-origin study — validated, and
      unneeded** *(v5.10.0's study; verdict 2026-07-17, no code change)* — Patrick's
      design to bring both trained models back to the live S2 fallback: (1) keep
      paging the reachable list, (2) run `cite_budget` with its **age origin at the
      oldest citer in the pool** rather than the seed (the truncated pool doesn't
      span the seed→now gap the seed-origin feature describes — DQN reads as a dense
      7-year history, not a 13-year classic), (3) let the model set the *total* only,
      with per-year banding still choosing *which* papers, (4) place the Latest band
      start with the `latest_gap` tau rule instead of a flat 12-month window. The
      ticket demanded it be **validated offline before wiring**, and stated its own
      null hypothesis up front: the live path already holds the pool, so the rule is
      computable, so the model may prove redundant. `ml_pipelines/live_pool_validation`
      simulated the exact reachable pool (newest 9,000 citers) for 58 seeds — 18 of
      them truncated — and ran both age origins against the rule computed exactly.
      **The verdict, in `research/live_pool_validation/analyze.ipynb`:**
      **Step 2 was right about the disease and wrong about the cure.** The seed
      origin *is* broken on truncated pools — **R² −0.707**, worse than predicting
      the mean — and moving the origin to the oldest reachable citer really does
      repair it, to **+0.446**. The diagnosis was correct. But the repaired model
      still misses by **41%** (MAE 25.5 against a label averaging 62.7) on a number
      the serve path can compute *exactly, for free, from memory*. So the null
      hypothesis held — not by the route it predicted (the model tracking the label
      so closely as to be redundant) but by a blunter one: predicting a computable
      quantity inherits error and saves nothing
      ([predict-vs-compute.md](predict-vs-compute.md), *a fortiori*). The sharpest
      form: **the age-origin repair fixes a distortion that only exists on truncated
      pools, and the only path with truncated pools is the one path that needs no
      model.** Correct, and nowhere to live.
      **Step 4 turned out unbuildable** — a finding the ticket's "eyeball the
      transfer rather than trusting it" caution earned. **56 of 58 seeds collapsed
      to a single-year Latest band**, and structurally so, twice over. First, step 3
      destroys what step 4 needs: `tail_edge` thresholds at `tau × the peak year's
      count`, but `select_up_to_cap_per_year` caps *every* year at 12 — so the peak
      **is** the cap, the threshold collapses to `0.25 × 12 = 3`, and any full year
      clears it instantly. Hawking's pool spans 1998–2026 and its selection is
      **exactly 348 = 29 × 12**; of the 23 seeds whose selection is exactly
      `12 × span`, **23 of 23** got a one-year band. Fed the app's own `tail_edge`, a
      flat 12/year shape returns 2026 where a top-N shape (what tau was *fit* on)
      returns 2020. Second and deeper: **a truncated pool has no recent tail to
      find** — it *is* the recent end, by definition. Steps 1 and 3 were already
      v5.5.0's shipped behavior, so the whole ticket resolved to **change nothing**.
      **Two things it left behind.** The tau rule *does* belong somewhere — the
      corpus path, which has real full-history distributions and still serves a flat
      12-month window (folded into the corpus-models ticket). And a finding neither
      ticket asked for: "exact" is a claim about arithmetic, not about the pool. The
      live path's computable label is exact about a sliver — VMD **12 against a
      full-history 166** (13.8×), median **1.8×** across the truncated seeds, and
      *Attention Is All You Need*'s newest 9,000 citers all sit in **one year**. The
      live path's real fix was never a better estimator; it's the offline corpus.

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

- [x] **Single-source provider selector — the hybrid retired** *(v5.0.0 — major)* —
      a graph is now built from **one** academic-data backend, chosen per graph in
      the header's **"Data source"** dropdown (`Semantic Scholar` / `OpenAlex`),
      instead of the v4.x hybrid (S2 seed/refs/similar + OpenAlex citations merged
      with `max` counts and cross-source id dedup). Each provider stands alone:
      **S2** does seed/references/citations via S2 (its live citation API is
      newest-first + ~10k-offset capped, so Field Landmarks are the top-cited among
      the *recent* citer tip — a known interim bias, surfaced as a note in the graph
      controls and lifted later by the offline citations corpus); **OpenAlex** does
      the whole graph via server-sorted `cites:`/`cited_by:` queries (true top-cited
      landmarks, no ceiling — but a famous *published* seed resolves to its
      lower-cited arXiv-preprint record). Wins: **one citation-count scale** (node
      sizes finally comparable across relations), and the whole cross-source glue
      (`_upgrade_node` count-max, OA→S2 fallback, `_citation_relations`) deleted.
      OpenAlex grew the two pieces it was missing to stand alone — `references()`
      (a `cited_by:` filter) and `resolve_seed_work()` (arXiv id / `DOI:`/`ARXIV:`/
      `W…`). **Provider is part of the cache key** (`graph:<provider>:<seed>`, so an
      S2 and an OpenAlex graph for one paper never collide) and the **local cache
      search is provider-scoped** (a cached paper's "instant" badge is truthful only
      for the selected backend). `config.graph.default_provider` (`"s2"`) seeds the
      dropdown; the choice persists across Home and into a saved session. **Rolls up
      "Drop the Similar relation from the graph"** (below): the purple `similar`
      relation is off the built graph (chip + legend + build removed), the S2
      recommendations client kept only for the researcher's `expand_node`.
      *(Patrick's design; browser-tested 2026-07-13. Phase 1 of the provider work:
      the seed SEARCH and detail panel still hydrate via S2 for both providers —
      since shipped as v5.1.0, below.)*
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
      months — see "Mega-paper citation coverage" below (since
      shipped as v3.1.0).
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
      the landmark middle band. **The stop-at-the-window half was retired in
      v5.5.0** — "the boundary page fills the middle band" held only while mining
      still supplied the real landmarks, and once v4.0.0 retired mining it left
      `landmark` living off one page of overshoot. See the v5.5.0 entry below and
      the Bugs entry "Field Landmarks were never landmarks". **Verified on DQN: ~3k citers paged, landmark
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
- [x] **The s2 live fallback's Field Landmarks made honest** *(v5.5.0 — minor)*.
      The s2 provider's live citer path (used whenever the offline corpus can't
      resolve a seed) was shipping a landmark relation that wasn't one: on DQN,
      2024–2025 LLM-agent surveys led by a 394-cite *Trust in AI*. Four compounding
      causes, each fixed (full stories in **Bugs**):
      - **The pager stopped at the `latest` window**, not the ceiling — so the
        landmark ranking got a 1999-citer pool covering two years while the
        reachable list runs back to **2019** with 7999. It now pages the whole
        list; `latest` is unchanged, cold builds cost more (QMIX 4 pages / ~8s,
        DQN 9 / ~15s). `_MAX_OFFSET` 9000 → **8000** (S2 400s a page whose window
        reaches ~10k; verified live), so the reachable pool is ~9k, not 10k.
      - **The cite-budget model was serving a pool it wasn't trained on** — its
        label came from OpenAlex's whole-history rankings, so it read DQN's age and
        sized for landmarks spanning decades that a ceiling-truncated pool doesn't
        have (63 predicted, 29 admitted). The live path now **selects from the pool
        it already holds** (`budget.density_selection`) instead of predicting; the
        model still serves the ranked paths (OpenAlex, corpus), where it's valid.
      - **A count can't express the answer.** The density rule is a *prefix* — one
        dense year ends the walk — so 2020 filling at rank 29 stranded 2024–2025
        entirely, leaving an 18-month hole before the Latest frontier. The
        selection **bands the ranking per year** (≤`DENSITY_CAP` each, skip the
        full ones): 84 landmarks across 2019–2025, same "no year over the cap"
        guarantee, no hole. It's the local equivalent of OpenAlex's per-year query
        bands — S2's `/citations` has no year filter, so it happens over the
        ranking. `density_budget` stays as the model's training label (a regression
        label has to be a scalar) and moved into `services/graph/budget.py` beside
        the features, with `ml_pipelines/cite_budget` importing both back.
      - **Date-poor papers got a guaranteed quota.** Undated citers are dropped
        rather than bucketed, `_is_latest`/`_latest_order` fall back to `year` when
        S2 gives no date (a post-cutoff year is frontier, not history), and
        Timeline filters undated papers out of the view. Killed both vertical
        lines. Result on DQN: 84 landmarks, 2019–2025, led by CQL, Decision
        Transformer, Dota 2. *Still ceiling-bound:* 2013–2018 (AlphaGo, A3C,
        Rainbow) is unreachable live at any page count — the corpus's job.

- [x] **Phase 2 — provider choice extended to search + detail** *(v5.1.0)* —
      v5.0.0's selector governed the *graph build only*; now picking **OpenAlex**
      is coherent end-to-end. **Seed search** has an OpenAlex path
      (`openalex.search_papers` — `search=` relevance over title/abstract/fulltext,
      year window as `from/to_publication_date`), with **provider-aware copy**
      (the hit list reads "Searching **OpenAlex**…" / "From **OpenAlex**"), and the
      local cache search already scoped per provider (v5.0.0). **Detail hydration**
      comes from the graph's provider (`openalex.get_paper` — abstract from the
      inverted index, **topic tags** from `topics`, no TL;DR so the panel shows the
      abstract; the panel's field-tag heading is provider-aware); OpenAlex nodes
      hydrate **by their node id** (the reliable `DOI:`/`W…` form — a bare arXiv id
      can miss a published paper's canonical OA record). **Field filter** is now a
      real, per-provider control: a new **OpenAlex field taxonomy** (`openalex.vocab`,
      the 26 top-level fields) served by `/api/taxonomy/openalex` in a unified
      `{id, name}` shape (S2's picker adopts it too), the picker refetches per
      provider, and OA search filters by `topics.field.id`. **The `arxiv` taxonomy
      provider was retired** (dead — it fed the long-gone arXiv-category search
      filter; `arxiv.vocab.groups()`/`valid_codes()` deleted, `name_for` kept for
      the detail-panel tags). *Deferred (its own ticket below): making the
      researcher's `expand_node`/`search_papers` tools provider-aware — still
      S2-only.* *(Patrick's asks incl. the OA field taxonomy + arxiv-taxonomy
      removal; browser-tested 2026-07-13.)*
- [x] **Provider-aware researcher tools** *(v5.2.0)* — the Q&A researcher's
      `expand_node` (references/citations/similar hops), `search_papers`, and its
      lazy detail hydration now follow the **selected graph provider** instead of
      always hitting S2 — so an OpenAlex graph stays OpenAlex end to end (no more
      S2-paperId nodes pulled onto an OpenAlex graph). `agents/traversal.py`'s
      `neighbors`/`search` branch per provider (OpenAlex resolves the node id →
      work, then `cited_by:`/`cites:`; the **similar** hop uses OpenAlex
      **`related_works`** — its concept/citation-overlap neighbors, weaker than
      S2's SPECTER2 but the closest analogue, chosen over a graceful degrade).
      Provider is in the traversal cache keys and threads
      `route → orchestrator.run → researcher.answer → ResearcherDeps.provider →
      the tools`; the frontend sends `provider` on `/api/ask`. *(Patrick's ask;
      browser-tested 2026-07-13.)*
- [x] **Phase 3 — S2 citations corpus (the real Field-Landmarks fix for S2)**
      *(v5.4.0)* — option **(b)** from `docs/citation-coverage.md`, shipped as a
      corpus-**optional** pipeline in `integrations/semantic_scholar/corpus/`. The
      bulk **`citations`** (2.4B edges, ~255GB) + **`papers`** (200M, ~45GB)
      Datasets releases are downloaded (resumable, checkpointed, signed-URL-expiry
      aware) and ingested via **DuckDB → Parquet**: papers projected + arXiv-indexed,
      citations **hash-partitioned on `citedcorpusid`** so a single seed's citer
      lookup reads ~1/1024 of the edge list. The app queries its own copy through a
      small **`CitationSource`** seam (`landmark_citers`/`latest_citers`) — a
      **`DuckDBCitationSource`** now, the **Athena-over-S3** impl (the AWS Airflow
      endgame) later behind the same two methods. `build.py::_traverse_s2` prefers
      the corpus (landmarks **citation-sorted across all history** — the ranking the
      live ~10k-offset endpoint can't give) and falls back to the recency-biased
      live path when the corpus is absent or can't resolve the seed. Operator
      workflow via the **`atlas corpus`** CLI (`status`/`download`/`ingest`/`activate`);
      corpus root is `config.storage.s2_corpus_dir` (gitignored, outside the repo).
      Which path served a build is on `Graph.citation_source` and surfaced in the UI
      (the Field-Landmarks note reads "offline citations corpus" vs the live caveat),
      plus a DEBUG build log. *(Patrick's plan, filed 2026-07-13; shipped 2026-07-15.)*
- [x] **Corpus ingest made viable — the partition-limit fix + a split parquet root**
      *(v5.6.0 — minor)*. Ingesting the first full release surfaced two things. The
      **bug**: DuckDB's `partitioned_write_max_open_files` defaults to **100** while
      we partition into **1024** buckets, so it cycled partitions open/closed and —
      Parquet being unappendable once closed — started a *new file* each time. One
      shard → ~21k files at **3.5 KB** (nearly all footer), ~8M projected for the
      release; file *creation*, not throughput, was the bottleneck (2.8 min/shard,
      ~18h projected; listing the output dir timed out). `_connect()` now raises the
      limit past `NBUCKETS` and stops pinning `threads=8`/`memory_limit=8GB` *below*
      DuckDB's own machine-sized defaults (16 / 25 GiB), which its docstring already
      claimed it wanted. Measured: **1024 files/shard, one per bucket, at 61 KB.**
      The **design point**: `raw/` is ~400 GB read exactly once, sequentially (fine
      on a spinning disk), while the Parquet is the queried working set and takes
      the ~400k partitioned writes — 20.6s/shard on NVMe vs 98.2s on an SMR HDD. New
      optional **`config.storage.s2_corpus_parquet_dir`** puts the halves on
      different drives (null = today's layout, and the right answer once one fast
      drive holds everything); `paths.release_paths()` wires both roots so a
      hand-built `ReleasePaths` can't silently ignore the split, and `corpus status`
      prints both. Full stories in **Bugs**; the residual O(n²) scaling and the
      `activate`-only-checks-papers hole are filed in the OnePager Backlog. *(Found while ingesting
      the 2026-07-07 release, 2026-07-15.)*
- [x] **Corpus citers deduped — S2 ships every edge twice** *(v5.6.1 — patch)*.
      The `2026-07-07` citations release is **two overlapping export batches** (240
      shards `…_00151_3g69z_…` + 150 `…_00016_bxc9g_…`, exactly as S2's API lists
      them): 5.1B rows for ~2.7B distinct edges. So `landmark_citers(limit=63)`
      counted **rows, not papers**, and DQN's 63-landmark budget bought ~32 — the
      right papers, half the graph. `source._citers` now groups by `citingcorpusid`
      before the join and the limit, `bool_or`-ing `isinfluential` (the batches
      disagree). Can't be done at ingest: a duplicate pair spans two shards, so a
      per-shard `DISTINCT` never sees both copies. The synthetic fixture now ships an
      overlapping second batch the way S2 does, so the plain landmark assertions fail
      if the dedupe is removed. Full story in **Bugs → Upstream**. *(Found right after
      the first full corpus went live, 2026-07-16.)*
- [x] **The corpus's two roots, named for what they hold** *(v5.7.0 — minor;
      **breaking config change**)*. v5.6.0's split bolted a second path onto a flat
      key: `s2_corpus_dir` + `s2_corpus_parquet_dir`. The first name stopped being
      true the moment the second existed — it reads "the corpus root" but meant
      "wherever the shards live, plus the pointer", with the Parquet a bolt-on.
      Now they're peers under one group, each named for its contents:
      ```json
      "storage": { "s2": { "raw": "E:\\s2corpus", "parquet": "D:\\s2corpus" } }
      ```
      matching how `providers.s2` / `llm.providers` already group. **`CURRENT` moved
      to the parquet root** — it names an *ingested* release, so it belongs beside
      the data it points at, and the payoff is real: the parquet root is now the
      app's **only serving dependency**, so shards can be deleted (or their drive
      pulled) and graph builds carry on. Previously serving needed both drives just
      to read a one-line pointer. `download.json` likewise sits with the shards it
      tracks. `paths` gains `raw_root()`/`parquet_root()`; `ReleasePaths` takes both
      and **raises** on an unconfigured half rather than defaulting to the other —
      silently defaulting is how Parquet once got written to a drive nobody asked
      for. `corpus status` prints both roots and a per-release `shards=` column, so
      "downloaded but not ingested" and "ingested, shards deleted" are both legible.
      **Breaking:** an old `config.json` fails validation loudly (`extra="forbid"`)
      rather than silently losing the corpus — the right trade. *(Patrick's call on
      the shape, 2026-07-16.)*
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
- [x] **Prune ghost similar papers (no citations AND no publication history)**
      *(v4.10.2)* — S2 recommendations that carry **zero citations AND no
      year/date** are unverifiable noise, so they're dropped from the *similar*
      relation at build time (`build._is_ghost_similar`, in the recommendation
      loop) — before the node and before the `similar` count, so the slider's
      pool stays honest. Both conditions are required (any citations, or any
      year/`pub_date`, keeps the paper); the prune is scoped to `similar` only,
      never to a verified reference/citation/latest link. Pinned by a
      boundary-case unit test on the helper plus a build-level test that a ghost
      is dropped while a cited-but-dateless and a dated-but-uncited
      recommendation stay. *(From the `todos.md` inbox, 2026-07-10.)*

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

### UI & rendering polish

- [x] **Show the publisher/venue in the Detail panel** *(v5.26.0)* — the
      panel named no venue. Now the meta block reads **`Authors: …`** /
      **`Publisher: *venue*`** (prefix plain, value italicized — both
      Patrick's browser-round calls) above the unchanged date · citations
      line. Full-stack: both providers gained a **`venue`** on the shared
      node shape — S2 prefers the normalized `publicationVenue` record with
      the legacy `venue` string as fallback (`venue_name()`), OpenAlex takes
      `primary_location.source.display_name` — as a **detail-tier** field
      like the abstract (seed at build via DETAIL_FIELDS/DETAIL_SELECT,
      neighbors hydrate on first open; arXiv-only papers honestly read
      "arXiv"). The graph model defaults it None so pre-venue cached
      snapshots validate, and `cleanNode` persists it (a restored node with
      an abstract never re-hydrates — dropping it would lose the seed's
      venue every restore; note the same gap exists for `fields_of_study`,
      which cleanNode has never persisted). The polish rounds also aired
      out the panel: meta rows 3→10px apart, tag groups 10→16px. Tests: S2
      preference/fallback/empty, OpenAlex primary-location/missing/
      sourceless, a DetailPanel render case; field-tier READMEs updated.
      *(From the `todos.md` inbox, 2026-07-18; shipped 2026-07-18.)*
- [x] **Select-all for find-bar matches** *(v5.25.0)* — the lexical find
      spotlighted matches, but scoping the teacher to them meant
      alt-dragging or shift-clicking one by one. The find pill now commits
      the whole match set to the hand-picked selection in one press — a
      **"select" link** beside the hit count AND **Enter in the box**
      (added on Patrick's browser round; both affordances kept on purpose:
      the link is discoverable, Enter is fast; Enter no-ops on zero hits).
      Additive via `nodeSelectionAdded`, exactly like the marquee, so
      repeated finds build a scope; GraphExplorer clears the find on
      commit so the cyan selection (not the find spotlight) shows the
      result — find → select → ask in three gestures. Tour's find stop,
      input/link tooltips, and the controls README teach both paths
      (final tour phrasing Patrick's own); FindBar suite +2 cases on a new
      makeProps helper. *(From the `todos.md` inbox, 2026-07-18; shipped
      2026-07-18.)*
- [x] **DATA SOURCE dropdown arrow overflows its box** *(v5.24.1)* — the
      header select relied on the native caret, which macOS rendered just
      past the rounded border. Fixed by owning the caret:
      `appearance: none` plus a muted data-URI SVG chevron drawn inside the
      box (`--muted` hardcoded — CSS vars can't reach into a `url()`), with
      right padding reserving its lane. *(From the `todos.md` inbox,
      2026-07-18; shipped 2026-07-18.)*
- [x] **Cleaner layout for expanded nodes — in BOTH layouts** *(v5.24.0)* —
      the researcher's `expand_node` discoveries used to land on top of the
      seed's neighborhood; after v5.23.0's relation clustering the failure
      got legible (a dashed-ring `reference` discovery was absorbed into the
      seed's blue sector, torn away from the node it was expanded from).
      Shipped as the sketched **satellite mini-clusters**: `useDiscovery`'s
      merge stamps a discovery anchored on a non-seed node with `_origin`,
      and the cluster force gathers such satellites just **beyond their
      origin, on the seed→origin ray** (own √population offset, pull 0.12 —
      a touch over the sectors' 0.08 so small groups stay gathered), the
      formation following the origin's live position. Satellite links stay
      short (the per-type orbit distance would have dragged them a whole
      orbit out — the accessor checks resolved endpoints for `_origin`),
      and satellites don't inflate sector populations. **Timeline**: x is
      date-pinned, so the merge bands satellites **outward in y** past
      their origin's side of the settled (height-frozen) mass instead.
      **Restore round**: a browser-verified session-reopen initially
      dissolved the satellites — saves fold discoveries into the graph, so
      the stamps were lost; `clusterForce.deriveOrigins` re-derives them in
      GraphExplorer's base build (first edge's other endpoint, when not the
      seed). Found while chasing a reported restore→Timeline "blank screen"
      via Claude-in-Chrome live debugging — canvas-arc hooks showed all 374
      nodes at finite coords and a mathematically correct zoomToFit, and
      the blank turned out to be a stale cached bundle (gone on hard
      reload), not a code defect. Vitest 147 → 154 (sector-vs-origin
      priority, orphaned-origin fallback, sector-count exemption, origin
      stamping/derivation, the Timeline y-band). *(From the `todos.md`
      inbox, 2026-07-14; shipped 2026-07-18.)*
- [x] **Group graph nodes by relation type in the Force layout** *(v5.23.0)*
      — the force layout mingled every relation into one undifferentiated
      cloud ("way waayyy too much clutter" — Patrick, triggering the
      immediate build). Now a custom d3 force (`graph/clusterForce.ts`)
      organizes the neighborhood into **relation clusters around the seed**:
      fixed compass sectors, stable across graphs — references **west**
      (past-is-left, echoing Timeline), Field Landmarks up-right, Latest
      Publications down-right, the researcher's similar/search discoveries
      on the west diagonals — with anchors computed from the seed's LIVE
      position each tick (drag the seed, the formation follows) and each
      cluster's orbit growing with **√population** (area scales with the
      papers), so big clusters sit farther from the seed and each other.
      In-cluster spacing from a radius-sized collide (Force mode previously
      allowed overlap). The real clutter culprit: the **default link force**
      (distance 30, full strength on leaf nodes) yanked every neighbor into
      one clump on the seed — links now stretch to their relation cluster's
      orbit at low strength (0.08), defaults captured once and restored on
      the switch to Timeline. `useTimeline` became the explicit single
      owner of the d3 force slots (both layouts write 'collide'/'link'/
      'cluster' — two owners would fight on every switch), with one shared
      new-graph effect re-applying whichever layout is active; discoveries
      re-balance orbits for free via the force's own `initialize`. Vitest
      +7 (sector directions, √ orbits, live-seed anchoring, seed exemption,
      discovery re-init). Browser round: approved as-shipped; it also made
      the expansion-clutter failure legible — sharpening the separate
      "Cleaner layout for expanded nodes" ticket (satellite mini-clusters
      around the expansion origin, Timeline y-band treatment). *(From the
      `todos.md` inbox, 2026-07-10; shipped 2026-07-18.)*
- [x] **Reorder the tour steps to match expectation** *(v5.22.0)* — some
      GRAPH_TOUR stops ran in an order that didn't match how the eye moves
      through the UI; re-sequenced live with Patrick over three browser
      rounds (an AskUserQuestion picked the shape, then two corrections
      from walking it). The walk now: the top-left **controls panel walked
      top-to-bottom through its last row** ("Open a paper" — it lives in
      the panel, which round two caught after find was first slotted
      before it), then the **bottom-right find control** (it used to OPEN
      the tour — a leftover from its top-right era; starting on a tiny
      corner button read as a diagonal jump), then a **new whole-panel
      "The paper detail panel" overview stop** (round three's ask;
      spotlights the entire `data-tour="details"` aside, staging
      `'details'` like its section stops) before the five per-section
      detail stops, then the teacher block reordered to **lecture-scope →
      source-scope → lectures → ask** (both scope pickers before the
      lecture grid). HOME_TOUR reviewed and left as-is (header
      left-to-right already). Pure `steps.ts` array surgery + one new
      step; no component changes. *(From the `todos.md` inbox, 2026-07-18;
      shipped 2026-07-18.)*
- [x] **A loading state over the whole Detail panel while its pieces arrive**
      *(v5.21.0)* — the panel fans out to several services after opening
      (S2/OpenAlex abstract hydration, arXiv category tags, HF code links,
      the ar5iv figure strip), and each piece popped in as its call landed,
      so the panel assembled jankily. Shipped in two design rounds. Round
      one built the ticket's sketched "honest middle": per-section
      **skeleton placeholders** — anonymous shimmer shapes (`Skeleton`
      in-file, `.skel-*` variants; `aria-hidden`, shimmer off under
      `prefers-reduced-motion`), headless on purpose since a section may
      resolve to "nothing" and a named header that then vanishes is its own
      jank — each resolving independently. The browser round exposed the
      flaw: figures sometimes beat the abstract, so the assembly still read
      staggered. Round two (Patrick's call) put everything behind **one
      joint gate**: while ANY fetch is in flight, every loadable section
      holds its skeleton — even one whose answer already landed — and the
      whole set reveals in a single paint when the last answer arrives;
      empty sections simply don't appear. Node-local parts (badges, title,
      meta, actions) render instantly. Plumbing: `useSelection` grew a
      `detailLoading` id for the summary hydration; the arXiv-keyed trio
      infers "in flight" from `arxiv_id && response === undefined` (those
      fetches always fire on first open and cache failures), which let the
      old `figuresLoading` prop and the hook's exposed `figLoading` retire.
      The "Loading figures…" text hint retired too. Vitest: new
      `DetailPanel.test.tsx` (5 cases: the gate holding a known abstract,
      the one-paint reveal, instant node-local parts, the non-arXiv paths).
      *(From the `todos.md` inbox, 2026-07-18; shipped 2026-07-18.)*
- [x] **Mirror the collapsed bar's readout in the expanded panel — and fold
      "clear" into the action row** *(v5.20.0)* — the v5.19.0 collapsed bar
      got the honest readout but the expanded footer still read the bare
      `78 / 356 papers`, and the selection status kept its own
      `2 picked · clear` row. Now **one readout string, computed once,
      renders in both places**: `N / total papers shown` under bare filters,
      flipping to `N / shown papers selected` during a hand-pick (same
      shown-papers denominator, honest to the `selected ∩ visible` teacher
      scope). The status row retired, and **clear became a proper Clear
      button** in the action row after Release / Fit / Refresh — always
      present, disabled until a pick or a teacher highlight exists
      (Refresh's disabled pattern), firing the same shared reset as Esc.
      The footer now stacks (readout line above the four-button row):
      side-by-side already wrapped awkwardly with three buttons in
      Patrick's screenshot, and the longer wording + fourth button settled
      it. Tour's actions stop grew into "Release · Fit · Refresh · Clear"
      with a sentence for the new button; controls README reworked; tests
      rewritten around the button's disabled/armed states and both readout
      flips. *(From Patrick's screenshot review, 2026-07-18; shipped
      2026-07-18.)*
- [x] **Collapse the graph controls panel to a single bar** *(v5.19.0)* —
      the declutter panel (`GraphControls.tsx`, pinned top-left) was a fixed
      272px box over the canvas whether or not the user was touching it. The
      panel now wears a **"Graph controls" header strip that is itself a
      button**: one click collapses the whole panel to that slim bar (the
      width shrinks with it — the FindBar's collapse-until-wanted idea,
      panel-sized), another reopens it. The collapsed bar keeps reporting
      state — `N / total PAPERS SHOWN` under bare filters, flipping to
      `N / shown PAPERS SELECTED` while a hand-pick exists (denominator = the
      *shown* papers, honest to the `selected ∩ visible` teacher scope) —
      wording and both fractions tuned across the browser rounds. Collapse
      hides the body via `hidden` rather than unmounting, so the tour's
      `presentIf` existence checks still see the year/citation stops; a new
      tour stop on the header teaches the gesture, and every stop inside the
      panel now stages **`'controls'`** (`Atlas` → `GraphExplorer`'s
      `tourStage` → the new `stagedOpen` prop), re-expanding a collapsed
      panel mid-walk and never re-collapsing after (the detail panel's
      no-tidy-up precedent). The collapsed flag is the panel's one piece of
      local state, like FindBar's own open/closed. Vitest +3 cases
      (round-trip with hidden-not-unmounted body, the readout flip, the
      staged re-expand); controls + tour READMEs updated. *(From the
      `todos.md` inbox, 2026-07-18; shipped 2026-07-18.)*
- [x] **A query-analyst toggle in the search bar — and rename "Filters"**
      *(v5.18.0)* — the search surface gave no way to skip the query-analyst
      agent; sometimes you want the raw keyword search without the LLM
      expansion round-trip (or its spend). Shipped as the ticket sketched: a
      checkbox in the popover, which therefore stopped being "Filters" — of
      the floated names ("Search options" / "Options" / sparkle-icon button)
      plain **"Options"** won against the mock, since the button sits inside
      the search form and the context is already there. Backend:
      `live_search(analyst=)` + `/api/search?analyst=0|false|no` — off skips
      `_analyze` *and* the recalled-title verification on both provider
      paths and runs the lexical search on the words as typed; the day-long
      result cache now keys on the flag too (a raw search and an expanded
      search must never serve each other's entries). Frontend:
      `SearchFilters` → `SearchOptions` (`analyst: true` in the defaults),
      the switch counts toward the button's badge (a closed popover still
      shows the next search behaves differently) and survives a provider
      switch; "Clear all" became **"Reset"**, since it now turns a checkbox
      back *on*. The browser round added a one-line "why" hint under the
      checkbox — the search only matches words, so "DQN" misses papers that
      never spell it out — Patrick's verdict: "a bit verbose, but necessary
      to explain". Tour step, tooltips, and the READMEs across both trees
      updated in the same change. Suite 522 → 526 backend. *(From the
      `todos.md` inbox, 2026-07-17; shipped 2026-07-18.)*
- [x] **One "Abstract" section in the detail panel, with a TL;DR toggle**
      *(v5.17.0)* — the ticket's premise turned out half-stale (the panel
      already rendered ONE section showing TL;DR *or* abstract), so what
      shipped is the real gap: **abstract-first on both providers, with
      in-section Abstract | TL;DR tabs** — and a TL;DR for papers that have
      none. A new **`summarizer` micro-agent** (`agents/summarizer/`, the
      query_analyst mold: Haiku, structured output, None-on-any-failure; own
      config entry + README) writes one plain-language sentence from
      title + abstract — the digest era's "summarize" button reborn.
      **Billing is structural, per Patrick's rule** ("don't bill my Anthropic
      account for papers I don't read"): generation runs ONLY on the panel's
      explicit ✦-marked TL;DR tab click (`POST /api/paper/tldr` — the sole
      code path that can reach the model; builds/traversals/hydration
      can't), and the result caches **permanently** by node id
      (`tldr:v1:<id>` in `data/digest.db`), so each paper bills at most one
      Haiku call ever. Cached summaries ride ordinary hydration for free
      (`api_paper` back-fills the hole but never overwrites a provider's
      native TLDR) — and keying by node id makes the path provider-agnostic,
      so S2 papers S2 never summarized get the ✦ treatment too. Frontend:
      `SummarySection` in `DetailPanel` (tabs, pending "Summarizing…",
      in-place error with the abstract a tab away, ✦ tooltip naming the
      one-time cost), `useSelection.mergeDetail`, `api.generateTldr`. Tour's
      detail stop rewritten (twice — Patrick smoothing the copy). Suite
      511 → 521 backend, 131 → 135 frontend. *(From the `todos.md` inbox,
      2026-07-16; shipped 2026-07-18 — the last of the four-item UI slate.)*
- [x] **Lexical search over the nodes on screen** *(v5.16.0)* — a keyword find
      for papers **already on the graph** (titles/authors), fully separate from
      the seed search that fetches new ones. Purely lexical and local:
      `model.findMatches` runs a case-insensitive substring match over the
      *visible* view (a filtered-out paper can't match invisibly), and
      GraphExplorer routes the matches through the teacher's highlight
      machinery — matches glow + label, everything else dims, zero hits dims
      the whole graph (honest no-match feedback), and clearing hands the glow
      back to the teacher. The surface took three browser iterations to land
      (each Patrick's call): a box *inside* the graph controls (crowded) → an
      always-open rounded pill top-right (blended into the Timeline axis, then
      floated in no-man's land) → the shipped **collapsed round 🔍 button**
      top-right that expands into a focused pill on click, Google-Maps style.
      A live query pins the pill open; ✕ / Esc / blur-while-empty tuck it back.
      Esc-in-box clears the query first (the global Esc-clears-all skips form
      controls); the clear-all gesture and a new graph reset it too. New tour
      stop; `FindBar.tsx` + tests, `findMatches` tests. *(From the `todos.md`
      inbox, 2026-07-13; shipped 2026-07-18. Moved to the bottom-right corner,
      mirroring the legend, in v5.18.1 — the fallback spot agreed when
      top-right shipped.)*
- [x] **Source-scope picker doesn't appear until a page refresh (+ note it
      above the ask bar)** *(v5.15.0)* — `Teacher.tsx` fetched the library
      once, in a mount-only effect, into local state; an upload in the 📚
      Sources drawer never refreshed it, so the picker (shown at >1 source)
      stayed hidden until a manual reload. Fixed the way the ticket predicted:
      the source list moved into a new **`library` store slice** (the store's
      fourth) that the drawer re-loads through on every upload/URL
      ingest/delete and the panel reads live — mirroring how the
      lecture-scope picker reads `transcript.lectures`. The panel's scope
      choices also flipped to **exclusion-tracking** (`excludedSources`, like
      `excludedLectures`), so a source uploaded after the user last touched
      the picker is searchable by default; a `loaded` flag keeps the panel's
      per-epoch remounts from re-fetching. The ask-bar note is now one
      combined line — *"Answers also draw on 2 played lectures (🎓) · 3
      sources (📚)"* — shown whenever either is in play, graph or
      library-only mode. Browser testing surfaced a latent popover bug the
      newly-usable picker exposed: with a subset checked, "Select all" +
      "Deselect all" both render and overflowed the 240px popover (heading
      wrapped, ✕ off-view, horizontal scrollbar) — bulk actions are now
      compact **All / None** links, the popover is `overflow-x: hidden`, and
      the header no-wraps. Suite 116 → 121. *(Patrick's report, 2026-07-11;
      shipped 2026-07-17.)*
- [x] **One fast "unhighlight everything" action** *(v5.14.0)* — clearing what's
      lit on the graph was piecemeal: the hand-picked selection had its own
      Clear, and a lit lecture beat / chat answer / inline `[n]` ref cleared by
      clicking it again. Now **Esc** (new `useEscapeClear` hook — skips form
      controls, and defers to the lightbox's and tour's own Esc-to-close) and
      the controls' `clear` link both run one `onClearAll`:
      `nodeSelectionCleared()` + `highlightSet([])`. The teacher panel's
      active beat/answer/ref marks follow the emptied global highlight on
      their own (`useConversation` watches the set — which also fixes a latent
      staleness where a graph reload killed the glow but left a beat looking
      lit). The controls row now shows "**N lit** · clear" when only the
      teacher's glow is active, the gesture hint teaches `esc clears all
      highlights`, and the tour's scope stop teaches Esc too. *(From the
      `todos.md` inbox, 2026-07-14; shipped 2026-07-17.)*
- [x] **Thicker dashed ring for "Discovered by teacher" nodes** *(v5.14.0)* —
      the ring was hard to see for a *painting* reason, not just a width one:
      it stroked the node fill's own arc, burying half its 1.2px line under
      the disc. It now draws on its own path just outside the fill
      (radius + 1.5) at width 2, brighter (alpha 0.6 → 0.9), dash 3/2 — and
      restores the fill's arc as the current path so the lit/pinned/selected
      rings after it are untouched. *(From the `todos.md` inbox, 2026-07-14;
      shipped 2026-07-17.)*
- [x] **Release re-condenses a scattered force layout on demand — and keeps
      your zoom** *(v5.14.0)* — Release was disabled with nothing pinned, so
      the only way to pull a drifted force graph back together was abusing a
      filter chip's reheat side effect. Now always enabled: unpins everything
      (Timeline keeps its date columns) and `d3ReheatSimulation`s. Patrick's
      browser pass added the second half: releasing used to re-arm the
      one-shot `fitDone` latch, so the engine-stop re-ran `zoomToFit` and
      yanked the camera out to the whole graph — it no longer does, matching
      the discovery merge's "reheat without camera yank" rule. The tour's
      actions stop now says so. *(From the `todos.md` inbox, 2026-07-11;
      shipped 2026-07-17.)*
- [x] **Hide dateless papers in Timeline, keep them in Force** *(shipped
      inside v5.5.0; ticket retired 2026-07-17)* — filed 2026-07-11, then
      solved en passant by v5.5.0's landmark work: `GraphExplorer.nodeOk`
      drops `year == null` nodes (and, via the visible-set intersection,
      their edges) from the Timeline view only, Force still shows them, and
      the count readout reads the filtered view — everything the ticket
      asked for. Sat unnoticed in the Backlog until the v5.14.0 quick-wins
      batch went looking and found the work already done (with its own test
      pinning the behavior). *(From the `todos.md` inbox, 2026-07-11.)*
- [x] **Guided help tour (coach-mark modal) for the graph tools** *(v5.9.0)* — a
      stepped, spotlight-style onboarding overlay launched from an
      always-present header **"?" button**, walking the user through the app's
      controls one at a time: an anchored bubble dims the rest of the screen
      (the dimming is the spotlight's 200vmax box-shadow, so there's exactly
      one hole), rings the relevant control, and shows **Back / Next**, a step
      counter, a **jump select** (every stop's title, numbered — skip straight
      to any tip instead of Next-ing through the walk), **Skip tips**, and a
      **✕** — the Yotpo-style product tour Patrick mocked up. Shipped as the
      reusable, data-driven component the ticket asked for (`tour/Tour.tsx`
      over a `steps.ts` array of `{ target selector, title, body }`,
      positioning each bubble off the target's bounding rect, clamped into the
      viewport, and skipping steps whose target is absent or hidden — so one
      list describes the maximal tour), plus what the build grew: **two
      phases** with their own localStorage seen-flags (**HOME_TOUR** auto-runs
      once on first launch over the search surface; **GRAPH_TOUR** once on the
      first graph over the graph tools — the "?" re-runs whichever fits what's
      on screen), **staged steps** (`stage:` — the tour opens the
      Library/Assistant/Sessions drawers and the detail panel itself, polling
      briefly for the just-mounted target; `presentIf` proxies gate stops
      whose own target only exists after staging), targets marked by greppable
      `data-tour="…"` attributes planted where the controls render, arrow-key
      / Esc navigation (arrows defer to the jump select while it has focus),
      and re-measuring on resize and capture-phase scroll. The first
      motivation is honored — the node-selector's alt-drag / shift-click /
      alt-click gestures get their own stop — and the researcher stop
      re-states the grounding contract (the papers you've selected, else every
      visible one) for emphasis. 10 jsdom/RTL tests (`test/tour/Tour.test.tsx`)
      pin the walking, absent-target skipping, staging, jump select, and all
      three quit paths. *(From the node-selector session, 2026-07-12.)*
- [x] **Rename the "Sources" button to "Library"** *(v5.3.1)* — the top-bar
      toggle reads **📚 Library**, and the drawer's own heading/aria-label
      followed ("Your sources" → "Your library") so the button and what it
      opens agree. **User-facing copy only**: the noted naming tension resolved
      as label-over-rename — the feature stays `sources` in code
      (`SourcesConfig`, `/api/sources`, the `Sources` component,
      `onOpenSources`, `sources-toggle`) to keep the "library"-vs-Python-
      packages ambiguity out of identifiers; the header and library READMEs
      document the label↔name mapping. *(From the `todos.md` inbox,
      2026-07-14.)*
- [x] **The assistant's two scope popovers shouldn't overlap** *(v5.3.2, bug)* —
      the AI-teacher header's two `ScopePicker`s ("🎓 All lectures" and "📚 All
      sources") could both be open at once, their popovers overlapping
      illegibly (screenshotted 2026-07-14); each picker held its own `open` in
      component-local `useState`, so nothing coordinated them. Fixed by making
      the picker **controlled** (`open`/`onOpenChange` props) with `Teacher.tsx`
      owning one shared slot (`openScope: 'lectures' | 'sources' | null`) —
      opening either closes the other. Also added a **✕ close button** in the
      popover header next to "Deselect all" (re-clicking the trigger still
      closes too). The controlled contract is pinned by 3 new RTL tests
      (`test/teacher/ScopePicker.test.tsx`, the suite's third jsdom file —
      with the explicit `afterEach(cleanup)` the no-globals setup needs).
      *(Patrick's browser find, 2026-07-14.)*
- [x] **Node selector tool that scopes the lectures and Q&A agents** *(v4.13.0)* —
      **hand-pick which nodes** the teacher works over, right on the graph. An
      **alt-drag marquee** (a transparent overlay that arms only while Alt is
      held, so it captures the drag without fighting react-force-graph's
      pan) sweeps up the enclosed **visible** nodes via screen-space
      hit-testing (`fgRef.graph2ScreenCoords`), and **shift-click** toggles a
      single node. The pick is **additive** — each sweep unions onto it, so
      several clusters build one scope; **alt-click** empty canvas or the
      controls' **Clear** resets it. Picked nodes ring **cyan** and the rest
      **dim**. The pick lives in the workspace slice (`selectedNodeIds`) and
      threads into grounding through `selectGroundingNodes`, which now
      **intersects** it with the filters: grounding = `(selected ∩ visible) ∪
      discoveries`, so hiding a relation after picking also drops those nodes
      (discoveries are always kept). Both the lecture (`streamLecture`) and the
      Q&A researcher (`streamAsk`) already send `nodes: groundingNodes`, so no
      payload plumbing changed — the selection just narrows what they see. The
      controls carry an always-on gesture hint and a picked-count/Clear row;
      the assistant panel notes an active pick above the ask box. *(Design
      calls, made with Patrick: intersect-not-replace for the filter interplay;
      an **additive** marquee rather than an Alt+Shift "replace vs. add" split —
      Alt+Shift is the OS keyboard-layout switch on Windows and can't be used
      mid-drag; see the Bugs log. A guided **help tour** to teach these gestures
      was split into its own backlog ticket below.) *(From the `todos.md` inbox,
      2026-07-11.)*
- [x] **Colour-coded lecture buttons + a two-view assistant panel** *(v4.11.0)* —
      a full pass over the assistant panel, tying each lecture to the nodes it
      narrates and de-cluttering the whole surface. **Buttons are colour-coded to
      their relation** (`MODES` in `Teacher.tsx`, `--c` from `REL_COLOR`, the same
      hex as the filter chips / legend dots): "How we got here" blue (references),
      "What's evolved since" green (landmark citers — **renamed** back from the
      v4.8.0 "The landmark papers since" now the colour carries it), "The current
      frontier" light green (latest), "This paper's intuition" gold (seed). Each
      button shows **only its short node-type word, centred** (References /
      Landmarks / Latest / This paper); the full lecture name moved to the
      tooltip + aria-label and to a **"Now playing" header** above the transcript
      (tinted the relation's colour). The lecture section is ruled off under the
      panel title with a divider + one-line intro. **Two views, one panel**
      (gated on `activeMode`): a shown lecture takes over the scroll (header +
      beats), otherwise it's the Q&A chat — asking a question hides the lecture
      (kept cached) so beats and chat never stack. **The Landmarks green was
      darkened** graph-wide (`REL_COLOR.citation` `#4ade80`→`#22c55e`) to separate
      it from Latest's pale green, and the detail-panel badges gained
      `BADGE_COLOR` / `BADGE_LABEL`: both citing relations (`citation` + `latest`)
      now read as **one "citation" badge** in the original in-between `#4ade80`
      (Latest Publications ARE citing papers), deduped so a node never shows it
      twice. Shipped with a backend fix found while testing — concurrent lecture
      streams hit "Event loop is closed" (see [Bugs](bugs.md)).
      *(From the `todos.md` inbox, 2026-07-11; browser-tested.)*
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
- [x] **Remove the "Powered by Claude" attribution** *(v5.3.1)* — the v1.11.0
      top-bar credit (starburst SVG + anthropic.com link) removed, with its
      `.cc-credit` CSS and README/comment mentions. *(From the `todos.md`
      inbox, 2026-07-08.)*

### Infrastructure, quality & tooling

- [x] **Budget vocabulary — name the two rules, define every term once**
      *(v5.10.0)* — the landmark-sizing code had accumulated a vocabulary nobody
      could read: five functions whose names described a *criterion* ("density")
      rather than a *mechanic*, a label written `n*` that most prose quietly
      confused with the rule the app actually serves, and the word **"anchor"**
      meaning three unrelated things (the four worked-example papers; where the
      model's age feature is measured from; force-graph node pinning on the
      frontend). Patrick's diagnosis: *"it's just too confusing to follow without
      precise examples."*
      **The distinction everything turns on**, now carried by the names: both
      rules bucket a seed's citation-ranked citers by publication year and cap
      every bucket at 12; they differ in **one word** — on a full bucket, one
      **STOPS** the walk (`number_of_ranked_citers_before_a_single_year_overflows`,
      the model's training label, and *only* that — no serving path calls it),
      the other **SKIPS** that citer and keeps walking
      (`select_up_to_cap_per_year`, what the live S2 fallback ships). Also
      `density_selection`→`select_landmarks`, `model_budget`→`predicted_budget`,
      `DENSITY_CAP`→`PER_YEAR_CAP`, `is_anchor`→`is_worked_example`, and
      "re-anchoring"→choosing the **age origin**. Config keys deliberately
      untouched (`config.json` is gitignored — renaming them would mean a hand
      migration on every machine).
      **[docs/landmark-vocabulary.md](landmark-vocabulary.md) is new and
      canonical** — every term with a worked example, the three senses of
      "anchor" named apart, and an old→new table so this file's older entries
      stay readable (they keep the pre-v5.10.0 names on purpose: they are
      records of what shipped then). Everything else links there instead of
      restating, per the repo's one-definition rule. Every toy example in it was
      executed against the real functions rather than asserted.
      **Data contracts moved too** (CSV headers; the artifact's `density_cap` key
      → `per_year_cap`) — safe because retraining `cite_budget` from the
      committed corpus reproduced `cv_r2 = 0.6804741428173474` to all sixteen
      digits with identical coefficients, proving a header rewrite is equivalent
      to re-collecting, so no live API traffic was needed. `latest_gap`
      reproduced `tau=0.25`/`max_span=7` likewise and its artifact was left
      untouched.
      **Six bugs surfaced on the way**, the notable one written up in
      [bugs.md](bugs.md): two of the three research notebooks had been
      **un-executable since the src-layout migration** and nobody knew, because
      nothing in the gate runs a notebook; `research/latest_gap/README.md`
      documented the **rejected** quantile design (`q=0.85, max_span=9`) as if it
      were shipped, contradicting its own notebook *and* `bands.py`; and two test
      docstrings claimed the STOP rule was the live fallback's trim — backwards
      since v5.5.0, i.e. the exact confusion this whole change set out to kill,
      sitting in the tests.
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
- [x] **No-single-letter-identifiers rule, machine-enforced** *(v5.3.0)* —
      the v2.4.2 naming convention (every binding named for what it holds)
      had only `CLAUDE.md` keeping it true; now a **local pre-commit hook**
      enforces it. Ruff has no minimum-identifier-length rule (E741 only
      bans the ambiguous `l`/`I`/`O`), so **`bin/check_identifiers.py`**
      walks the AST itself and flags every single-character *binding* —
      assignments (incl. walrus), loop/comprehension targets, parameters,
      function/class names, `except`/`with`/import aliases,
      `global`/`nonlocal`, `match` captures, PEP 695 type params — with `_`
      allowed as the pure-discard idiom and attribute *reads* out of scope
      (react-force-graph's `node.x`, a paper's `_s` field aren't bindings we
      own). **Notebooks are covered too**: each `.ipynb` code cell is parsed
      individually and reported ruff-style (`file:cell N:line`; cells that
      aren't plain Python, e.g. magics, are skipped). The sweep that made it
      green caught stragglers in four test files and three research
      notebooks (`k`/`v` → `key`/`values`, `i` → `index`, `lambda *a, **kw`
      → `*args, **kwargs`) — including one in the days-old v5.1
      `test_search.py`, exactly the drift the hook exists to stop.
      Negative-tested: a deliberately bad file fails the run. *(Follow-through
      on the v2.4.2 sweep.)*
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
- [x] **Moved `ml_pipelines/` into `src/` and split `models/` per model**
      *(v4.10.1)* — the training pipelines moved from the repo root to
      `src/ml_pipelines/` — a second top-level package **alongside** `src/atlas/`,
      **not** bundled into the shipped app wheel (`packages = ["src/atlas"]`
      unchanged) and not force-typed by strict mypy, but importable everywhere
      because the editable install already puts `src/` on `sys.path`. The shared
      `ml_pipelines/models/` package **dissolved**: each model's committed
      artifact now lives **beside its own code** as `model.joblib` +
      `model.metadata.json` inside `cite_budget/` and `latest_gap/`, so a model's
      collector, trainer, corpus, README, and artifact sit together. The app's
      load paths (`services/graph/budget.py`, `bands.py`) and the trainers' write
      paths point at the new per-package location; `pyproject`'s `pythonpath`
      dropped the repo-root `"."` (everything's under `src/` now). The `models/`
      README was deleted, its "committed / regenerated-not-edited / loaded-
      defensively / version-skew" notes folded into each package README. Verified
      the app loads both models from the new paths and the full gate is green.
      *(From the `todos.md` inbox, 2026-07-10.)*
- [x] **~~Iterative (multi-round) landmark mining to beat recency bias~~ —
      RETIRED** *(v4.0.0)* — this was an idea to loop S2 reference-list mining to
      fill the sparse early-landmark band. The **OpenAlex hybrid** (shipped)
      recovers that band directly with a sorted `cites:` query — no mining, no
      verification, no loop — and the whole S2 mining apparatus it built on was
      deleted. Kept only as a tombstone; the live fallback path is plain deep
      paging.
- [x] **Tie `docs/citation-coverage.md` to its research notebook** — the
      citation-coverage write-up (`docs/citation-coverage.md`) and the experiment
      that backs it (`research/citation_coverage/analyze.ipynb` + its README) live
      apart and can drift. Cross-link them: the doc should point at the notebook as
      the source of its numbers/plots, and the notebook/README should point back at
      the doc — the same doc↔notebook pairing `cite_budget` and `latest_gap`
      already have (each `analyze.ipynb` is referenced from its ship note). *(From
      the `todos.md` inbox, 2026-07-13.)*

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
