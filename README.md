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

**Stack:** Python/Flask + uv · [PydanticAI](https://ai.pydantic.dev) agents on
Claude · React + TypeScript (strict) + Vite + Redux Toolkit ·
[`react-force-graph-2d`](https://github.com/vasturiano/react-force-graph) ·
[OpenAlex](https://openalex.org) (citations) +
[Semantic Scholar Academic Graph API](https://api.semanticscholar.org/api-docs/) ·
[ar5iv](https://ar5iv.org) + pymupdf-mined open-access PDFs for figures/full text ·
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
environment variables, ever). Every field must be *present* and is validated at
startup by Pydantic, so a malformed value fails fast with a clear message — but
the API-key values may be left blank. For the **full value-by-value reference**
(every tunable, its default, and *why* it's there), see
**[docs/configuration.md](docs/configuration.md)**.

The two **data-source keys are completely optional** — Atlas explores the graph
fully without them, just on tighter public rate limits. The **Anthropic key is
the one that unlocks the AI teacher** (lectures, research Q&A, library chat); the
graph explorer runs fine without it, but the Assistant panel needs it.

- **`providers.s2.api_key`** — **optional.** A free
  [Semantic Scholar API key](https://www.semanticscholar.org/product/api) is
  recommended (the keyless pool is tight), but keyless works.
- **`providers.openalex.api_key`** — **optional.** OpenAlex (the citation
  source) runs keyless on its `mailto` polite pool ($0.10/day of metered search
  — plenty for browsing); a free key at
  [openalex.org/settings/api](https://openalex.org/settings/api) lifts it to
  $1/day. Set `providers.openalex.mailto` to your email either way.
- **`llm.providers.anthropic.api_key`** — **required to power the agents.** A
  [Claude API key](https://console.anthropic.com/settings/keys) drives the whole
  crew (lectures, research Q&A, library chat, query analysis); the per-agent
  model choices live under `llm.agents`. Anthropic is the only LLM provider
  today — **support for other providers is on the roadmap.**

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
   the graph's own note names which source is behind them; see
   [docs/citation-coverage.md](docs/citation-coverage.md) for how the two sources
   compare), with **how many to show measured per-seed from
   the real citer pool** (an old classic maps out large, a young hot paper stays
   tight — the STOP rule in `services/graph/budget.py`); **Latest Publications**
   (light green) is the recent frontier — recent citers, per-year banded for even
   coverage, with the band's **start sized per-seed from fitted constants**
   so an old classic's bands widen back to meet its landmark cluster instead of
   leaving a gap (see `services/graph/bands.py`) — as a filterable relation of
   its own. (Every term here — *landmark*, *band*, *tail edge*, the sizing
   rules — is defined once, with a worked example, in
   [docs/landmark-vocabulary.md](docs/landmark-vocabulary.md).) Node size =
   citations; thick links = influential citations; a
   dashed ring = discovered by the teacher mid-chat. Click a node for
   details (TL;DR, abstract/PDF links, arXiv & Semantic Scholar category
   tags, figures — mined straight from the open-access PDF for journal
   papers, tables and algorithms included — code & artifacts);
   **double-click to re-seed** on it — journal papers included. LaTeX math (`$…$`) renders throughout — titles,
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
   **Atlas** brand anytime to go home. By default the app **sizes each graph
   for you** (how many landmark citers to ship, where the Latest bands start —
   per seed); turn **"Size graphs automatically" off** in Settings ▸ Graph to
   have it ship everything it can and size the bands yourself, and each filter
   chip gains a **count slider** to trim how many of that relation you see.
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

For the project's direction and past, two living docs sit beside the code:
**[OnePager.md](OnePager.md)** (the vision, the full feature stack, and the
open backlog) and **[docs/history.md](docs/history.md)** (the complete shipped
record, version by version).
