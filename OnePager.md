# Atlas — One-Pager

> **Status:** v6.5.0 · living document · MIT-licensed. The core loop has
> shipped: the provider-selectable citation graph (Semantic Scholar or
> OpenAlex, with an optional offline S2 citations corpus for honest
> all-history landmarks), the AI teacher (four relation-scoped lectures + an
> agentic researcher with graph- and library-reach), the local semantic
> library, saved sessions & workspaces, and an in-app settings modal — with
> light/dark theming and per-request graph sizing (adaptive or user-tuned).
>
> This file holds the product vision and the working roadmap — the **Backlog**
> below is the open work. The full shipped history (every item's story +
> version tag) lives in [docs/history.md](docs/history.md); the notable-bugs
> log in [docs/bugs.md](docs/bugs.md); the per-version chronology in git tags.
> Keep all three current as phases ship.

---

## Vision

**Atlas** turns a research paper into an explorable *map* and puts an AI
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
- **AI teacher:** a **PydanticAI agent crew** (librarian /
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

- [ ] **Click a library citation to open the source at that page** — Part 2 of
      the citation ticket whose Part 1 shipped in **v6.6.0** (see
      [docs/history.md](docs/history.md)). Citations now *resolve*: the model
      writes `[S1, p.243]`, the server hands the frontend a real source id, and
      the reader sees *"(Reinforcement Learning: An Introduction, p.460)"*. What's
      missing is the click — it renders as quiet grey text, not a control.
      **The blocker is that there is no page viewer, which the original ticket
      wrongly assumed existed:** the only source-image route is
      `/api/sources/<id>/figure/<n>`, which serves one *mined manifest entry*,
      and nothing in the frontend displays an arbitrary page. Two halves:
      **(a) backend, small** — `pdf/floats.py`'s `render_float` already
      rasterizes a clipped page region via PyMuPDF, so a whole-page render is
      the same call without the clip; add `/api/sources/<id>/page/<n>`.
      **(b) frontend, a new surface** — decide how a page is shown (a lightbox
      like `FigCard`'s? a docked reader?), which is the real design work here.
      Then make `.source-ref` a button. Note the page-render path has no
      caption-anchoring dependency, so unlike figure mining it works on any
      PDF-backed source — but URL sources have no stored PDF and must degrade
      to nothing clickable. **Supersedes** the frontend prose-highlight bandaid,
      built and then removed 2026-07-24 — that highlight could never be
      clickable without the structured reference v6.6.0 added.
      *(From #2 of the 2026-07-24 front-end quick-wins pass.)*
- [ ] **The guard is gated on a field the model writes** — a known weakness in
      `_must_have_looked`, kept here because the guard itself is core: it only
      fires on an `answered` turn, and `kind` is self-reported, so labelling a
      real question `conversational` would skip the library unchallenged.
      **Never observed** — it was the first suspect when a v6.7.0 answer
      skipped the search, but the log said `kind=answered` and the real cause
      was elsewhere (`docs/bugs.md`). Narrowed pre-emptively in v6.7.1
      (`answered` is the prompt's default; any question on any subject
      qualifies). Watch with `grep 'answer kind=' data/atlas.log` — a
      `conversational` line on a turn that clearly asked something is the
      signal. If it ever does slip, the lever is a cheap pre-classifier
      deciding the kind before the researcher runs, so the answering model
      can't grant itself the exemption (`summarizer` is the pattern).
      Related gap, unbuilt: a user can say *"answer from your own knowledge,
      don't search"* and nothing expresses that — with a library in scope the
      guard would override an explicit instruction.
      *(Filed 2026-08-06; scope-trimmed 2026-08-08.)*
- [ ] **Reconcile when the researcher should search vs. expand** — the agent has
      two "reach beyond the graph" tools with fuzzy boundaries: `expand_node`
      (a lineage hop — references/citations/similar of a paper *on* the graph) and
      `search_papers` (free-text, off-graph). **Now three**, since v6.7.0 made
      `search_sources` (the user's own library) a first-class reach on every
      turn rather than a pre-answer retrieval — so the decision rule has to
      cover all three, and the library one is the only one with a hard rule
      already attached (it must run before a substantive answer).
      Their prompt guidance overlaps, so
      the model sometimes searches when a hop would be tighter (or vice versa),
      wasting budget and pulling noisier nodes. Sharpen the tool descriptions /
      skill prompt on the decision rule (expand = "trace a known paper's
      neighbors"; search = "reach recent/topical work no hop can"), and consider a
      cheap heuristic nudge. *(From the `todos.md` inbox, 2026-07-14.)*
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
- [ ] **"Render page region" fallback for uncaptioned inline diagrams** — the
      v5.28.0 figure miner is caption-anchored, so a diagram with no caption
      (Sutton & Barto's inline backup diagrams; pseudo-code "figures" in very
      old PDFs) has nothing to anchor on and correctly reports "not
      extractable" — the one honest gap left after the Sarsa(λ) fixes. A
      fallback could let the agent show such a diagram anyway by rendering a
      *page region* rather than a manifest entry: e.g. a
      `show_source_page(source_id, page)` tool (whole page, or the page's
      largest drawing neighborhood via the existing cluster machinery), traded
      against the risk of shipping half a page of body text as an "image".
      Needs a crop heuristic that doesn't reintroduce the mislabeling problem
      the caption echo just fixed — the tool result must say exactly what's
      being shown ("page 87 of X", not a figure designation). *(Filed
      2026-07-19, out of the v5.28.0 browser tests.)*
- [ ] **Investigate: no figures extractable from the Feynman Lectures Vol. 3** —
      the library figure miner comes up empty on *Quantum Mechanics* (Vol. 3),
      so the librarian can't show anything from it. Unknown yet whether this is
      the known caption-anchoring gap (the ticket above — a book whose figures
      are captioned in a form `CAPTION_RE` doesn't match, e.g. "Fig. 3–2" with
      an en-dash, or captions set as running text rather than their own block),
      a text-layer problem (the volume may be a scan, or have figures drawn as
      vector art the cluster machinery discards), or an ingest-side failure.
      **Start by looking, not fixing:** dump the mined manifest for the source
      and compare against the actual pages — if captions are present but
      unmatched it's a regex/anchor fix; if the page has no text layer it's the
      OCR question (deliberately dropped, 2026-07-16); if the drawings are
      filtered out it's the float-geometry constants. See
      [docs/pdf-mining.md](docs/pdf-mining.md) before touching
      `services/pdf` — the storage decisions there are settled.
      **Narrowed 2026-07-19 (browser round):** the v6.1.1 hyphen fix to
      `captions.split_label` did *not* help, and neither did re-uploading the
      volume — so it's neither a stale manifest nor (only) caption labelling.
      The chip now reports the honest failure ("Tried figure 1 on p.72 of
      the_feynman_lectures_vol_III_quantum_mechanics"), which means the miner
      is returning **no floats for that page at all** — the caption anchor
      never matched, or the page's drawings were filtered out before captions
      were considered. Next step is still to dump the manifest for the source
      and compare against the PDF; if the manifest is empty everywhere, the
      question is whether the volume has a text layer at all.
      *(From the `todos.md` inbox, 2026-07-19.)*
- [ ] **Images from HTML sources never reach the chat either** — the same
      user-visible symptom as the Feynman ticket above ("the assistant can't
      show me a picture from this source"), but a **different pipeline**, so
      don't assume one fix covers both: that one is PDF float-mining in
      `services/pdf`, this one is whatever the HTML ingest path does with
      `<img>`. Repro Patrick is using: the **Wikipedia "Black hole" article** —
      image-rich and public, so it makes a good fixture. **Questions to answer
      before designing anything:** does HTML ingest extract images at all, or
      only text? If it records them, where do they live — note
      [docs/pdf-mining.md](docs/pdf-mining.md) settles that images are
      *deliberately* never cached server-side for PDFs, and that reasoning may
      or may not carry to remote URLs we could simply hot-link. And can
      `show_source_figure` even address a non-PDF source, given it's
      page/manifest-shaped today? Start by ingesting the article and dumping
      what the source record actually holds — the same "look before fixing"
      discipline the Feynman ticket calls for. Also worth checking whether the
      honest-failure trace chip fires here, or whether it fails silently; the
      latter would be its own bug. *(From the `todos.md` inbox, 2026-08-09.)*
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
- [ ] **A precise "overlapping references/citations" skill for the researcher** —
      asking which references or citations the seed paper SHARES with an
      expanded paper kind-of works today, but the answer comes from the model
      eyeballing the graph and reads imprecise. Give it a real tool: a
      deterministic overlap computation (intersect the two papers' reference/
      citer sets server-side — the graph and the expansion data already hold
      both) exposed as a researcher skill, so the answer is exact set output
      rather than model recall. Probably wants the result grounded as
      highlightable node lists too. *(From the `todos.md` inbox, 2026-07-18.)*

### Citations & graph data

- [ ] **A real switch between the corpus and the live S2 API** — today the
      choice is **implicit, config-driven, and silently per-seed**. There is no
      flag: `corpus/source.py`'s `active_source()` (`:477-500`) hands back a
      `DuckDBCitationSource` only when `config.storage.s2_corpus` is set *and*
      the directory exists *and* `CURRENT` names a release *and* that release
      has papers Parquet — any gate failing returns `None` and
      `citation_relations` (`:573-578`) falls through to live. It then falls
      back **again, per build**, when the seed doesn't resolve to a corpus id,
      so two seeds in the same session can quietly come from different sources.
      `services/graph/build.py:178-194` picks corpus-first and stamps the
      outcome as `citation_source: "corpus" | "live"` on the `Graph`
      (`model.py:118`), which the UI surfaces **read-only** through
      `landmarkNote(provider, graph?.citation_source)`
      (`GraphExplorer.tsx:591`). So the app already *tells* you which source it
      used — it just gives you no way to *ask* for one.

      **Today's only control is a path, not a switch**: SettingsModal's
      "Citations corpus" text field (`:509-528`, hint "Empty = corpus off").
      Forcing a live comparison means blanking the field — and losing the path
      you'd have to retype to get back. That's the actual pain: A/B-ing corpus
      against live is a routine thing to want (the corpus can only ever be as
      fresh as its release, and the live endpoint has the newest citations),
      and it currently costs a settings round-trip in each direction.

      **The design question is scope**, and both precedents already exist. A
      **per-request** choice would mirror the S2/OpenAlex provider picker —
      a `?provider=`-style query param read in `routes/graph.py:67-77`, with
      `resolve_provider`'s degrade-to-default behaviour (`build.py:98-119`) as
      the model — and is the more useful shape for comparison, but it widens
      every graph/search/agent call site that already threads `provider`. A
      **config default** (`providers.s2.prefer_corpus`, say) is a much smaller
      change and enough if the goal is just "pin me to live for this session".
      Worth deciding *before* building, since the per-request version
      subsumes the other. Either way, keep the automatic fallback: a seed the
      corpus can't resolve must still build from live rather than fail.
      *(From the `todos.md` inbox, 2026-08-16.)*

- [ ] **Surveys as a first-class node kind** — a review/survey paper is a
      different animal from a primary result: it's the field's own overlook of
      a period, and right now it's an anonymous dot like everything else.
      Identify them, give them their **own node colour and filter chip**, and
      let the user **scope the researcher and lecturer to them** — "teach me
      this field from its surveys" is a genuinely different (and often better)
      first pass than the citation lineage.

      **The data is there and we simply don't ask for it**, which makes the
      first step small: S2 exposes `publicationTypes` (carrying `Review`) and
      OpenAlex a `type` field (`review`) — neither appears in
      `semantic_scholar/nodes.py`'s `NEIGHBOR_FIELDS` nor
      `openalex/nodes.py`'s `NEIGHBOR_SELECT`, so it's a field addition on both
      before anything else can be built. Worth checking coverage on a real
      graph first: if the flag is sparse or noisy, a title/abstract heuristic
      ("a survey of", "a review of", ": a survey") may have to back it up, and
      that changes the ticket's shape.

      **Then two halves.** *Rendering* — surveys aren't a graph *relation*
      (a paper is a survey regardless of how it reached the canvas), so this is
      an **overlay** on the existing relation colouring rather than a new
      relation, and the chip is a filter over a property, not over `rels`.
      That's a real difference from the sibling "filter chip for
      teacher-discovered and search nodes" ticket, which does filter `rels`.
      *Scoping* — the agents already accept a hand-picked node set
      (`selectedNodeIds` → `selectGroundingNodes`), so "only the surveys" could
      ride that existing seam rather than needing its own plumbing.
      *(From the `todos.md` inbox, 2026-08-14.)*

- [ ] **Replace the STOP/SKIP citation rules with a citation-threshold predicate**
      — the standing goal (Patrick, 2026-07-20). Rip out the STOP rule, the SKIP
      rule, truncated-vs-full-history, and adaptive-vs-non-adaptive, and replace
      all of them with a single **per-citer predicate** — something shaped like
      `is_landmark(citer) = citer.cited_by >= threshold(citer, seed)` — that reads
      one citer and never the pool, so it is order-free and provider-independent
      by construction. That collapses five behaviors to one, pushes the filter
      into the query (OpenAlex `cited_by_count:>N`, a corpus `WHERE`), and turns
      truncation into a caveat instead of a code path. Latest Publications becomes
      the complement; the sliders return as display-only trimming; `PER_YEAR_CAP`
      demotes from semantics to a default slider position; "Field Landmarks"
      becomes "Landmarks".

      **Restarting from scratch under the `research` process** (`.claude/skills/research`).
      A first fully-specified formulation
      (`citer.cited_by >= max(FLOOR, T[age] · S(seed))`, fit for a 20–40 landmark
      band) reached Phase 1 on the `citation-threshold` branch and was retired —
      but its **key finding must carry forward so we don't rediscover it the hard
      way:** a pool-independent predicate can *center* the landmark count but
      cannot *pin* it per seed. The required per-seed multiplier scatters ~1.9–2.5×
      around anything seed size predicts, while a 20–40 band is only ~1.65× wide →
      ~35% max in-band, an exhaustively-proven ceiling for that model family
      (independently reproduced). The lesson: a **count guarantee belongs in the
      display layer** (the sliders), not the predicate — the predicate owns the
      Landmark/Latest *split*, the sliders own *volume*. The `citation-threshold`
      branch survives with its fitted S2 corpus sample (1,502 seeds) for
      reference; fitting still runs on the **Windows** box (offline corpus),
      artifact travels back via git.
      *(Goal filed 2026-07-20; restarted 2026-07-23.)*
- [ ] ~~**Spike: is the SKIP rule what we actually want?**~~ — **superseded
      2026-07-20** by the threshold-predicate ticket above, which generalizes
      this spike's own option (3), "SKIP with a citation floor", into an
      age-adjusted, seed-scaled floor applied to every path. Kept for its
      success criterion, which any future design should still be measured
      against (see the citation-threshold ticket above, now restarting from
      scratch under the research process). Original text follows. — Patrick's ask
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
      **Scope grown (Patrick, 2026-07-19): the truncated path's *Latest* side
      too** — its rolling 12-month window should move in line with the
      adaptive Latest (tau-started per-year bands), even if that means the
      truncated path's landmarks end up a very small set. And **sequencing:
      do this after the settings modal ships.**
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
- [ ] **Search cache refresh override** — seed-search results are served from
      the whole-result cache (v2.0.0) with no way to bypass a stale entry; add
      a refresh/override button to the search surface, mirroring the graph's
      per-seed **Refresh** button (v2.5.0) that busts the snapshot cache.
      *(From the `todos.md` inbox, 2026-07-08.)*
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

  **The experiment.** Same seeds
  (Attention, GPT-3, QMIX, DQN + a physics control like Hawking): pull SPECTER
  neighbors re-ranked by citations, then measure against (a) our shipped OA
  landmark set, (b) S2's true top-cited citers where pullable (the <9k-citer RL
  papers), and — **the key metric** — how many semantic neighbors are *verifiable
  citers OA missed* (resolve each id, check the edge). That last number is what
  distinguishes genuine landmark **recovery** from just a prettier Similar
  relation. Hits live S2 + OA, so keep it to a handful of seeds (shared IP).

- [ ] **Refresh the corpus incrementally instead of re-downloading it** — a
      monthly S2 release is re-pulled and re-ingested whole: ~400 GB of
      shards, then the full ingest (citations bucketed into 1024 partitions,
      papers compacted with a global `ORDER BY corpusid` sort) — hours of
      disk on NVMe and, per the corpus README's own measurements, ~10.6h of
      ingest alone on a spinning disk. Almost none of that is new: month over
      month the citation graph *appends*. **The investigation first:** the
      Datasets API is believed to expose a diff between two releases
      (update/delete file lists per dataset) — confirm that against the live
      API before anything else, since `datasets.py` today only calls
      `/release/latest` and `/release/{id}/dataset/{name}`, and the whole
      ticket rests on it. *(From the `todos.md` inbox, 2026-08-16 — Patrick's
      "is that possible? worth investigating".)*

      **If diffs exist, the ingest layout decides how hard this is, and the
      two halves differ sharply.** *Citations* are hash-partitioned on
      `citedcorpusid`, so an update file's edges scatter across all 1024
      buckets — appending is cheap in principle (write new files into each
      `bucket=<N>/`) but must preserve the within-bucket sort that makes row
      groups prune, so it's an append-then-merge per touched bucket, not a
      plain copy. *Papers* are the harder half: they are **globally sorted**
      by `corpusid` for exactly the pruning reason the README measures, and
      updated rows land anywhere in the 0–290M id range, so a naive append
      destroys the clustering that made hydration ~30x faster. That points at
      a re-compaction of the affected clustered files (which the existing
      `_compacting/` + `MANIFEST.json` staging already knows how to commit
      safely), plus a rebuild of the arXiv index.
      **Two constraints not to lose:** deletes are real (S2 merges and
      retracts records), so "append-only" is the wrong mental model; and
      releases are currently *isolated* subtrees with `CURRENT` naming an
      ingested one — an in-place incremental update mutates the release the
      app is serving, which is precisely the half-built-state hole the README
      warns about. Decide whether an incremental release copies-then-updates
      (cheap on a filesystem with reflinks, expensive otherwise) or whether
      `CURRENT` has to move aside for the duration.

### UI & rendering polish

- [ ] **Cache indicators in search results: split "cached graph" from "cached
      search", and stop the badge outliving its cache** — the suspicion was
      right on both counts. The badge exists — it reads **"⚡ opens
      instantly"** (`search/useDirectSearch.ts:65`), not "instantly loads" —
      and it means exactly one thing: **a cached graph snapshot**, never a
      cached search. It's driven by `paper.has_graph` from the SSE `cached`
      frame (`useDirectSearch.ts:165`, `routes/search.py:233-238`), which
      `services/search/discovery.py:217-219` computes by scanning only
      `graph:v2:<provider>:` keys. Cached *searches* live under a separate
      `search:<provider>:…` prefix (`agents/traversal.py:166`) and feed **no
      indicator at all** — so the second half of the ask is new plumbing, not
      a relabel.

      **On expiry, the answer is "yes, but only at compute time."**
      `discovery.py:171` does gate the badge on `(now - created) <=
      config.graph.cache_ttl` (86400s), deliberately still letting expired
      snapshots supply *titles* — so the flag is honest when it's calculated.
      Three gaps make it dishonest afterwards:

      - **It's frozen into markdown and saved.** `instant` is computed once
        from the `cached` frame, re-applied at `useDirectSearch.ts:186`, and
        baked as plain text into the transcript answer, which is persisted
        with the session (`store/workspace.ts:269`). **Reopen a saved session
        days later and long-expired entries still promise "opens instantly."**
        Nothing re-evaluates it. This is the bug worth fixing first.
      - **Build shape is ignored.** `fresh_seeds` keys on the snapshot's
        `seed.id`/`arxiv_id` regardless of the key's `shape.cache_suffix()`
        (`discovery.py:168-175` vs `services/graph/build.py:374`), while the
        browser sends its own shape on every build (`api/graph.ts:149,188`).
        A snapshot cached under a *different* shape sets `has_graph=True` and
        the actual open is a cache miss — a false badge on a perfectly fresh
        cache.
      - **False negatives.** Scout-found papers never get the badge even when
        their graph is cached, and the whole pre-pass is skipped when a field
        filter is active (`routes/search.py:232`).

      **The data model doesn't distinguish the two kinds**, which is why this
      is more than a label: `storage/cache.py:32-38` is one table of
      `key, value, created_at` with no kind or expiry column — the only
      separator is the key prefix, a convention the storage README itself
      (`:76-82`) flags as fragile after the `v2:` incident. Settings blurs them
      too, describing "graph snapshots, search results and paper details" as
      one thing (`SettingsModal.tsx:379`) with a single all-or-nothing
      `drop_cache` (`routes/settings.py:294`). Worth noting one genuine
      oddity to decide on while here: paper TL;DRs are cached with
      `max_age=None` — **they never expire** (`routes/graph.py:392`).

      **Test gap:** `has_graph` is asserted only for the fresh case
      (`test/atlas/services/test_search.py:46,156`); nothing ages a snapshot
      past `cache_ttl` and asserts the badge goes away, though the aging helper
      already exists (`test/atlas/storage/test_cache.py:21-23`).
      *(From the `todos.md` inbox, 2026-08-16.)*

- [ ] **Make it clear that direct search leaves the map** — the ask keeps
      🔍 **Find papers** while a graph is open (**decided 2026-08-15**, against
      the first instinct to hide it; it rides the Chat row rather than the bar
      since v7.11.0), but nothing on screen says what it does
      differently there. In graph mode every other control is about the papers
      you can see; this one goes looking for papers that have nothing to do
      with them, and a reader can reasonably read it as "find papers *in this
      map*". *(From the `todos.md` inbox, 2026-08-15.)*

      **Why it stays.** Hiding it would have removed a path, not just a
      distraction: searching would only be reachable from home, and `goHome`
      dispatches `workspaceCleared()` — so "go home to search" costs you the
      graph and any unsaved exploration. Running a search *beside* an open map
      is also a legitimate thing to want, and it is the reader's call whether
      the two are related.

      **So the work is wording, not gating.** Enough that the difference is
      obvious before the click: the toggle's tooltip and the transcript's lead
      line should both say these are new papers from the whole corpus, not the
      neighbourhood on screen. (The **Filters** button stays regardless — since
      v7.6.0 that window binds the *researcher's* paper searches too, which
      matters more in graph mode, not less.)

      **What comes after it is now its own ticket** — "Grow the map from a
      search hit, instead of only leaving it" *(Patrick, 2026-08-15; split
      out 2026-08-16)*, below. Keep them in that order: this one explains
      what search does today, that one gives it a second mode.

- [ ] **Teach the visual vocabulary — what every colour and glyph means** —
      the app encodes a lot in colour and shape and explains almost none of it.
      The graph legend lists node colours by name (References, Field Landmarks,
      Latest Publications…) with no word on what the relation *is*; the two
      citation glyphs (one node lit = spotlight a paper already on the canvas,
      three nodes wired = build that paper's own graph) are explained only in a
      tooltip you have to hover to find; edge colour, edge thickness
      (influential citations), node size (citation count), the dashed ring
      (teacher-discovered) and the cyan selection ring are explained nowhere at
      all. **Two more surfaces joined the list since** *(Patrick,
      2026-08-16)*: the v7.8.0 **left rail** — its glyphs (✎ new graph, ＋
      save, 📚 library, ⚙, ☀/☾, ?) and the fact that the list under them is
      your saved graphs — and the **ask's own controls** (🔍 Find papers, ▽
      Filters, and the 📚 source scope — a labelled chip row under the bar
      with no graph, bare icons on the Chat row with one, since v7.11.0),
      which today only the tour explains, and the tour is a one-time read.
      The docked half is the sharper case: there they are icons and nothing
      else.

      **The ask:** one place that lays out the vocabulary. Candidates worth
      pricing against each other — a tour step (fits the existing help
      surface, but the tour is a one-time read and this is reference
      material); an expandable "what am I looking at" panel off the legend
      (discoverable exactly when the question occurs); or a help/? overlay.
      Reference material argues against the tour.

      **Do this after the two tickets that change the vocabulary itself** —
      "A filter chip for teacher-discovered nodes and search nodes" and
      "Rework the `search` node treatment", both below — not before:
      documenting a palette that's about to lose a colour is work done twice. It's also the reason to keep resisting new
      colours — the fewer arbitrary hues, the shorter this page is.
      *(Patrick's ask, 2026-08-15.)*

- [ ] **The references lecture keeps opening with "The story begins…"** — a
      verbal tic in HOW WE GOT HERE, and the reader sees it every time. Worth
      knowing before anyone starts: **it is not a string in the codebase** —
      grep finds nothing, because the lecturer is *writing* it. So the fix is
      in `lecturer/config.py`'s mode prompt, and the shape of it is a rule
      about openings rather than a banned phrase (ban the sentence and the
      model reaches for the next stock opening). The `teaching-voice` skill is
      the other candidate home, if the tic turns out to span modes rather than
      living in this one. Check the other three modes before deciding which.
      *(From the `todos.md` inbox, 2026-08-15.)*

- [ ] **The chat bar's two icons sit small inside their circles** — both
      buttons are the same 34px disc (`.teacher-ask > button` and its
      `.ask-clear` variant, `teacher.css`), which was the point; what's off is
      the *glyph inside* each. The send arrow is a 16px text character in a
      34px circle and the bin is a 19px SVG, and both read as undersized for
      the disc around them. Scale each up — the arrow via `font-size`, the bin
      via its `svg` width/height — and check the pair together rather than one
      at a time: they sit side by side, so what matters is that they look like
      the same weight of control, not that either hits a particular number.
      Watch the stop square (`.stop-glyph`, 9px) too — it shares the send
      button and has to grow with it or the hover swap will jump.
      *(From the `todos.md` inbox, 2026-08-14.)*

- [ ] **Animate the arrival of the graph** — the sibling of the chat-motion
      work that shipped in v6.15.0 (see [docs/history.md](docs/history.md)),
      and the bigger of the two. Today the landing→graph
      transition is a cut: the chat is the page, then the graph simply *is*
      there and the chat is a side panel. The ask is a **zoom-in fade into the
      graph while the composer glides out of the way to the side** — one
      continuous move that says the conversation became the map, rather than
      two surfaces swapping places.

      **What makes it feasible.** The Teacher element deliberately stays at a
      single position in the tree across the switch (v6.13.0) — only its class
      changes, `.teacher.landing` → docked — precisely so entering graph mode
      doesn't remount it. So the composer's journey is a style change on one
      persistent element, which is the one case CSS can actually animate. The
      catch is *what* changes: `width: 100%` + `flex: 1` + `padding` →
      `width: 340px` + `flex-shrink: 0` + a left border, plus an inner
      `width: min(720px, 100%)` reading column that has to narrow at the same
      time. Some of that transitions cleanly and some doesn't (flex shorthand
      changes don't), so the first task is finding the subset that does — or
      committing to a FLIP-style transform, which animates smoothly regardless
      but needs the before/after boxes measured.

      **The graph half.** `GraphExplorer` already has the hook: a one-shot
      `zoomToFit(400, 60)` latch fired from `onEngineStop` once the force sim
      settles (`fitDone`). A zoom-in entrance is that same camera move started
      from further out, plus an opacity ramp on the canvas — so the sequencing
      question is whether the fade waits for the sim to settle (clean, but the
      first layout tick is the slowest) or overlaps it (livelier, but the user
      watches nodes shuffle into place). Worth trying both; the honest answer
      may be that a settling graph is *worth* watching.

      **Constraints inherited from the ticket above:** one motion language for
      both, a `prefers-reduced-motion` path for everything added, and no
      re-animation on a *re-seed* — a graph already on screen being replaced is
      a different, quieter event than the first one arriving, and the
      transcript survives it on purpose. *(Patrick's ask, 2026-08-14.)*

- [ ] **Make the provenance line a control, not a caption** — the quiet
      summary under an answer ("grounded in 1 of your sources + 1 paper ✦",
      `teacher/transcript/provenance.ts`) reads as a label, but it names the
      one thing a reader most wants to act on. **Ask:** when the paper it
      cites isn't on screen, the line becomes clickable and *seeds the graph*
      on it — tinted like a seeding `[n]` chip and ending in the graph glyph
      instead of the ✦. When the answer's papers **are** already on the graph,
      it stays exactly as it is: current colour, current diamond, because the
      whole-bubble click already re-lights them and a second affordance saying
      the same thing is noise.

      **What to settle first:** which paper it seeds when the answer cites
      more than one. The line is a *count* ("+ 3 papers"), not a reference, so
      there's no single target — options are seeding the first cited paper,
      splitting the count into per-paper chips, or only offering the click in
      the unambiguous one-paper case. The reuse is otherwise clean: the
      chip's colour, glyph and seed handler all exist (`AnswerMarkdown`'s
      `cite-ref-seed` + `GraphGlyph` + `onPaperSeed`), and the
      already-on-the-graph test is the same `onGraphIds` set that greys stale
      chips. Any provider stamp on the seeded id has to come along too — see
      the graph-free provider ticket above. *(Patrick's ask, 2026-08-14.)*

- [ ] **A lecture that grounded an answer should say so in the provenance
      line** — the line under a bubble already names papers, web pages and
      the reader's own sources; **lectures are the one grounding it stays
      silent about**. They're real material and they're already in the
      prompt: `answer(lectures=...)` folds every played lecture's beats in as
      context to build on (`_lectures_context`, budgeted by
      `_LECTURES_MAX_CHARS`), so an answer can lean on a lecture the reader
      watched and report itself as ungrounded.

      **The catch, and it's the ticket's real work:** every other count on
      that line is *observed* — a tool call the server watched happen — while
      lecture context is **pushed into the prompt**, so there is nothing to
      count. Whether the answer used it is exactly the thing `Provenance`'s
      docstring refuses to ask the model, because a model can't reliably tell
      which of its sentences came from context and which from its weights. So
      either the honest version is weaker than the others ("2 lectures in
      context", a fact about the prompt, not the answer), or lectures need a
      citation marker of their own so usage can be counted off the finished
      prose the way `[Sn]` and `[n]` are. Settle that before building.

      **Trace chips too**, on the same terms — the reader should watch the
      agent reach for a lecture the way they watch it search their library.
      Note this has the same problem in sharper form: a trace chip reports a
      *tool call*, and there is no lecture tool to call — the material is
      already in the prompt. A chip saying "read the lecture" when nothing
      was read would be the first dishonest chip in the panel. Which may
      argue for making lecture material a real retrieval tool rather than
      prompt stuffing — a bigger change, and the honest one.
      *(From the `todos.md` inbox, 2026-08-15.)*

- [ ] **A "quick answer" toggle for a run in progress** — the agentic sweep is
      thorough by construction: since v7.0.0 an `answered` turn consults every
      available source, and v7.1.0 has it follow the web's names back into the
      literature. That's right by default and sometimes not what the reader
      wants *right now* — they asked something small and are watching a
      full sweep run. **The ask:** a control in the chat, live during
      execution, that says "wrap up".

      **The mechanism already exists**, which is what makes this cheap: every
      tool answers `STEPS_EXHAUSTED` once the step budget is gone and the
      model lands the answer itself inside the same run — no cancel, no lost
      work. So "quick answer" is *zeroing `deps.steps_left` mid-run* rather
      than any new stopping machinery. **Two things to settle.** The
      coverage guard must not then bounce the answer for skipping a source
      — as of v7.1.0 it already stops demanding what a spent budget can't
      reach, so this composes, but it needs a test saying so *deliberately*
      rather than by luck. And the plumbing: the SSE stream is
      server→client only, so a mid-run signal needs a side channel (a second
      endpoint keyed on the run, or a cancellable flag in the deps the route
      can reach). Cheaper alternative worth pricing first: a "quick" flag sent
      **with** the question, which needs no side channel at all and may cover
      most of the want. *(From the `todos.md` inbox, 2026-08-15.)*

- [ ] **The Data Provider dropdown's text sits off-centre** — minor, and the
      cause is already visible: `.provider-select select`
      (`header/header.css`) uses `padding: 7px 26px 7px 10px`, where the 26px
      right pad reserves a lane for the custom data-URI caret (the native
      arrow rendered outside the rounded border on macOS, hence
      `appearance: none`). The text is centred in the *element*, so the
      asymmetric padding pushes it visibly left of optical centre. Either
      balance the horizontal padding and let the caret overlap its own lane, or
      commit to left-aligning the label so the offset reads as intentional.
      *(From the `todos.md` inbox, 2026-08-14.)*

- [ ] **Settings modal — the corpus vs. live-citations toggle** — the
      adaptive-sizing half of the stage-2 ticket shipped in v6.3.0 (the switch,
      the revived per-chip count sliders, the band-shape inputs — see history).
      What's left is the **corpus toggle.** The corpus path is a
      `storage.s2_corpus` edit today (settable in the modal since v6.1.0), but
      there's no way to say "ignore the corpus for this build" — useful when
      it's stale, mid-ingest, or suspect. The fallback already exists and is
      automatic when the corpus can't serve a seed; this makes it deliberate.
      **The catch:** the graph cache is keyed by `(provider, seed)` and **not**
      by citation source. v6.3.0's `BuildShape.cache_suffix()` is the pattern to
      follow — a suffix that's empty on the default path and distinguishing
      otherwise — so a corpus/live choice keys around the cache instead of
      serving the wrong old snapshot.
      **Sequencing (Patrick, 2026-08-09): do this *after* the S2-corpus
      landmark-citation research tickets land, not before.** The toggle is only
      worth exposing once the corpus path is known-good — shipping a user-facing
      "use the corpus" switch while the corpus still returns a random-looking
      set of Field Landmarks would just hand people a way to make their graph
      worse. Treat the research outcome as the gate. *(From the `todos.md`
      inbox, 2026-07-16; scoped 2026-07-19; adaptive half shipped 2026-07-20;
      gated on the corpus research 2026-08-09.)*

- [ ] **A filter chip for teacher-discovered nodes and search nodes** — discovered
      papers (dashed ring, from `expand_node`/`search_papers`) and topic-search
      hits (the pink `search` relation) have no filter control — both are
      **always shown**: `GraphExplorer.tsx` seeds the `enabled` set with
      `[...REL_TYPES, 'search', 'similar']`, and `GraphControls` renders chips
      only for `REL_TYPES`. Give them their own toggle(s) alongside the relation
      chips so a busy post-Q&A graph can collapse back to the built neighborhood.
      *(From the `todos.md` inbox, 2026-07-14; absorbs the former "search nodes
      as a filter chip" ticket, 2026-07-07.)*
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

- [ ] **Grow the map from a search hit, instead of only leaving it** — split
      out of the "direct search leaves the map" ticket above *(Patrick's
      idea, 2026-08-15; its own ticket 2026-08-16 — it's a feature, not
      wording)*. Today a paper found by direct search can only **re-seed**:
      you leave the graph you were reading to go look at another one. But the
      provider knows whether an edge exists between that hit and the papers
      already on screen, and *"does this cite, or get cited by, anything I'm
      looking at?"* is one `traversal` call per candidate. Answered yes, the
      hit can join the current map **with its real citation edge** — turning
      search from a way out into a way to reach distant work.
      **The constraint it must respect:** the graph only draws edges somebody
      actually wrote (v7.5.0), so this adds a paper *and its real edge*, never
      a "related to" line — a hit with no edge to anything on screen still
      has nothing to attach to, and re-seeding stays its only offer.
      **Sequencing:** do the wording ticket first; this one changes what
      search *does*, and there's no point explaining behaviour that's about
      to gain a second mode.

- [ ] **Responsive layout + a collapsible icon side rail (mobile-friendly)** —
      the frontend assumes a wide desktop window; resizing squeezes the
      header until controls collide, and mobile is unusable. Patrick's
      sketch: much of the header (Library / Assistant / Sessions / data
      source…) collapses into a **hidden side panel behind a hamburger
      (☰)**, in the style of **Azure DevOps' left rail — icons visible in
      the collapsed strip**, one per function, expanding to labels.
      **Before building: ask Patrick for examples/images of the look he
      wants.** Substantial: touches the header, panel overlays, and the
      canvas-resize plumbing; probably lands in stages (desktop-narrow
      first, true mobile after). *(From the `todos.md` inbox, 2026-07-18.)*

      **Half of this shipped as v7.8.0** — the rail exists, collapses to a
      56px icon strip, and swallowed the header outright, which was the
      sketch's whole left-hand side. (v7.11.0 added the Azure DevOps gesture
      the sketch was drawn from: drag the handle past the floor to fold it,
      drag the folded edge to bring it back.) What's left is the *responsive*
      half:
      the layout still assumes a wide desktop window, and nothing reflows or
      re-clamps as the window narrows (the sideways-scrolling chat panel
      above is one concrete instance of it). Re-price the remainder against
      the rail as built rather than against the original sketch.

- [ ] **Highlight inline library-source references like paper links** — when an
      answer cites an uploaded library source inline (source, page number), the
      reference renders as plain text; style it in the same blue treatment used
      for research-paper link references so it stands out. The one difference:
      it's a highlight only — clicking shouldn't do anything, since there's no
      node/page to jump to. *(From the `todos.md` inbox, 2026-07-19.)*

- [ ] **Let a source be renamed after upload, so chat references are readable**
      — an uploaded source carries whatever name it arrived with, and in a chat
      citation that's often unreadable: a hashed PDF filename, or a URL slug for
      a web page. Give the library an **alias** — an editable display name set
      after upload — and render *that* wherever the source is named to the user
      (the `[Sn]` marker's resolved title, the trace chips, the library list).
      Pairs naturally with the reference-highlighting ticket above: no point
      styling a citation to stand out while the text inside it is a hash.
      **Design notes:** the alias is presentation-only — retrieval, embeddings,
      and the stored source id must not key on it, or renaming would invalidate
      the index. Keep the original name visible somewhere (tooltip, or beneath
      the alias in the library list) so a source stays identifiable. Worth
      deciding whether an alias also reaches the *agent* — the researcher sees
      source titles when it decides what to search, so a clearer name may help
      it too, but that makes the alias semantically load-bearing rather than
      cosmetic. Default to presentation-only unless there's a reason.
      *(From the `todos.md` inbox, 2026-08-09.)*

- [ ] **Light-mode relation colors — darker & higher-contrast** — the v6.2.0
      light/dark toggle deliberately left the *relation* palette unthemed (gold
      seed, blue references, green landmarks, pink search were chosen to read on
      either background, so only the neutrals flip). In light mode those read a
      touch washed out against the off-white; give the reference-type colors
      **darker, more contrasting** variants for light while keeping the soft
      off-white and grey neutrals. This revisits the "relation palette is not
      themed" call from that ticket — so it's a light-only override of the shared
      relation colors, not a full re-theme. *(From the `todos.md` inbox,
      2026-07-20.)*

- [ ] **Default the theme to the browser's `prefers-color-scheme`** — v6.2.0
      deliberately did *not* read `prefers-color-scheme` (dark-first app; a light
      OS setting shouldn't silently hand a first-timer the alternative), seeding
      the opening theme from `ui.default_theme` instead. This flips that: for a
      browser with no saved choice, honor the OS preference by default. Decide
      how it composes with `ui.default_theme` — does the config default become
      the fallback when the OS expresses no preference, or does the OS win
      outright? — and keep the explicit ☀/☾ toggle authoritative once the user
      picks. Touches `ui/theme.ts`'s `readStored` / `applyConfiguredDefault`
      rule. *(From the `todos.md` inbox, 2026-07-20.)*

- [ ] **A startup discovery feed — hottest & latest papers** — the app opens to
      a bare chat bar; give it a landing **feed of papers to click into**, with
      a **tab switch** between *Hottest* (trending / recently most-cited) and
      *Latest* (newest) across all fields. Clicking a paper seeds its graph, the
      same as a search hit. **The hard part is the data, not the tabs:** neither
      S2 nor OpenAlex exposes a plain "trending" endpoint, so *Hottest across all
      fields* needs a defined signal (e.g. recent papers ranked by
      citation-velocity, or a curated set) and *Latest* a cross-field recency
      query — decide the source and its caching before building the UI. *(From
      the `todos.md` inbox, 2026-07-20.)*

- [ ] **Tidy the tour's ordering and card titles** — polish, not a bug: the
      steps teach the right things, they just **arrive in the wrong order**
      and some **card titles want renaming**. Explicitly *not* about length
      (Patrick, 2026-08-16 — "it's not the length of the tour") — no stop
      gets cut to save time. Both lists live in `tour/steps.ts`.

      **The ordering problem is the rail.** `HOME_TOUR` walks ask →
      direct-search → filters → **provider** → **library button** → library
      panel → assistant panel → **rail (saved graphs)** → **settings**, so it
      crosses from the rail to the centre and back: the four rail controls
      are visited in two groups split by a stop in the middle of the screen,
      and within the rail they don't follow the rail's own top-to-bottom
      order (saved graphs sit *above* the data source, but are taught last).
      `GRAPH_TOUR` already follows the eye (controls panel → find → detail
      panel → teacher) and is the smaller job.

      **The titles to re-read** are the ones that name a mechanism rather
      than what the reader gets: *"Release · Fit · Refresh · Clear"* (a list
      of buttons as a heading), *"How many of each"*, *"Open a paper"* (which
      targets the hint line, not a paper), *"Four lectures"* (a count that
      goes stale the moment a mode is added). One rule to hold: the bubble's
      title doubles as the **jump select** (see `tour/README.md`), so titles
      are navigation labels — they have to read well out of context, in a
      list, not just above their own card.

### Enhancements & tech debt

- [ ] **`atlas corpus verify` mistakes a tidied-up release for a destroyed
      one** — deleting a release's `raw/` shards once its ingest succeeds is
      **supported and documented** (`corpus/paths.py`'s module docstring: "A
      release's `raw/` shards remain deletable the moment its ingest
      succeeds"), and Patrick did exactly that to the 2026-08-05 release on the
      Mac — 47 GB of Parquet left, `raw/` gone, `download.json` still listing
      all 455 shards `done`. Run `atlas corpus verify` against that release now
      and `_inspect_shard` hits `not target.exists()` for every shard and
      reports **455 × "missing"**. With `--repair` it would then cheerfully
      **re-download all ~408 GB** — a spectacular answer to "please check my
      corpus is OK", on a release that is perfectly fine. (Reproduced offline
      against the real release, feeding `download.json`'s shard names in as the
      listing: 395/395 citations shards came back `missing`, no network needed
      — `_inspect_shard` short-circuits before it probes a size.)

      **The fix is a precondition, not a per-shard change:** `verify_release`
      should notice that the dataset's raw directory is absent or empty and
      return a distinct "raw shards deleted — nothing to verify, the ingested
      Parquet is what matters here" outcome, rather than a per-shard verdict.
      Worth deciding at the same time whether `--repair` should refuse (or
      demand confirmation) when the miss count is *everything*, since that
      shape is far more likely to be a tidied release than a corrupted one.
      Note `atlas corpus download`'s behaviour on the same state is
      **correct and should not change** — shards gone means re-fetch, which is
      what "a re-ingest just means a re-download" promises.

      Shipped in v7.12.0 and found the same night; no data at risk, but the
      command is a footgun until this lands. *(Found 2026-08-16.)*

- [ ] **Exercise the corpus downloader's unproven recovery paths on Windows** —
      v7.12.0's guard is covered by 16 offline tests against a fake `urlopen`,
      but three paths have **never run against real S3**, and all three only
      fire on the rare/awkward cases the tests had to simulate: (1) the **416
      disambiguation** (`_settle_range_past_eof` — is a `.part` at/past EOF a
      complete shard to promote, or over-long garbage to discard?), (2) the
      **mid-verify URL refresh** (a 400-shard verify outliving the signatures
      it started with), and (3) **`verify --deep`** at full scale, which
      decompresses ~400 GB. The Mac can't test any of it — its raw shards are
      deleted (see the ticket above) — so this rides on the **Windows machine**,
      which still has its shards, or on the next monthly release pull.

      Cheap and worth doing in the same pass: run `verify` (fast, size-only)
      against a corpus whose shards are intact and confirm it reports a clean
      bill, since tonight's evidence that the shards *are* intact came from a
      hand-rolled `gzip -t` sweep rather than from the command itself. See
      `docs/bugs.md`'s "A dropped connection looks exactly like a finished
      download" for why each path exists. *(Found 2026-08-16.)*

- [ ] **Save a conversation with no graph** — Save is graph-gated end to end:
      the rail only offers it when `hasGraph` (`Atlas.tsx`), `saveWorkspace`
      throws `No graph to save yet.` without one, `POST /api/sessions` 400s on
      an empty `nodes` list, and `restoreSession` rebuilds a `GraphResponse`
      from `data.seed` on the way back. But since the landing chat became the
      front door, a reader can hold a long, useful conversation before any
      graph exists — and today closing the tab throws it away. **The design
      question is what a graphless session *is*:** does it appear in the same
      saved list as the graphs (and if so, what names and labels it, with no
      seed title to borrow?), and what does reopening one restore you to — the
      landing chat with its transcript, presumably, which the store can already
      express (`graph: null` + a restored transcript). **The plumbing is
      mostly loosening, not building:** make `seed`/`nodes` optional through
      the save blob, the route's validation, and the restore path, and decide
      whether a session that later grows a graph overwrites the same row.
      *(From the `todos.md` inbox, 2026-08-16.)*

- [ ] **Rename `integrations/` to `providers/`** — `src/atlas/integrations/`
      holds one subpackage per external data source (`semantic_scholar/`,
      `openalex/`, `arxiv/`), and "integrations" is the vaguer word for what
      they are: the app already says **provider** everywhere else — the
      `Provider` type, `resolve_provider`, `config.providers`, the header's
      "Data source" dropdown, the per-provider cache keys. One name for one
      concept. **Blast radius is wide but shallow:** the package is imported
      from routes, services, and every agent (`from ...integrations import
      openalex`), so it's a mechanical sweep plus the READMEs that name it
      (`src/README.md`'s map, `services/graph/README.md`, `agents/README.md`).
      Two things to check while doing it: `providers` is already a *config
      section* name, so make sure the docs distinguish the package from
      `config.providers`; and `arxiv/` is not a graph provider at all (it's an
      id parser and a category vocabulary), so decide whether it belongs under
      the new name or somewhere else before the rename cements it. *(From the
      `todos.md` inbox, 2026-08-15.)*

- [ ] **The researcher is slow next to plain Claude or ChatGPT — find out
      why, then decide what to trade** — Patrick's read is that it's the web
      search; the evidence says it's the *shape of the run*, and the ticket
      should start from that rather than from the hunch. *(From the `todos.md`
      inbox, 2026-08-15.)*

      **What one real turn looks like** (`data/atlas.log`, 2026-08-15
      21:23–21:24, "what's new in quantum computing?"): ~31s wall clock for
      `searches=1 passages=6 paper_searches=3 web_searches=1 web_pages=8`.
      That is **three scout runs**, and a scout is not one call — the logged
      `find_papers` line shows a single run issuing four lookups (two
      searches, two `more_like` hops). So the turn is a Sonnet researcher
      taking a step, waiting on a Haiku sub-agent that is itself taking
      several steps, each waiting on a provider — **serial all the way down**,
      by construction: the scout's tools are `sequential=True` because they
      mutate shared deps, and the researcher's are too.

      **Why the comparison isn't quite fair, and where it still stings.**
      Claude answers from weights with one round-trip; this reads real
      sources and tells you which. That difference is the product, not a
      regression. But a reader doesn't experience "grounded" — they
      experience 31 seconds, and three of those scout runs may have been one
      question's worth of need.

      **Levers, roughly in order of value-per-risk.** (a) **Run independent
      tools concurrently** — `search_web` and `find_papers` for *different*
      needs don't touch each other's state; the sequential flag is about deps,
      and the parts that genuinely share deps are inside one scout, not
      across two. (b) **Show more, sooner** — the direct-search work proved
      the reader will happily watch a search that is visibly working
      (v7.6.0); the researcher already streams trace chips but sits silent
      through the long middle. (c) **Cap the fan-out** — three paper searches
      for one question may be the prompt's "one call is the floor, not the
      ration" landing too hard. (d) **Model tier per worker** — already Haiku;
      little left. **Measure before touching (a)**: instrument per-step
      timings so the split between model time, provider time and waiting is a
      number, not a guess. A prior latency complaint on this same path turned
      out to be six S2 429s from running keyless — worth ruling out first,
      every time.

- [ ] **Re-evaluate where the frontend lives and what its folder is called** —
      **it stays in this repo for now** (Patrick, 2026-08-09); this is about
      *placement and naming*, not extraction. `frontend/` is a generic name
      inherited from `npm create vite`, and it sits at the repo root as a peer
      of `src/` — which reads oddly now that the backend is a proper src-layout
      package (`src/atlas/`) and the frontend is the larger of the two trees.
      Options worth weighing: rename in place (`web/`, `ui/`, `app/`, or
      something Atlas-specific); move it under a shared parent so the two halves
      are visibly siblings (`packages/`, `apps/`); or leave it and just write
      down *why*, which is a legitimate outcome. **What makes this
      non-trivial** is the blast radius of a rename — `frontend/` is named in
      `.pre-commit-config.yaml`'s two hook patterns, `noxfile.py`'s `vitest`
      session, both `bin/setup` scripts, `.github/workflows/ci.yml`,
      `.gitignore` (`frontend/dist/`), the Flask static-serving path, and a
      good deal of prose across `README.md`, `CLAUDE.md`, and the READMEs
      themselves. Do it as one mechanical sweep with the gate green on both
      sides, or not at all — a half-renamed tree is worse than either end
      state. Also note the "Publish to PyPI" ticket wants to ship
      `frontend/dist` as package data, so settle the location *before* the
      packaging work hard-codes a path. *(From the `todos.md` inbox,
      2026-08-09.)*
- [ ] **Scrub the STOP/SKIP docs & memories once citation-thresholding supersedes
      them** — a deliberately-deferred cleanup, **gated on** the "Replace the
      STOP/SKIP citation rules with a citation-threshold predicate" ticket
      (Citations & graph data) actually landing. While STOP/SKIP still ship, their
      docs stay accurate and must remain. The moment the predicate replaces them,
      a large body of material goes dead at once and should be revised in one
      pass: `docs/landmark-vocabulary.md` (STOP/SKIP/tau/anchor — most of it),
      `docs/predict-vs-compute.md` (its whole regime table is about the rules
      being replaced), the STOP/SKIP/tau rows in `docs/constants.md`, the relevant
      `docs/configuration.md` prose, and the STOP/SKIP-era memories. `history.md`
      and `bugs.md` stay **verbatim** as always. (The 2026-07-22/23 research-reset
      scrub already retired the *model/pipeline* material; this ticket is the
      *rules* half, which couldn't go until the rules do.) *(Filed 2026-07-23.)*
- [ ] **Audit every constant in `src/` for config-knob-worthiness — then decide
      which knobs belong in the UI instead** — a systematic pass over the
      module-level constants (`NBUCKETS`, `_RANK_POOL`, `_MAX_OFFSET`,
      `PER_YEAR_CAP`, `_LATEST_WINDOW_MONTHS`, `UNBOUNDED_LANDMARK_CAP`, the
      retrieval/chunking numbers, agent extras defaults, …) asking of each:
      should this be a `config.json` knob? The audit needs the lesson the
      v6.0.0 count-caps purge taught as its filter — knobs nobody turns are
      *deletion* candidates, so "could be configurable" is not the bar;
      "someone would actually turn it, and turning it is safe" is.
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
- [ ] **Gate research notebooks — nothing executes them, so they rot silently**
      — a committed notebook output is a *claim*, and nothing checks it. Under the
      old (now-deleted) `research/` layout, two of three notebooks had been
      un-executable since the src-layout migration and nobody noticed, because no
      nox session runs a notebook; `precommit` lints notebook *identifiers*, which
      makes them feel covered while their correctness is checked by no one (see
      `docs/bugs.md` → "Two of the three research notebooks had been un-executable
      for weeks"). **Carry this forward into the rebuilt research** (the
      `research-reset` restart): whatever notebook lives beside a fitted artifact
      needs a `notebooks` nox session running `jupyter nbconvert --execute` over
      it. **The design question that stops it being a one-liner:** the gate must
      never hit a live API or need the corpus machine, so it needs a rule for
      what's includable (offline, committed inputs only) and a per-notebook opt-out
      rather than globbing everything — and the pipelines' **collectors** (which
      call live APIs) stay uncovered for the same reason. Fold this into the
      research-rule decision before rebuilding the pipeline plumbing. *(Found while
      renaming the budget vocabulary, 2026-07-16; re-scoped for the restart
      2026-07-22.)*
- [ ] **Rename `digest.db` → `cache.db`** — the ephemeral graph-snapshot store
      is still named `digest.db`, a leftover from the retired daily-digest era;
      it's really the 1-day graph/artifact **cache** now. Rename the file (and
      the `storage.data_dir`-relative path + any `config`/docstring references,
      e.g. `storage/sessions.py`'s note contrasting it with `sessions.db`) so the
      name matches what it holds. A cosmetic rename — old `digest.db` files can be
      left to age out or deleted, since it's a regenerable cache. *(From the
      `todos.md` inbox, 2026-07-11.)*
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
      the scout searched for, so the researcher may ground on the wrong
      cached hits. Investigate the retrieval/cache-key path vs. the expanded
      query (paper scout → researcher/retrieval). *(From the `todos.md` inbox,
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
- [ ] **Support additional LLM providers (OpenAI, Google, Meta, …)** — the whole
      agent crew runs on Claude only today; the README now says other providers
      are on the roadmap. PydanticAI already abstracts providers and `config.llm`
      is shaped for more than one (`LLMProvidersConfig` names `AnthropicProvider`,
      `OpenAIProvider`, …), so the work is: wire provider construction per vendor,
      let each agent's `model` string name a vendor (`openai:…`, `google:…`,
      today's are `anthropic:…`), and generalize the settings modal — the agent
      **model dropdowns** populate from the Anthropic Models API only, and the
      "LLM vendor" row is a fixed label. Watch for per-provider streaming and
      tool-call differences in the agentic paths (see `teacher/agentic.py`'s
      SDK-boundary handling). *(From the `todos.md` inbox, 2026-07-20.)*
- [ ] **Publish to PyPI — pick an available distribution name** — the package
      `name` in `pyproject.toml` must change even though the GitHub repo and the
      `atlas` CLI stay as-is. **Availability checked 2026-08-09:** `atlas` is
      TAKEN; `arxiv-atlas`, `atlas-papers`, `papers-atlas`, `atlas-graph`, and
      `citation-atlas` are all free (404 on the PyPI JSON API). Also needs the
      packaging work: **bundling the built React frontend (`frontend/dist`) as
      package data** so `atlas serve` works from an installed wheel,
      config-file discovery for an installed package (today it reads
      `config.json` from the cwd), and the PyPI metadata (license, authors,
      classifiers, project URLs, long-description from the README).
      `[build-system]` already exists (hatchling).
      **The real driver, established 2026-08-09.** Not distribution to the
      public — Patrick needs the code inside his employer's network, and their
      only ingress is an **Artifactory remote that proxies PyPI** (it also
      fronts npm and other public mirrors) with a **JFrog Xray** scan on the
      way in. A public GitHub repo does *not* help if GitHub isn't an approved
      source. Artifactory serves **both sdists and wheels**, so the sdist can
      carry whatever source the work side needs. The work copy is a **one-way
      import — no syncing code back** to the GitHub repo (Patrick, 2026-08-09).
      **Consequences of that framing:**
      - PyPI gives no *fork* — no git history, no PRs. It seeds a work-side
        repo once; it is not a synced remote. Accepted.
      - **Blocked on the PyMuPDF/AGPL question** — see the optional-extra
        ticket below. Xray license policy plausibly rejects the whole package
        over that one transitive dependency, which would waste the packaging
        work. **Patrick owns clarifying the Xray policy**, including the
        specific question of whether it flags *declared optional dependencies*
        or only what actually resolves.
      - **Open: does the work side need the frontend TypeScript source?** A
        wheel/sdist would carry the built `frontend/dist`, not `frontend/src`.
        Their Artifactory also fronts npm, so building the frontend at work is
        possible — but only if the TS source gets there somehow.
      - The **Windows CUDA torch routing does not survive publication**:
        `[[tool.uv.index]]` is uv-only resolution config, absent from wheel
        metadata, so `pip install` on Windows silently gets PyPI's CPU-only
        torch — exactly the bug that index block exists to fix. Needs at least
        a documented warning; matters less if the work side is Linux.
      Ties into the licensing work (2026-07-20) — a public, timestamped release
      is also the prior-art defense discussed there, though note
      `docs/licensing.md:61` credits *"this repo, and PyPI"*, so making the
      GitHub repo public would serve that goal on its own. **The MIT →
      Apache-2.0 relicense trigger does *not* fire on a one-way import** (no
      outside copyright enters the repo); Patrick nonetheless chose to
      relicense first, 2026-08-09, as a deliberate preference rather than a
      prerequisite. *(Raised 2026-07-20, deferred from the licensing pass;
      re-scoped 2026-08-09 around the work-Artifactory driver.)*
- [ ] **Make PyMuPDF an optional extra — it's AGPL, and it's the one licensing
      landmine in the dependency graph** — a license audit of the installed tree
      (2026-08-09) came back clean everywhere except one:
      `pymupdf` is **"Dual Licensed - GNU AFFERO GPL 3.0 or Artifex
      commercial"**. Everything else is BSD-3 (torch, scikit-learn, flask),
      Apache-2.0 (sentence-transformers), or MIT (anthropic, duckdb,
      sqlite-vec). Enterprise scanners commonly ban AGPL outright, and Atlas is
      a Flask **network service** — precisely the scenario AGPL §13 targets — so
      this is the most likely reason the "Publish to PyPI" work above fails at
      the Xray gate. **The fix, and why it beats a work-specific fork:**
      ```toml
      dependencies = [ … ]           # pymupdf removed
      [project.optional-dependencies]
      pdf = ["pymupdf>=1.24"]
      ```
      `pip install <dist>` then has no AGPL anywhere in its graph, while
      `pip install <dist>[pdf]` (and the dev env / `uv sync --all-extras`) keeps
      today's behavior. One published package, no divergent branch whose
      pymupdf-removal could drift back into `main` — which was Patrick's stated
      worry, 2026-08-09. **Contained enough to be tractable:** pymupdf is
      imported in exactly three modules — `services/pdf/{floats,mine,text}.py` —
      with references in `config.py` and `services/sources/extract.py`. The work
      is making those imports lazy and degrading the upload/sources feature
      cleanly ("PDF support not installed") rather than crashing at import.
      Work doesn't plan to upload files or sources at all (Patrick), so the
      degraded mode is the *expected* mode there.
      **Caveat that could kill the approach:** some policy engines flag
      *declared* optional dependencies, not just resolved ones. If Xray does,
      the extra doesn't clear the gate and the real fix is swapping to
      `pypdfium2` (BSD-3/Apache-2.0) or `pdfminer.six` (MIT) — a much bigger
      job, since `mine.py`/`floats.py` lean on PyMuPDF's layout and image
      extraction. Confirm before building either. Worth doing on its own merits
      regardless of PyPI: it lightens the default install and removes a copyleft
      dependency from a network service. See [docs/pdf-mining.md](docs/pdf-mining.md)
      before touching the caching layer. *(Filed 2026-08-09, out of the PyPI
      packaging discussion.)*
- [ ] **A deploy / release-automation strategy** — *(CI, the first of this
      ticket's three stages, **shipped in v6.10.0** — see
      [docs/history.md](docs/history.md). What follows is the remainder.)* The
      release ritual is still manual (bump `pyproject.toml` → `uv lock` → tag →
      push; see `CLAUDE.md`), and there's no deploy story at all. Still to
      define: a **repeatable build** (backend wheel + bundled frontend), how a
      **release** is cut and published, and **where/how the service is
      deployed**. `.github/workflows/release.yml` exists but only asserts the
      tag matches `pyproject.toml`'s version — it is the place the build and
      publish jobs will land. **Fold PyPI publishing in** — the concrete
      packaging (distribution name, frontend bundling) is the "Publish to PyPI"
      item above; this is the surrounding automation, and it **shouldn't start
      until the Xray policy answer lands**, since that decides whether there's
      a publishable artifact at all. Deploy is the genuinely open one: no
      target has been chosen, and the service needs an `ANTHROPIC_API_KEY` and
      a writable `data/`, so it isn't a static host. *(From the `todos.md`
      inbox, 2026-07-20; narrowed 2026-08-09 when CI shipped.)*
- [ ] **Rename the `data/oa_pdfs/` PDF cache — "oa" reads as OpenAlex, means
      open-access** — `services/pdf/fetch.py` caches downloaded PDFs under
      `data_dir/oa_pdfs` (hash-named, LRU-pruned beyond `config.pdf.cache_files`).
      The `oa_` prefix is meant as *open-access* but reads as *OpenAlex*, which
      misleads — the cache is provider-agnostic (any paper's open-access PDF,
      mined for figures/full text). Rename to something unambiguous (`pdfs/`,
      `pdf_cache/`), updating `fetch.py` and the `services/pdf/README.md`
      references; old `oa_pdfs/` dirs can age out (it's a regenerable cache).
      *(From the `todos.md` inbox, 2026-07-20.)*
- [ ] **Move `check_identifiers.py` out of `bin/` to the project root** — the
      no-single-letter-identifiers AST hook lives in `bin/check_identifiers.py`,
      but it's repo-level tooling like `noxfile.py`, which sits at the root; move
      it alongside. Updates the `.pre-commit-config.yaml` `entry`
      (`uv run --no-sync python bin/check_identifiers.py`) and the two CLAUDE.md
      references. *(From the `todos.md` inbox, 2026-07-20.)*

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
