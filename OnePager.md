# Atlas — One-Pager

> **Status:** v5.7.0 · living document · The core loop has shipped: the
> provider-selectable citation graph (Semantic Scholar or OpenAlex, with an
> optional offline S2 citations corpus for honest all-history landmarks), the
> AI teacher (four relation-scoped lectures + an agentic researcher with
> graph- and library-reach), the local semantic library, and saved sessions &
> workspaces.
>
> This file holds the product vision and the working roadmap — the **Backlog**
> below is the open work. The full shipped history (every item's story +
> version tag) lives in [docs/history.md](docs/history.md); the notable-bugs
> log in [docs/bugs.md](docs/bugs.md); the per-version chronology in git tags.
> Keep all three current as phases ship.

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

We **leave the storage to the ecosystem** (Semantic Scholar / OpenAlex / arXiv)
and connect dynamically — no mandatory local corpus, just a thin cache of the AI
artifacts we generate. (One deliberate exception since v5.4.0: an **optional**
offline copy of S2's bulk citation data, for the all-history landmark rankings
the live API can't serve.)

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

- **Academic graph:** two interchangeable providers, chosen per graph in the
  header — [Semantic Scholar](https://api.semanticscholar.org/api-docs/)
  (arXiv-native ids, SPECTER2 embeddings, `tldr` summaries; ~1 req/sec on the
  free key) and [OpenAlex](https://docs.openalex.org/) (server-sorted `cites:`
  queries — true top-cited landmarks). See
  [docs/citation-coverage.md](docs/citation-coverage.md) for each one's honest
  limits.
- **Offline S2 citations corpus (optional):** the bulk Datasets releases
  (papers + 2.4B citation edges) ingested via DuckDB → Parquet — citations
  hash-partitioned, papers clustered by `corpusid`, citer queries two-phase
  (`integrations/semantic_scholar/corpus/`, `atlas corpus` CLI; hundreds of GB,
  on its own drive outside the repo). Serves the all-history landmark rankings
  the live S2 endpoint can't; builds fall back to the live path automatically.
- **Seed discovery:** provider-native paper search (S2 relevance search /
  OpenAlex `search=`) with LLM query expansion, served cache-first from local
  snapshots.
- **Graph renderer:** [`react-force-graph-2d`](https://github.com/vasturiano/react-force-graph)
  (canvas force-directed with custom node painting; Force ↔ Timeline layouts).
  Sigma.js + graphology remains the fallback if we ever need very large graphs.
- **AI teacher:** a **PydanticAI agent crew** (query_analyst / librarian /
  lecturer / researcher behind a deterministic orchestrator) on the Anthropic
  API, streaming end-to-end over SSE.
- **Local library (bring-your-own sources):** PDFs/URLs chunked and embedded
  **locally** (sentence-transformers + sqlite-vec, hybrid FTS5+vector
  retrieval via RRF) — copyrighted books never leave the machine.
- **Audio (roadmap):** [Podcastfy](https://github.com/souzatharsis/podcastfy)
  (Python lib) + Edge TTS (free) / ElevenLabs (optional).
- **Polished media (roadmap):** [AutoContent API](https://autocontentapi.com/)
  (optional, behind a flag).
- **Storage:** SQLite in `data/` for the day-TTL cache, saved sessions, and
  the library index — plus the optional Parquet corpus above. All gitignored.

---

## Backlog — not yet shipped

> Open work only, grouped by theme. When an item ships, its entry moves — full
> story, version tag and all — into [docs/history.md](docs/history.md)'s
> matching theme section, so this list stays the honest to-do surface. New
> ideas arrive through the `todos.md` inbox and get filed here.

### Teacher & agent reach

- [ ] **Say whether the researcher may answer from its own knowledge — right now
      the prompt leans "no"** — the ask was to confirm the researcher blends its
      own LLM knowledge with the papers. It isn't *forbidden* (the result's `cited`
      list is explicitly allowed to be empty), but nothing invites it and the
      wording pushes the other way: `SYSTEM_PROMPT` opens *"Answer from real
      content: read the papers you draw on"*, and the one escape hatch it names —
      *"pull in outside work"* — is defined as `expand_node`/`search_papers`, i.e.
      **more papers**, not recall. A model reading that will reasonably conclude
      everything must be grounded in a fetched paper. So the honest answer to "is
      this already the case?" is *probably not, and by accident*.
      Decide what we actually want, then say it explicitly. It's a real design
      question, not just wording: background a paper *assumes* (what a Bellman
      equation is, why on-policy vs off-policy matters) is exactly what a student
      needs and exactly what no cited paper will state. The knobs: does recall get
      used freely, only to bridge gaps, or only when tools come up empty? How is it
      **attributed** — `cited: []` reads as "ungrounded" today, and the frontend's
      citation chips have nothing to point at, so the UI may need a way to show
      "this part is background, not from a paper". And the guard has to be that
      recall never quietly substitutes for reading a paper we *have*. *(From the
      `todos.md` inbox, 2026-07-16.)*
- [ ] **Reconcile when the researcher should search vs. expand** — the agent has
      two "reach beyond the graph" tools with fuzzy boundaries: `expand_node`
      (a lineage hop — references/citations/similar of a paper *on* the graph) and
      `search_papers` (free-text, off-graph). Their prompt guidance overlaps, so
      the model sometimes searches when a hop would be tighter (or vice versa),
      wasting budget and pulling noisier nodes. Sharpen the tool descriptions /
      skill prompt on the decision rule (expand = "trace a known paper's
      neighbors"; search = "reach recent/topical work no hop can"), and consider a
      cheap heuristic nudge. *(From the `todos.md` inbox, 2026-07-14.)*
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
      **agent-reliability** item (shipped side: `docs/history.md`) — the model already skips `show_figure`
      even when asked, so "show more often, unprompted" needs the tool-call
      compliance to be solid first (stronger `AGENT_MODEL` / sub-agent
      decomposition). *(From the `todos.md` inbox, 2026-07-07.)*
- [ ] **Figures from uploaded PDFs in answers** — extend the v1.20.0 figures
      feature to the user's **own library**: pull images out of an ingested PDF
      (via `pymupdf`, which we already use for text) and let the agent surface a
      relevant one when it cites a source passage — the library analogue of
      `show_figure`, which today only covers arXiv papers (ar5iv). Needs page →
      image extraction at ingest (or on demand), a way to reference an image from
      a retrieved passage, and a `show_source_figure`-style tool + `figure` event
      reusing the existing answer-figure rendering. *(From the `todos.md` inbox,
      2026-07-03.)*
- [ ] **Keep "frontier" out of the "landmark papers since" lecture** — the
      evolution lecture ("The landmark papers since", narrating the landmark
      citers) sometimes ends on a beat whose **title contains the word
      "frontier"**, which is usually wrong for this mode and reads as a spillover
      from the separate **"The current frontier"** lecture (the `latest` relation)
      where that vocabulary belongs. Fix the lecturer's **EVOLUTION mode-intent**
      so the closing beat doesn't reach for "frontier" language — this lecture is
      about the giants that built on the seed, not the present frontier. *(From
      the `todos.md` inbox, 2026-07-11.)*
- [ ] **Should display filters scope the agents? Researcher yes, lecturer maybe
      not** — today filtering the graph (relation chips, year / citation sliders)
      narrows what **both** the researcher and the lecturer are grounded in:
      grounding is `(selected ∩ visible) ∪ discoveries` (v4.13.0), both
      `streamAsk` and `streamLecture` send `nodes: groundingNodes`, and the v4.9.0
      caption tells the user "filtering the graph scopes the lecture."
      Reconsider whether that's right **per agent**. A **researcher** answering a
      question probably *should* respect the visible/filtered set — the user
      narrowed the map on purpose. But a **lecture** is a complete story over its
      relation (`_story_nodes`); hiding a few nodes to declutter the *view*
      shouldn't silently drop them from the *narration*. Likely split: the
      lecturer narrates its full relation regardless of display filters, while the
      researcher stays scoped to what's shown. *(From the `todos.md` inbox,
      2026-07-13.)*


- [ ] **OCR for scanned PDFs in the library** — image-only PDFs are rejected at
      ingest today; OCR them so they ingest and retrieve like any other source.
      *(Deferred — needs a system Tesseract dep, fiddly on Windows. Moved out of
      the shipped Phase 3d polish list, 2026-07-16.)*

### Citations & graph data

- [ ] **Budget-cap the Similar nodes with a trained model** *(mooted — Similar was
      dropped from the graph in v5.0.0; keep only if a future ticket re-adds it)* —
      the *Similar*
      relation ships a flat `similar_limit` count, the same one-size problem the
      landmark budget solved for citations (v4.5.0). Give it its own budget
      model: cap how many SPECTER2 neighbors to show per seed, trained the same
      way as `cite_budget` (a new `ml_pipelines/<study>/` producing a loadable
      artifact the app calls at serve time, degrading gracefully). Decide the
      right label/signal for "how many similar papers are worth showing" (density
      of similarity scores? a drop-off / knee in the ranked similarity? seed
      features?) during the study. Mirrors the `cite_budget` / `latest_gap`
      pattern. *(From the `todos.md` inbox, 2026-07-10.)*
- [ ] **The live path can only see the recent sliver — the fix is the corpus, not
      a better estimator** — *(the residue of the live-path age-origin ticket,
      which `live_pool_validation` answered on 2026-07-17: see
      [docs/history.md](docs/history.md). The design's steps 2 and 4 are dead; this
      is what its measurements left behind.)* The study put a number on how little
      the live S2 fallback can see: across 18 truncated seeds the full-history
      landmark budget is a median **1.8×** the one computable from the reachable
      pool, and the tail is savage — VMD **12 vs 166** (13.8×), KEGG 13 vs 131,
      Random Forests 15 vs 114. *Attention Is All You Need*'s newest 9,000 citers
      **all fall in one year**, so the live path can see no history of it at all.
      Nothing on the live path fixes this: it isn't an estimation error, it's
      missing data, and the exactly-computed answer is exact about a sliver. The
      `select_up_to_cap_per_year` band is the honest response (it ships what the
      window holds without implying the window is the history), and the real repair
      is the **offline corpus**, already built. So this is less a ticket than a
      standing reason not to invest further in live-path landmark sizing — and an
      argument for surfacing provenance in the UI, since the same seed can
      legitimately show a 14×-different landmark band depending on the data source.
      *(Patrick's design, 2026-07-16; measured and resolved 2026-07-17.)*
- [ ] **Spike: is the SKIP rule what we actually want?** — Patrick's ask
      (2026-07-17), from the conversation that retired the budget model. Since
      v5.13.0 SKIP serves exactly one situation: a **truncated** live pool — a
      hyper-cited seed, on a machine with no corpus. Everything else prefixes by
      the STOP rule. Questions for the spike, against real seeds: (1) SKIP
      guarantees up to `PER_YEAR_CAP` from *every* reachable year, so a thin year
      ships its 40-citation best beside a blockbuster year's 13,000-citation
      13th-best — is that a landmark band or padding? (2) The truncated pool's
      "landmarks" are already only "most-cited of the newest 9k" —
      would an honest **UI label** (provenance: "recent most-cited", not "Field
      Landmarks") matter more than the selection rule? (3) Is there a defensible
      middle — e.g. SKIP with a citation floor, or a shorter band span — or
      should the truncated path simply mirror the complete path's shape and
      accept the hole the 29-vs-84 measurement documented?
      **The success criterion (Patrick, 2026-07-17):** whatever rule the
      truncated pool ends up with should land **as close as possible to what the
      STOP rule would ship if the seed's full citation history were reachable**
      — full-history STOP is the ground truth, and SKIP-vs-alternatives is an
      approximation contest, not a taste question. That makes the spike
      *measurable* with machinery we already have: `live_pool_validation`
      simulates the exact truncated pool from the offline corpus, so each
      candidate rule can be scored against the full-history STOP band (overlap
      on the reachable intersection, plus count agreement) across the 58-seed
      corpus. A candidate can't ship what the ceiling hides, so the honest
      ceiling on any rule's score is how much of the true band is reachable at
      all — the study's median 1.8× budget gap says that ceiling is often low,
      which feeds question (2): where no rule can score well, provenance
      labelling is doing the real work. Analysis only; no code until the spike
      reports. *(Filed 2026-07-17.)*
- [ ] **Investigate forward references — references S2/OpenAlex date *after*
      the seed's publication** — both providers sometimes list a reference (a
      paper the seed *cites*) with a publication date later than the seed's
      own, which should be impossible and currently just renders where the date
      says (right of the seed on the timeline — an ancestor drawn in the
      future). Likely upstream dating quirks — revised/journal versions dated
      over the preprint the seed actually cited, or plain misdates — but
      investigate per provider before deciding: how common, whose date is wrong
      (the seed's or the reference's), and whether the graph should clamp,
      flag, or trust. If it's genuinely upstream, the finding belongs in
      `docs/bugs.md`'s Upstream half, justifying whatever guard ships. *(From
      the `todos.md` inbox, 2026-07-17.)*
- [ ] **Reevaluate how Latest Publications distribute across their bands — the
      spread should read more uniform, without a recency-bias pattern** — the
      per-year bands were built precisely so no single year dominates, but the
      on-screen result still shows a recency-leaning density Patrick wants
      flattened: each band ships its top `latest_per_year` by citations, and
      how *full* each year's band actually comes back varies enough that the
      frontier can still pile toward the newest years. Look at the shipped
      band-size distribution across real seeds first (all three implementations
      share the shape now — OpenAlex's per-year queries, the corpus's windowed
      query, the live complete-pool bands — so one fix should land in all
      three), then decide whether the answer is a per-band cap tweak, a
      different within-band ranking, or something like sampling toward
      uniformity. *(From the `todos.md` inbox, 2026-07-17.)*
- [ ] **`corpus activate` only checks papers — it will happily activate a corpus
      with no citation edges** — the guard is
      `if not paths.parquet_dataset("papers").exists(): raise`. It never looks at
      citations, and `ingest_release` does papers first (rebuilding the arXiv index
      as it goes), so a release can have a *complete* seed index and ~0% of its
      edges. Then `corpus.citation_relations` resolves the seed, finds few or no
      edges, and returns `([], …)` — a valid tuple, **not** `None` — so `build.py`
      prefers the corpus and ships a graph whose Field Landmarks are a random
      sample of whichever shards happen to be done, labelled *"drawn from the
      offline citations corpus — the full citation history"*. Confirmed live on
      2026-07-15: with papers at 60/60 and citations at 2/390, DQN resolved and
      `citation_relations` returned **(60 landmarks, 0 latest)**. The empty case
      would at least announce itself; this one looks plausible and claims the
      strongest provenance we have. Two halves to fix: **(a)** `activate` should
      verify citations too (and the same hole is in `active_source()`, which only
      checks `parquet_dataset("papers").exists()`); **(b)** a resolved-but-edgeless
      seed should arguably fall back to live rather than ship an empty relation —
      needs a rule that can tell "no edges ingested" from "genuinely uncited".
      Related: the module docstring's "the app never queries a half-built corpus"
      only holds for a release that isn't active *yet* — re-ingesting an already-
      active one walks straight through it (documented in `corpus/README.md`;
      the workaround is to move `CURRENT` aside first). *(Found while re-ingesting
      the active release, 2026-07-15.)*
- [ ] **Even Latest-Publications spread via citation velocity** — the
      stratified/per-year band approach has been tried several times and the
      spread still isn't even. Revisit **citation velocity** as the ranking
      instead: balance citation count against recency, which are inversely
      proportional (newer papers haven't had time to accumulate citations), so
      neither extreme dominates the selection. The shelved WIP's
      **`_velocity` helper — `citation_count / (age + 1)`** (`stash@{0}`, see
      the mega-papers phase notes in `docs/history.md`) is the starting formula; may need tuning so
      the balance point lands where the spread looks even. **Related:** the
      live-path age-origin ticket above bands Latest per year — velocity
      would slot in as the *within-band* ranking. *(Patrick's brainstorm,
      2026-07-10.)*
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
- [ ] **Distinguish survey/review papers from primary-contribution papers** — a
      graph today treats a review or survey the same as a paper that introduces a
      new idea, but they play very different roles in a field's story (a survey
      *summarizes* the field; an innovation *advances* it). Classify the two per
      node so the app can act on the difference: a **badge / distinct styling** in
      the detail panel or on the node, and — more usefully — letting the
      lecturer/researcher **weight primary contributions over surveys** when
      narrating "how we got here." Decide the signal during the work: title
      keywords ("survey" / "review" / "a comprehensive …"), the citations-vs-
      references shape (surveys cite widely, get cited broadly, rarely introduce
      method), or S2/OpenAlex type metadata — heuristic first, a small classifier
      only if it needs one. *(From the `todos.md` inbox, 2026-07-13.)*
- [ ] **SPIKE: SPECTER2 semantic retrieval as a landmark source (not just
      Similar)** — a spike to investigate, **not yet a build decision**. Patrick's
      idea: use S2's SPECTER2 recommendations to surface heavily-cited **landmark**
      papers, as a workaround for the citation-coverage limits documented in
      [`docs/citation-coverage.md`](docs/citation-coverage.md). *(Discussed
      2026-07-13; picking up next session — full reasoning below so we don't
      re-derive it.)*

  **Why it's more than "reuse Similar."** It dodges **both** of our measured
  citation failure modes at once:
  - **S2's 10k ceiling + no sort** — `/recommendations/forpaper` is a *different
    retrieval mechanism* (SPECTER2 nearest-neighbors, up to 500, returned
    directly), so it has no offset-paging problem: a heavy hitter buried past the
    `_MAX_OFFSET`≈10k newest-first window is reachable by embedding when it isn't
    by citation paging (`integrations/semantic_scholar/traversal.py`).
  - **OpenAlex's missing ML citation edges** — the *real* open problem in the
    coverage doc (§3–4): OA under-extracts arXiv-preprint→preprint citations, so
    its ML landmark set is a different, lower-quality set (3/15 top-citer overlap
    on QMIX/MADDPG). **SPECTER2 embeddings don't need the citation edge to
    exist**, and they're computed over exactly the preprint-native corpus S2 is
    strong on — so semantic retrieval sidesteps the extraction gap entirely.

  **Free-lunch mechanic.** Recommendations already return `citationCount` (same
  `NEIGHBOR_FIELDS` we rank references/citations by), so **re-ranking the 500
  neighbors by citation count is zero extra calls** — the exact over-fetch-then-
  rank pattern `_neighbors` already uses. One call, no deep paging, no 429
  backoff, no OA dependency. Cheap regardless of the rest.

  **Motivating observation (Patrick).** Citation-ranked landmarks for a mega-seed
  drag in off-field applications — e.g. *Attention Is All You Need* → a
  transformers-for-protein-structure paper (AlphaFold-ish), which is really an
  application of ML in biology, not core ML. Semantic neighbors would stay closer
  to the field.

  **Honest caveats — it changes the question, so probably a complementary
  relation, not a replacement:**
  - **Loses directionality.** A citation landmark is a *descendant* (built on the
    seed); a SPECTER neighbor can be an ancestor (reference), descendant (citer),
    **or a sibling** (contemporaneous, no edge). So "semantic landmark" = "papers
    *near* this one", not "giants that *built on* this one." Fine for a
    Connected-Papers-style map (CP is co-citation/coupling-based, not direct-edge),
    but it **breaks the lecturer's timeline** ("how we got here" / "what evolved
    since" both depend on seed↔node time direction). Fixable by splitting the
    semantic set on publication-year-vs-seed, but not free.
  - **On-topic isn't unambiguously better.** *"Attention enabled AlphaFold"* is
    one of the most important things that paper did — cross-field impact is a
    **feature** of the citation graph, not noise. Filtering it out gives a cleaner
    field map but drops real impact signal.
  - **500-cap + era bias.** We get the 500 *nearest* then re-rank; a topically
    further-out landmark falls outside the pool (good = the AlphaFold exclusion;
    bad = can also drop a legit landmark). And embedding similarity clusters
    same-subfield/same-era, so it may be *worse* at surfacing deep-history
    foundational ancestors than the recent frontier.

  **Two plausible shapes (if the spike pays off):** **(A)** a parallel "related
  landmarks" relation — 500 SPECTER neighbors re-ranked by citations, top-N, shown
  distinctly (optionally year-split onto the timeline); **(B)** a *supplement* that
  unions the semantic top-N into the OpenAlex landmark set (deduped) specifically
  on the arXiv-native ML seeds where §4 showed OA is weak. (Note: this is a
  deliberate spike *despite* the v5.0.0 removal of the Similar relation (`docs/history.md`) — it
  reuses the recommendations API, which that ticket keeps wired for the
  researcher anyway.)

  **The experiment (extends `research/citation_coverage/`).** Same seeds
  (Attention, GPT-3, QMIX, DQN + a physics control like Hawking): pull SPECTER
  neighbors re-ranked by citations, then measure against (a) our shipped OA
  landmark set, (b) S2's true top-cited citers where pullable (the <9k-citer RL
  papers), and — **the key metric** — how many semantic neighbors are *verifiable
  citers OA missed* (resolve each id, check the edge). That last number is what
  distinguishes genuine landmark **recovery** from just a prettier Similar
  relation. Hits live S2 + OA, so keep it to a handful of seeds (shared IP).


### UI & rendering polish

- [ ] **One "Abstract" section in the detail panel, with a TL;DR toggle** — today
      the panel shows the abstract and S2's `tldr` as *separate sections*, and an
      OpenAlex paper has no TL;DR at all (its detail hydration returns no `tldr`,
      so the panel just shows the abstract — see `docs/bugs.md` on OA hydration).
      Make it **one section titled ABSTRACT**, defaulting to the abstract on both
      providers, with an in-section toggle to a TL;DR view — **no second section**.
      - **S2** has `tldr` already (`DETAIL_FIELDS` requests it, `nodes.node` pulls
        `tldr.text`); the toggle just swaps what the one section renders.
      - **OpenAlex** has no equivalent, so **we generate one**: a small Claude
        agent that summarises the paper in a short paragraph — the old "summarize"
        button from the digest era, now a per-paper TL;DR. That means a new agent
        package (`agents/<name>/`, its own config entry + README, per the agents
        convention), an endpoint, and a decision on **caching** (per-paper, in
        `data/`?) so re-opening a node doesn't re-bill. Note the abstract is
        already hydrated lazily on node-open, so the summary should ride that same
        request rather than adding a second round trip.
      - The toggle's *form* is open — a button, a segmented control, a link. Wants
        a look at the panel before deciding; the constraint is that it lives inside
        the section, not beside it. *(From the `todos.md` inbox, 2026-07-16.)*
- [ ] **A settings modal — and let the user choose corpus vs live citations** —
      there's nowhere in the UI to configure anything; the corpus is a `config.json`
      edit plus a server restart. Add a **settings button (top-right)** opening a
      modal that can at least (a) point at the citations corpus
      (`storage.s2.parquet` — and `.raw` if downloads are wanted) and (b) **toggle
      the corpus off**, falling back to the live S2 citation endpoint. The fallback
      already exists and is automatic when the corpus can't serve a seed; this makes
      it a *choice* — useful when the corpus is stale, mid-ingest, or suspect.
      Design questions worth settling first: config today is **load-once at import**
      (`config.py`'s `config = load_settings()`), so a UI that writes `config.json`
      either needs a reload path or an honest "restart required" — and a
      *per-request* provider/source override (like `?provider=`) may be the cleaner
      model than mutating global config. The graph cache is keyed by
      `(provider, seed)` and **not** by citation source, so a toggle must bust or
      key around it or the old snapshot just comes back. *(From the `todos.md`
      inbox, 2026-07-16.)* **Scope grew 2026-07-17:** the modal is also the
      landing place for whichever `config.json` knobs deserve to live **with the
      user** rather than in a file nobody edits — the second half of the
      constants-audit ticket (Enhancements & tech debt) feeds it a candidate
      list. Placement: the settings button sits top-right **beside the
      help/tutorials button**.
- [ ] **A query-analyst toggle in the search bar — and rename "Filters"** — the
      search surface gives no way to skip the query-analyst agent; sometimes you
      want the raw keyword search without the LLM expansion round-trip (or its
      spend). Fold it into the existing dropdown as a checkbox, which means the
      "Filters" label no longer fits once it holds a behavior switch. Patrick
      floated **"Options"** and asked for better names — candidates:
      **"Search options"** (says where it applies), plain **"Options"**, or
      keeping "Filters" and putting the toggle elsewhere (a small sparkle icon
      button beside the search box, the pattern other AI-search UIs use for
      "AI on/off"). Decide the name against the mock, not in the ticket. *(From
      the `todos.md` inbox, 2026-07-17.)*

- [ ] **One fast "unhighlight everything" action** — clearing what's lit on the
      graph is currently piecemeal: the hand-picked selection has its own Clear,
      and a lit lecture beat / chat answer / inline `[n]` ref clears by clicking
      it again. Add a single fast gesture (an **Esc** key and/or one visible
      Clear) that drops **any** active highlight or selection at once — regardless
      of whether it came from a marquee/drag pick or from clicking a
      bubble/chapter/ref in the lecturer/researcher. Unifies `highlightSet` +
      `nodeSelectionCleared` + the panel's active-beat/chat/ref state behind one
      reset. *(From the `todos.md` inbox, 2026-07-14.)*
- [ ] **Thicker dashed ring for "Discovered by teacher" nodes** — the dashed
      "discovered" ring on agent-pulled nodes is hard to see; thicken it (and/or
      up the contrast) so a discovery reads at a glance. *(From the `todos.md`
      inbox, 2026-07-14.)*
- [ ] **Cleaner layout for expanded nodes** — nodes/edges the researcher pulls in
      via `expand_node` land right on top of the seed's own edges and nodes, so a
      dense neighborhood turns to spaghetti around the seed. Give discoveries more
      breathing room — a wider initial scatter, a local repel/anchor tweak in
      `useDiscovery`, or a post-merge settle — so the new cluster reads as
      distinct from the existing graph. *(From the `todos.md` inbox, 2026-07-14.)*
- [ ] **A filter chip for teacher-discovered nodes and search nodes** — discovered papers
      (dashed ring, from `expand_node`/`search_papers`) and search papers have no filter control;
      add a chip (like the relation chips) to show/hide the whole discovered set
      at once, so a busy post-Q&A graph can collapse back to the built
      neighborhood. *(From the `todos.md` inbox, 2026-07-14.)*
- [ ] **Rework the `search` node treatment (overlap → grounded, dual-relation
      detail)** — the parked "do we even want a distinct pink `search` relation?"
      question, shaped: when a topic-search hit is **also** a citation/reference
      already reachable on the graph, it shouldn't render as an **isolated pink
      node** — it should merge onto the green/blue node **with its edge**, and the
      detail panel should show **both** relations (e.g. "Search + Reference").
      Only genuinely off-graph hits stay pink-and-floating. Needs the search
      discovery to check for an existing edge/overlap before emitting an
      edge-less node, plus multi-relation detail badges (the panel already dedupes
      badges by label). *(From the `todos.md` inbox, 2026-07-14; relates to the
      v5.2.0 edge-less-node filter fix.)*
- [ ] **Source-scope picker doesn't appear until a page refresh (+ note it above
      the ask bar)** — uploading sources through the 📚 Sources drawer doesn't make
      the assistant panel's **source-scope picker** show up until you manually
      reload the page. Root cause: `Teacher.tsx` fetches the library once, in a
      mount-only `useEffect(… , [])`, into local `libraryItems` state; an upload
      elsewhere never refreshes it, so the picker (shown at >1 source) stays
      hidden. The lecture-scope picker doesn't have this bug because it derives
      from the store (`transcript.lectures`), which updates live — the fix should
      make the source list react the same way: lift it into the store (or a shared
      context) that the Sources drawer updates on upload/delete, or re-fetch when
      the drawer closes, so the picker appears immediately. **While here:** also
      surface the selected sources in the **one-line note above the ask bar**
      (like the lectures note added in v4.12.0) — space is tight, so likely a
      combined line ("Answers draw on N lectures · M sources") rather than two.
      *(Patrick's report, 2026-07-11.)*
- [ ] **Hide dateless papers in Timeline, keep them in Force** — a paper with no
      publication date has no honest position on a time axis. Today the Timeline
      layout parks a dateless node at the **seed's own x** (`nodeTimelineX` in
      `useTimeline.ts`, the v2.3.1 fix) so it doesn't fly to the far edge — but
      it still shows, misleadingly sitting at the seed's year. Instead: **omit
      dateless nodes from the Timeline view entirely** (and their edges), while
      **keeping them in the Force view**, where position is force-driven, not
      time-driven, so they belong. A layout-scoped visibility filter (Timeline
      drops `year == null && pub_date == null` nodes; Force shows everything),
      kept in step with the paper-count readout so it reflects what's shown.
      *(From the `todos.md` inbox, 2026-07-11.)*
- [ ] **Release should re-condense a scattered force layout on demand** — on a
      big graph the force nodes drift apart and there's no way to pull them back
      together without changing the view. The **Release** button (graph controls)
      only un-pins pinned nodes and is **disabled when nothing is pinned**
      (`pinnedCount === 0`), so it can't help. Today's only workaround is toggling
      a relation filter chip, which reheats the simulation as a side effect and
      condenses the layout. Give the user a real control: either make **Release**
      also **reheat the simulation** (`d3ReheatSimulation` on the ForceGraph2D
      ref) so it re-settles the nodes even with none pinned, or add a dedicated
      **"Re-layout"/"Recenter"** action beside Release/Fit. *(From the `todos.md`
      inbox, 2026-07-11.)*
- [ ] **Group graph nodes by relation type in the Force layout** — the force
      layout currently mingles every relation into one undifferentiated cloud;
      nodes should **cluster into visual groups by their relation to the seed**
      (references / Field Landmarks / Latest Publications / Similar) so the
      neighborhood reads at a glance. Likely a per-relation grouping force (a
      cluster centroid per relation, or a radial/sector layout keyed on
      `link.type`) in the force-graph config; Timeline already separates by date,
      so this is the Force-layout counterpart. *(From the `todos.md` inbox,
      2026-07-10.)*
- [ ] **Lexical search over the nodes on screen** — a quick keyword box that finds
      a paper among the ones **currently on the graph** (matching titles/authors),
      distinct from the seed search that fetches new papers from S2. Purely
      **lexical and local** — no API call — filtering to or spotlighting the hits
      (reusing the `highlightIds` glow/dim machinery) so a specific paper is easy
      to pick out of a busy neighborhood. Separate from the pink `search`-relation
      researcher hits and from the seed-search surface entirely. *(From the
      `todos.md` inbox, 2026-07-13.)*



### Enhancements & tech debt

- [ ] **Delete the four dead per-relation count caps — the app should size itself**
      — `ref_limit`, `cite_limit`, `latest_limit` and `similar_limit` are all
      **`null` in the real `config.json`** and have been for a long time: the app
      already sizes every relation itself (the fitted `PER_YEAR_CAP` of 12 per
      publication year, `bands`' fitted `tau`/`max_span`, and
      `UNBOUNDED_LANDMARK_CAP` as the payload ceiling). Like `recs_pool` below,
      they're knobs nobody turns. Patrick's call (2026-07-17): sizing should be
      **automatic**, with a user-facing "show me more" setting later if wanted —
      not a config file nobody edits.
      **Now unblocked.** The blocker used to be that the two sizings disagreed
      about what an unset `cite_limit` *meant*: `predicted_budget` read it as
      `UNBOUNDED_LANDMARK_CAP` (500) while `select_landmarks` read it as infinity.
      You can't delete a field two code paths interpret differently. v5.11.0 made
      them agree, so the field can now go without changing behavior.
      **The work:** drop the four fields from `config.py` and
      `config.example.json`, delete the ceiling reads in `budget.py` /
      `build.py` / the traversals, and prune `docs/configuration.md`. **Migration:**
      `config.py` is `extra="forbid"`, so every existing `config.json` fails at
      startup until the keys are deleted — a hand-edit on both machines, and
      `config.json` is gitignored so it can't be done for them. Consider whether
      the session-start config-drift check in `CLAUDE.md` should also flag keys the
      template has *dropped*, not just ones it has added.
      **Worth deciding while in there:** `UNBOUNDED_LANDMARK_CAP = 500` becomes the
      *only* ceiling once `cite_limit` goes, and unlike `PER_YEAR_CAP = 12` it was
      never fitted — its docstring frames it as a paging pragmatic ("without paging
      a mega seed's entire citer list"). That's a defensible payload guard rather
      than a legibility rule, but it should be *named* as one, since "data-driven
      over magic numbers" is the house line. *(Patrick, 2026-07-17.)*
- [ ] **Audit every constant in `src/` for config-knob-worthiness — then decide
      which knobs belong in the UI instead** — a systematic pass over the
      module-level constants (`NBUCKETS`, `_RANK_POOL`, `_MAX_OFFSET`,
      `PER_YEAR_CAP`, `_LATEST_WINDOW_MONTHS`, `UNBOUNDED_LANDMARK_CAP`, the
      retrieval/chunking numbers, agent extras defaults, …) asking of each:
      should this be a `config.json` knob? The audit needs the lesson of the
      count-caps ticket above as its filter — that ticket exists because knobs
      nobody turns are *deletion* candidates, so "could be configurable" is not
      the bar; "someone would actually turn it, and turning it is safe" is.
      Fitted constants (`PER_YEAR_CAP`, `tau`/`max_span`) and API-reality
      constants (`_MAX_OFFSET` is what S2 serves, `NBUCKETS` is baked into the
      ingested corpus layout) probably stay code. **Part two, a separate pass
      once the knobs settle:** decide which config knobs graduate out of the
      file entirely and live **with the user** — the settings modal (UI &
      rendering polish ticket, which this feeds a candidate list; settings
      button top-right beside help/tutorials). End state worth aiming at: config
      holds operator concerns (paths, keys, ports), the modal holds user
      preferences, and code holds fitted or structural constants. *(From the
      `todos.md` inbox, 2026-07-17.)*
- [ ] **Gate the research notebooks — nothing executes them, so they rot
      silently** — two of the three (`research/cite_budget`, `research/latest_gap`)
      had been un-executable since the src-layout migration and nobody noticed,
      because no nox session runs a notebook (see `docs/bugs.md` → "Two of the
      three research notebooks had been un-executable for weeks"). `precommit`
      lints notebook *identifiers*, which makes them feel covered while their
      actual correctness is checked by no one; a committed output is a claim, and
      claims were going stale invisibly. **Proposal:** a `notebooks` nox session
      running `jupyter nbconvert --execute` over `research/*/analyze.ipynb`.
      **The design question that stops this being a one-liner:** all three
      currently read *committed* corpora and are offline and cheap (~seconds), so
      today it's free — but the gate must never become a thing that hits a live
      API or needs the corpus machine, and a future notebook might want either.
      So the session needs a rule for what's includable (offline, committed inputs
      only) and a way for a notebook to opt out, rather than globbing everything.
      Worth pairing with the fact that the pipelines' **collectors** have no test
      coverage at all for the same reason — they call live APIs. *(Found while
      renaming the budget vocabulary, 2026-07-16.)*
- [ ] **Drop the `recs_pool` config knob (hardcode `all-cs`)** — the S2
      *Similar* recommendations pool is a `Literal["all-cs", "recent"]` config
      option (`config.providers.s2.recs_pool`), but `config.py` and
      `docs/configuration.md` both say it **must stay `all-cs`** — `"recent"`
      returns nothing for older seeds, so no real graph ever wants it. Like the
      retired per-relation count caps, it's a dead knob: remove the config field
      and hardcode `from=all-cs` at the recommendations call site
      (`integrations/semantic_scholar`), deleting the now-moot "why it must stay
      all-cs" config/docs notes. Confirm nothing else reads it first. *(From the
      `todos.md` inbox, 2026-07-11.)*
- [ ] **Rename `digest.db` → `cache.db`** — the ephemeral graph-snapshot store
      is still named `digest.db`, a leftover from the retired daily-digest era;
      it's really the 1-day graph/artifact **cache** now. Rename the file (and
      the `storage.data_dir`-relative path + any `config`/docstring references,
      e.g. `storage/sessions.py`'s note contrasting it with `sessions.db`) so the
      name matches what it holds. A cosmetic rename — old `digest.db` files can be
      left to age out or deleted, since it's a regenerable cache. *(From the
      `todos.md` inbox, 2026-07-11.)*
- [ ] **Drop the retired per-relation count caps from config** — remove
      `graph.ref_limit`, `graph.cite_limit`, `graph.adaptive_cite_limit`,
      `graph.latest_limit`, and `graph.similar_limit` from `config.json` /
      `config.example.json` and the Pydantic `graph` config. Resolved plan (per
      Patrick, 2026-07-10):
  - **`cite_limit` + `adaptive_cite_limit`** → gone: the **computed STOP rule
    always determines the cite limit** (since v5.13.0 on every path — the model
    that used to predict it is retired) — no toggle, no config ceiling. The rule
    owns its own upper bound (`UNBOUNDED_LANDMARK_CAP` as the payload guard,
    `services/graph/budget.py`) rather than clamping to a config `cite_limit`.
  - **`ref_limit`** → gone: **show all references** (no cap).
  - **`latest_limit`** → gone: Latest Publications is already **banded by year**
    (`latest_band_years` × `latest_per_year`), so the flat cap is redundant.
  - **`similar_limit`** → **staged behind** the *Budget-cap the Similar nodes with
    a trained model* ticket (under Citations & graph data): that ticket replaces
    the flat `similar_limit` with a trained per-seed budget, so remove the config
    key as part of / after it, not before. *(From the `todos.md` inbox,
    2026-07-10.)*
- [ ] **Fold the retired predictor into `ml_pipelines` (or retire it fully)** —
      since v5.13.0 `budget.predicted_budget` / `load_model` / `MODEL_PATH` are
      app-side code (`services/graph/budget.py`) whose only callers are
      pipelines: `latest_gap/collect.py` (trims citer-year distributions the way
      v5.12-era builds did, so its committed corpus stays reproducible) and
      `live_pool_validation/collect.py` (both age-origin columns). That respects
      the dependency rule (pipelines import the app, never the reverse — the
      `compute_features` precedent), but "app code with no app callers" is worth
      resolving deliberately: either move the predictor + artifact loading into
      `ml_pipelines/cite_budget` (churns the `latest_gap` collector's provenance
      story; `compute_features`/the STOP label stay app-side — the label is the
      serving rule now), or decide the `latest_gap` corpus should be re-collected
      against the *computed* budget and delete the predictor outright. Blocked
      on neither; just don't do it silently — the model coming back (a future
      provider that genuinely can't compute) is the one reason to wait. Pairs
      with the count-caps ticket above (both are "what does the model's absence
      let us delete?"). *(Patrick, 2026-07-17, spotting the near-dead code in
      review.)*
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
- [ ] **Replace every string `Literal` type with an `Enum`** — the backend leans
      on string `Literal[...]` unions in ~8 modules (relation types, event kinds,
      lecture modes, config choices — `agents/events.py`, `services/graph/model.py`,
      `agents/traversal.py`, `researcher/tools.py`, and others; ~30 occurrences).
      Convert **all** of them to proper `Enum`s — likely `StrEnum` so the JSON/wire
      values stay exactly the strings they are today — for one named source of
      truth, exhaustiveness, and refactor safety instead of the same literals
      retyped across modules. A whole-codebase sweep, not a targeted one; keep the
      wire format identical so snapshots, saved sessions, and the SSE protocol are
      unaffected. *(From the `todos.md` inbox, 2026-07-13.)*

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

## Open questions & costs

- **Semantic Scholar rate limits** — real even with a key (~1 req/sec): the
  client throttles + backs off, graph snapshots cache for a day, and the
  offline citations corpus removes the deep-paging dependency entirely.
- **Citation coverage per provider** — which backend serves which seed
  honestly is measured and documented in
  [docs/citation-coverage.md](docs/citation-coverage.md) (OpenAlex
  under-extracts preprint→preprint edges; live S2 is recency-truncated; the
  corpus is S2's fix). Read it before touching citation-source logic.
- **AutoContent API** — ~€24/mo (1,000 credits: infographic 10, slide deck 30,
  video 50). Trial the cheap tier and judge quality by eye before committing
  (Phase 7).
- **ElevenLabs** — optional premium TTS; free tier ~10k credits/mo (Phase 6).
- **Paper figures for slides** (later phase) — evaluate ar5iv HTML vs. arXiv
  source tarball vs. `pdffigures2`/DeepFigures for pulling real diagrams; decide
  how to caption/attribute them. Deferred until the visuals/slides phase.
