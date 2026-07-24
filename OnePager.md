# Atlas — One-Pager

> **Status:** v6.3.0 · living document · MIT-licensed. The core loop has
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

### UI & rendering polish

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
      serving the wrong old snapshot. *(From the `todos.md` inbox, 2026-07-16;
      scoped 2026-07-19; adaptive half shipped 2026-07-20.)*

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

- [ ] **Highlight inline library-source references like paper links** — when an
      answer cites an uploaded library source inline (source, page number), the
      reference renders as plain text; style it in the same blue treatment used
      for research-paper link references so it stands out. The one difference:
      it's a highlight only — clicking shouldn't do anything, since there's no
      node/page to jump to. *(From the `todos.md` inbox, 2026-07-19.)*

- [ ] **Wrap text in the research chat input** — the chat box keeps what you
      type on a single line, so longer questions scroll horizontally and are
      hard to follow while composing. Make the input wrap (likely a
      `<textarea>`/auto-growing input instead of a single-line field) so a
      multi-line question stays readable. *(From the `todos.md` inbox,
      2026-07-19.)*

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
      a bare search box; give it a landing **feed of papers to click into**, with
      a **tab switch** between *Hottest* (trending / recently most-cited) and
      *Latest* (newest) across all fields. Clicking a paper seeds its graph, the
      same as a search hit. **The hard part is the data, not the tabs:** neither
      S2 nor OpenAlex exposes a plain "trending" endpoint, so *Hottest across all
      fields* needs a defined signal (e.g. recent papers ranked by
      citation-velocity, or a curated set) and *Latest* a cross-field recency
      query — decide the source and its caching before building the UI. *(From
      the `todos.md` inbox, 2026-07-20.)*

### Enhancements & tech debt

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
- [ ] **Publish to PyPI — pick an available distribution name** — `atlas` is
      almost certainly taken on PyPI, so the package `name` in `pyproject.toml`
      must change (candidates: `arxiv-atlas`, `atlas-papers`, …) even though the
      GitHub repo and the `atlas` CLI stay as-is. Also needs the packaging work:
      a `[build-system]`, **bundling the built React frontend (`frontend/dist`)
      as package data** so `atlas serve` works from an installed wheel,
      config-file discovery for an installed package (today it reads
      `config.json` from the cwd), and the PyPI metadata (license, authors,
      classifiers, project URLs, long-description from the README). Ties into the
      licensing work (2026-07-20) — a public, timestamped PyPI release is also
      the prior-art defense discussed there. *(Raised 2026-07-20, deferred from
      the licensing pass.)*
- [ ] **A build / deploy / release strategy** — the release ritual is ad-hoc and
      manual (bump `pyproject.toml` → `uv lock` → tag → push; see `CLAUDE.md`),
      and there's no deploy story at all. Define a real one: **CI** (run
      `uv run nox` on push/PR so the gate can't be skipped), a **repeatable
      build** (backend wheel + bundled frontend), how a **release** is cut and
      published, and **where/how the service is deployed**. Fold **PyPI
      publishing** in — the concrete packaging (distribution name, frontend
      bundling) is the separate "Publish to PyPI" item above; this is the
      surrounding automation. Likely staged: CI first, then release automation,
      then deploy. *(From the `todos.md` inbox, 2026-07-20.)*
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
