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
>   embedding progress bars**, and a per-source scope picker for the agents.
> - **Sessions** save the whole workspace — graph, discovered papers, chat —
>   and restore with zero API calls.
>
> See **[OnePager.md](OnePager.md)** for the vision, the full feature stack,
> and the roadmap.

```
┌──────────┐  find seed   ┌─────────┐  citations         ┌──────────┐
│  search  │ ───────────▶ │ backend │ ─────────────────▶ │ OpenAlex │
│  (S2+LLM)│  (title/id)  │ (Flask) │  refs/similar/TLDR  └──────────┘
└──────────┘              └────┬────┘ ─────────────────▶ ┌──────────────────┐
                               │ /api/graph (thin cache) │ Semantic Scholar │
                               ▼                         └──────────────────┘
                     ┌───────────────────────┐
                     │  React + force graph  │  ← the interactive map you explore
                     └───────────────────────┘
```

Since **v4.0.0** the citation graph is a **hybrid**: OpenAlex supplies the
citation relations (its sorted `cites:` queries return a seed's landmark citers
directly — no recency bias), while Semantic Scholar keeps the seed resolve,
references, similar papers, and TL;DRs. The two are matched by DOI / arXiv id.

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
bootstrap: pinned tools, `uv sync`, and the frontend install + build. Without
mise, `uv` and `Node.js` installed any other way work fine too.

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
   badge marks papers whose whole neighborhood is cached. Optional filters:
   a publication-year window (1800 → now) and S2 **fields of study**.
2. **Read the map** — 🟡 seed · 🔵 references · 🟢 citations · 🌱 latest ·
   🟣 similar · 💗 found-by-search. Citers (from **OpenAlex**) split into two
   relations: **Field Landmarks** (green) are the all-time most-cited papers
   citing the seed — the historic giants, returned directly by a sorted `cites:`
   query (no recency bias, no mining), with **how many to show sized per-seed by
   a small trained model** (an old classic maps out large, a young hot paper
   stays tight — see `ml_pipelines/cite_budget/`); **Latest Publications** (light
   green) is the recent frontier — recent citers, per-year banded for even
   coverage, with the band's **start sized per-seed by a second trained model**
   so an old classic's bands widen back to meet its landmark cluster instead of
   leaving a gap (see `ml_pipelines/latest_gap/`) — as a filterable relation of
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
   Semantic Scholar. Click the **Atlas** brand anytime to go home.
4. **Learn** (the 🎓 Assistant panel):
   - **Lectures** — the past → present → future arc, narrated over the
     graph **as you built it** (lectures never expand it — only the research
     agent does), each pinned to one kind of graph node so they don't overlap:
     "How we got here" (chronologically through the seed's **references**,
     ending AT the seed), "This paper's intuition" (the seed **alone** — it
     reads the paper's full text and teaches it in chapters with its real math,
     no detours to other papers), "The landmark papers since" (the
     **landmark citers** onward through the work that built on it), and "The
     current frontier" (just the graph's **Latest Publications**). Each lecture
     is **grounded in the papers currently shown on the graph** — filter the
     graph and you scope the lecture. The chronological lectures are nudged to
     span the whole publication history — both ends, not just the oldest,
     most-cited papers. Lecture length is tunable too (`min_beats`/`max_beats`
     in the lecturer's config `extras`, default 7–12). Beats light up their
     papers and carry the papers' **real figures** inline — click to enlarge.
     The four mode buttons are **cached show/hide toggles** that generate in
     parallel: play one, then flip between them instantly (or start another, or
     ask a question, while one still loads in the background).
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

---

## The codebase

The rewrite's first principle: **every package documents itself**. Start at
any folder's `README.md` — e.g. `src/atlas/agents/` (the crew, the
event protocol, the streaming bridge), `services/sources/` (hybrid retrieval:
FTS5 + vectors + RRF), `frontend/src/README.md` (the render-tree map), or
`frontend/src/store/` (what earns a Redux slice and what stays local).

Quality gates: `uv run nox` runs the whole repo's — pre-commit hooks (file
hygiene; ruff incl. Google-style docstring rules; pydoclint for
Args/Returns completeness; the frontend's prettier + oxlint incl. JSDoc
completeness), strict mypy, pytest (`test/`, 328 offline tests), and Vitest
(`frontend/test/`, offline too) — plus `cd frontend && npm run build`
(strict tsc + Vite) for the type/build check.
