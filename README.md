# Atlas

**Explore how research papers connect — and have an AI teacher narrate the
story of how a field got here.**

Drop in a paper and Atlas renders a **Connected-Papers-style interactive
graph** of how it links to the literature — the papers it cites (its
intellectual ancestors), the papers that cite it (its descendants), and its
nearest neighbors by meaning. Then wander: double-click any node to re-center
the graph on it and keep exploring.

It connects to the academic-graph ecosystem **dynamically** — there's no local
corpus of papers to store. The only things kept on disk are a small cache of
the graphs you've looked at, your saved sessions, and the library of sources
you upload (embedded locally; nothing leaves your machine).

> **Status: v2.0.0 — the readability rewrite.** The entire app was rebuilt
> file-by-file for a codebase a human can read: every package carries its own
> README (what/why → structure → design decisions → who uses it → how it's
> verified), the backend is strictly typed (mypy strict, Pydantic models on
> every boundary), and the frontend runs strict TypeScript with a
> three-slice Redux store. Along the way the app itself leveled up:
>
> - **Search covers all of Semantic Scholar** (200M+ papers across venues,
>   not just arXiv) — with an LLM **query analyst** that expands acronyms
>   ("DQN" → "deep Q-network") and **recalls famous papers by exact title**,
>   verified against S2's title-match endpoint so the seminal paper leads
>   the hits. Pasted arXiv ids/URLs still jump straight in; repeated
>   queries answer instantly from a whole-result cache.
> - **The AI teacher is a crew of [PydanticAI](https://ai.pydantic.dev)
>   agents** behind one orchestrator: a **lecturer** (streamed, illustrated
>   lectures in typed beats over the graph you built — history / intuition /
>   evolution / current frontier, each with the papers' real figures inline), a **researcher**
>   (agentic Q&A that reads full text via ar5iv, expands the graph, searches
>   S2, searches *your* library, and attaches real figures inline), a
>   **librarian** (single-shot RAG over your uploads, cited by page), and
>   the **query analyst**. Everything streams for real — beats, prose, tool
>   traces, discoveries.
> - **Bring-your-own sources** with hybrid retrieval (sqlite-vec semantic +
>   FTS5 lexical, fused with RRF), parallel PDF uploads with **live
>   embedding progress bars** (**GPU-accelerated** when there's a GPU to use),
>   and a per-source scope picker for the agents.
> - **Sessions** save the whole workspace — graph, discovered papers, chat —
>   and restore with zero API calls.
>
> See **[OnePager.md](OnePager.md)** for the vision, the full feature stack,
> and the open backlog — and **[docs/history.md](docs/history.md)** for the
> complete shipped record, version by version.

```
┌──────────┐  find seed   ┌─────────┐   whole graph      ┌──────────────────┐
│  search  │ ───────────▶ │ backend │ ─── seed/refs/ ──▶ │  Semantic Scholar│
│  (S2+LLM)│  (title/id)  │ (Flask) │     citations      │       — or —      │
└──────────┘              └────┬────┘  (one provider)    │     OpenAlex     │
                               │ /api/graph (thin cache)  └──────────────────┘
                               ▼
                     ┌───────────────────────┐
                     │  React + force graph  │  ← the interactive map you explore
                     └───────────────────────┘
```

Since **v5.0.0** the citation graph is built from **one** academic-data provider,
chosen per graph in the header's **"Data source"** dropdown (the v4.x
S2+OpenAlex hybrid is retired). **OpenAlex** returns true top-cited landmark
citers via server-sorted `cites:` queries (no offset ceiling); **Semantic
Scholar** does the whole graph too, but its live citation API is newest-first with
no citation sort and rejects any page past an offset of 8,000 — so the newest
**9,000** citers (the last page starts at 8,000 and holds 1,000) are all it can
ever reach, and its Field Landmarks can only be the best of the citers inside that
window. Since **v5.5.0**
the live path at least mines that whole reachable window and bands it **twelve
landmarks per publication year**, so a mega-seed's landmarks span the years the API
can see (DQN: 2019–2025, led by Conservative Q-Learning and Decision Transformer)
instead of piling into the last two. Everything older than the wall — DQN's
2013–2018 citers, the ones you'd actually name — stays out of reach live. Since
**v5.4.0** that ceiling is lifted for real by an **offline S2 citations corpus**
(opt-in): the
bulk `citations`+`papers` Datasets releases are downloaded and ingested to local
DuckDB-over-Parquet via the `atlas corpus` CLI, and the S2 provider then draws
Field Landmarks **citation-sorted across all history** from your own copy (the
graph's note says which source is behind the landmarks). It's the local prototype
of the eventual AWS Airflow→S3→Athena pipeline; see
[`src/atlas/integrations/semantic_scholar/corpus/README.md`](src/atlas/integrations/semantic_scholar/corpus/README.md).
The *Similar* relation is retired from the built graph (kept for the researcher's
`expand_node`).

**Stack:** Python/Flask + uv · [PydanticAI](https://ai.pydantic.dev) agents on
Claude · React + TypeScript (strict) + Vite + Redux Toolkit ·
[`react-force-graph-2d`](https://github.com/vasturiano/react-force-graph) ·
[OpenAlex](https://openalex.org) (citations) +
[Semantic Scholar Academic Graph API](https://api.semanticscholar.org/api-docs/) ·
[ar5iv](https://ar5iv.org) for figures/full text ·
[Hugging Face Papers](https://huggingface.co/papers) for code & artifacts ·
sentence-transformers + sqlite-vec for the local library. Runs locally.

---

## Setup

The toolchain (python, uv, nodejs, trivy) is pinned in `.tool-versions` —
[mise](https://mise.jdx.dev) installs it all with `mise install` (mise reads
the asdf-format file and works on Windows and macOS alike). With mise in
place, `bin/setup.bat` (Windows) or `bin/setup.sh` (macOS/Linux) does the full
bootstrap: pinned tools, `uv sync --all-groups` (dev tooling and the notebook
`research` group alike), and the frontend install + build. Without
mise, `uv` and `Node.js` installed any other way work fine too.

> **Windows pulls a CUDA build of torch** (~1.8GB, from PyTorch's `cu130`
> index) so the local embedder can use a GPU if you have one — PyPI's Windows
> wheel is CPU-only, and that's the whole difference between ~80 and ~1500
> chunks/s at ingest. It falls back to CPU on a machine without a GPU, and
> macOS/Linux resolve torch from PyPI as usual. See
> [`sources.embedding.device`](docs/configuration.md).

### 1. Configure

```bash
cp config.example.json config.json
```

All configuration lives in `config.json` (gitignored — it holds your keys; no
environment variables, ever). Every field is required and validated at startup
by Pydantic; the value-by-value rationale lives in
[docs/configuration.md](docs/configuration.md). The two keys that matter:

- **`providers.s2.api_key`** — a free
  [Semantic Scholar API key](https://www.semanticscholar.org/product/api).
  Optional but strongly recommended; the unauthenticated pool is tight.
- **`providers.openalex.api_key`** — optional. OpenAlex (the citation source)
  runs keyless
  on its `mailto` polite pool ($0.10/day of metered search — plenty for browsing);
  a free key at [openalex.org/settings/api](https://openalex.org/settings/api)
  lifts it to $1/day. Set `providers.openalex.mailto` to your email either way.
- **`llm.providers.anthropic.api_key`** — powers the whole agent crew
  (lecture, research Q&A, library chat, query analysis). The per-agent model
  choices live under `llm.agents`.

### 2. Build the frontend & run

**Single-server** (serves the built frontend + API together):

```bash
cd frontend && npm install && npm run build && cd ..
uv run atlas serve                      # http://127.0.0.1:5000
uv run atlas serve --port 5050          # ...or another port (--host to expose it)
```

**Development** (two terminals, hot-reloading frontend):

```bash
uv run atlas serve                      # Terminal 1 — API
cd frontend && npm run dev                    # Terminal 2 — http://localhost:5173
```

The Vite dev server proxies `/api/*` to Flask.

---

## Using it

1. **Search a paper** — type a title, a topic, or an acronym (the analyst
   expands it and title-resolves famous papers), or paste an **arXiv id /
   URL** to jump straight in. Cached papers appear instantly; an **instant**
   badge marks papers whose whole neighborhood is cached. The **Options**
   popover holds a publication-year window (1800 → now), S2 **fields of
   study**, and a checkbox that turns the analyst off for a raw, no-LLM
   search of your words as typed.
2. **Read the map** — 🟡 seed · 🔵 references · 🟢 citations · 🌱 latest ·
   💗 found-by-search. Citers split into two relations: **Field Landmarks**
   (green) are the most-cited papers citing the seed — the historic giants
   (under **OpenAlex**, the true all-time top-cited, returned directly by a sorted
   `cites:` query; under **Semantic Scholar**, the whole citation history when the
   offline corpus serves it or the seed's citer list is fully reachable live —
   see the "Data source" note), with **how many to show measured per-seed from
   the real citer pool** (an old classic maps out large, a young hot paper stays
   tight — the STOP rule in `services/graph/budget.py`); **Latest Publications**
   (light green) is the recent frontier — recent citers, per-year banded for even
   coverage, with the band's **start sized per-seed by a trained model**
   so an old classic's bands widen back to meet its landmark cluster instead of
   leaving a gap (see `src/ml_pipelines/latest_gap/`) — as a filterable relation of
   its own. Node size = citations; thick links = influential citations; a
   dashed ring = discovered by the teacher mid-chat. Click a node for
   details (TL;DR, abstract/PDF links, arXiv & Semantic Scholar category
   tags, figures, code & artifacts); **double-click to re-seed** on it —
   journal papers included. LaTeX math (`$…$`) renders throughout — titles,
   abstracts, lecture beats, answers, and figure captions — via KaTeX.
3. **Declutter** — Force ↔ Timeline layouts (x = publication date), relation
   on/off **filter chips**, a dual-knob **year slider** and a dual-knob
   **citation-count slider** (a log-scale min…max window over the papers on
   screen — a display filter, no re-query), drag-to-pin, focus-on-hover, and a
   **Refresh** that busts this seed's day-cached snapshot to re-fetch fresh from
   Semantic Scholar. **Hand-pick a scope** with the node selector:
   **alt-drag** a marquee to add papers to the teacher's scope (additive —
   several sweeps build one cluster), **shift-click** to add/remove one, and
   **alt-click** empty (or **Clear**) to reset. Picked papers ring cyan and the
   rest dim; the teacher then grounds only in your selection. Click the
   **Atlas** brand anytime to go home.
4. **Learn** (the 🎓 Assistant panel):
   - **Lectures** — the past → present → future arc, narrated over the
     graph **as you built it** (lectures never expand it — only the research
     agent does), each pinned to one kind of graph node so they don't overlap:
     "How we got here" (chronologically through the seed's **references**,
     ending AT the seed), "This paper's intuition" (the seed **alone** — it
     reads the paper's full text and teaches it in chapters with its real math,
     no detours to other papers), "What's evolved since" (the
     **landmark citers** onward through the work that built on it), and "The
     current frontier" (just the graph's **Latest Publications**). Each lecture
     is **grounded in the papers currently shown on the graph** — filter the
     graph, or hand-pick a cluster with the node selector (alt-drag), and you
     scope the lecture (and Q&A) to it. The chronological lectures are nudged to
     span the whole publication history — both ends, not just the oldest,
     most-cited papers. Lecture length is tunable too (`min_beats`/`max_beats`
     in the lecturer's config `extras`, default 7–12). Beats light up their
     papers and carry the papers' **real figures** inline — click to enlarge.
     The four mode buttons are **colour-coded to the graph nodes** they narrate
     (blue references / green landmarks / light-green latest / gold seed) and are
     **cached show/hide toggles** that generate in parallel: play one, then flip
     between them instantly (or start another while one still loads). The panel
     is **one surface with two views** — a playing lecture (its "Now playing"
     header + beats) or the Q&A chat; asking a question tucks the lecture away
     (still cached) so the two never pile up.
   - **Ask** — the research agent answers grounded in what it actually
     reads, streaming its tool steps live (read / expand / search / search
     your sources / show a figure). Answers render in full **Markdown + math**,
     and their inline `[n]` citations are **clickable** — click one to spotlight
     that paper on the graph, click it again to clear. (Lecture beats cite the
     same way.) Answers also cite their whole grounding set — click the bubble
     to re-light them all.
   - **No graph open?** The same panel is a chat straight over your uploaded
     library, cited by page.
5. **Your sources** (📚) — drop in PDFs (parallel, with live embedding
   progress) or paste URLs; scope any conversation to a subset of them.
6. **Sessions** (🗂) — save the workspace, reopen it later free of charge.
7. **Lost?** Hit the header's **?** for a guided coach-mark tour — it auto-runs
   once on first launch (the search surface) and once more on your first graph
   (the graph tools), spotlighting one control at a time; the bubble's title
   doubles as a jump select that skips straight to whichever tip you came
   back for.

---

## The codebase

The rewrite's first principle: **every package documents itself**. Start at
any folder's `README.md` — e.g. `src/atlas/agents/` (the crew, the
event protocol, the streaming bridge), `services/sources/` (hybrid retrieval:
FTS5 + vectors + RRF), `frontend/src/README.md` (the render-tree map), or
`frontend/src/store/` (what earns a Redux slice and what stays local).

Quality gates: `uv run nox` runs the whole repo's — pre-commit hooks (file
hygiene; ruff incl. Google-style docstring rules; a repo-local
no-single-letter-identifiers AST check, notebooks included; pydoclint for
Args/Returns completeness; the frontend's prettier + oxlint incl. JSDoc
completeness), strict mypy, pytest (`test/`, 419 offline tests), and Vitest
(`frontend/test/`, offline too) — plus `cd frontend && npm run build`
(strict tsc + Vite) for the type/build check.
