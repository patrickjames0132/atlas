# arXiv Atlas

**Explore how research papers connect — and have an AI teacher narrate the story
of how a field got here.**

Drop in a paper and Atlas renders a **Connected-Papers-style interactive graph**
of how it links to the literature — the papers it cites (its intellectual
ancestors), the papers that cite it (its descendants), and its nearest neighbors
by meaning. Then wander: double-click any node to re-center the graph on it and
keep exploring.

It connects to the academic-graph ecosystem **dynamically** — there's no local
corpus of papers to store (millions of papers are many TB; we leave that to the
people who already host it). The only thing kept on disk is a tiny cache of the
graphs you've already looked at.

> **Status:** v1.13 — the graph explorer **and a streaming AI teacher** are live:
> Claude narrates a lecture over the graph and lights up nodes in sync, and
> answers follow-up questions grounded in the papers on screen. The Q&A agent
> **reads the papers' actual full text** (via ar5iv), can **traverse to papers
> not yet on the graph** (`expand_node` — one hop of references / citations /
> similar work), and can **search all of Semantic Scholar** for off-graph work
> (`search_papers`, with a year filter, for recent/topical papers citation hops
> can't reach) before answering — a tool-use loop with live trace UI, read/hop/
> search budgets, and wall-clock guardrails. Discovered papers merge into the
> graph (a dashed "discovered" ring; search hits get their own pink "found by
> search" color). Each answer is a **clickable section** that re-lights the
> papers it drew on, just like a lecture beat. A **Timeline layout** arranges
> papers left→right by year (so the lecture sweeps through time), and the detail
> panel shows a paper's own **figures + captions** and links to both the abstract
> and the PDF. Seed search is **cache-first**: papers you've already seen appear
> instantly (and still work when the APIs are rate-limiting). You can also **bring
> your own sources** — upload a PDF/book or paste a URL and it's chunked, embedded
> **locally** (no API key; the text never leaves your machine), and made
> semantically searchable via sqlite-vec; the **teacher then searches your library
> in Q&A and cites it by page** ("*per your textbook, p.243…*"). You can also
> **chat with your library directly** — an "💬 Ask library" mode answers straight
> from your uploaded sources, no graph or seed search needed, optionally **scoped
> to one source**. Concept mindmaps
> and audio lectures follow — see **[OnePager.md](OnePager.md)** for the full
> vision and phase plan.

```
┌──────────┐  find seed   ┌─────────┐  graph/refs/cites/recs  ┌──────────────────┐
│  arXiv   │ ───────────▶ │ backend │ ──────────────────────▶ │ Semantic Scholar │
│  search  │  (title/id)  │ (Flask) │      (dynamic API)      │  Academic Graph  │
└──────────┘              └────┬────┘                         └──────────────────┘
                               │ /api/graph  (thin cache only)
                               ▼
                     ┌───────────────────────┐
                     │  React + force graph  │  ← the interactive map you explore
                     └───────────────────────┘
```

**Stack:** Python/Flask + uv · React + TypeScript + Vite ·
[`react-force-graph-2d`](https://github.com/vasturiano/react-force-graph) ·
[Semantic Scholar Academic Graph API](https://api.semanticscholar.org/api-docs/)
(the same data backbone Connected Papers uses) · the
[`arxiv`](https://pypi.org/project/arxiv/) package for seed search · Claude (via
the `claude` CLI **or** the Anthropic API) for the AI-teacher lecture + Q&A.
Runs locally on your Mac.

---

## Setup

`uv`, `Node.js`, and `Python 3.11+` are already installed on this machine.

### 1. Configure

```bash
cd ~/arxiv-digest
cp .env.example .env
```

Edit `.env` (everything here is **optional** — Atlas works with no keys, just
more slowly):

- **`S2_API_KEY`** — a free [Semantic Scholar API key](https://www.semanticscholar.org/product/api).
  Strongly recommended: the unauthenticated pool is tight and graph builds will
  occasionally hit rate limits without it (the client backs off and retries, and
  snapshots are cached, so it still works — just less snappily).
- **`ANTHROPIC_API_KEY`** / **`TEACHER_BACKEND`** — power the AI teacher
  (lecture + Q&A). It runs through the Anthropic API (**`TEACHER_BACKEND=api`**,
  needs the key) or the `claude` CLI under a Claude Pro/Max subscription
  (**`TEACHER_BACKEND=claude_cli`**, no API billing).

### 2. Build the frontend & run

**Single-server** (serves the built dashboard + API together):

```bash
cd frontend && npm install && npm run build && cd ..
uv run python backend/run.py serve            # http://127.0.0.1:5000
```

**Development** (two terminals, hot-reloading frontend):

```bash
# Terminal 1 — API
uv run python backend/run.py serve            # http://127.0.0.1:5000

# Terminal 2 — dashboard
cd frontend && npm run dev                     # http://localhost:5173
```

The Vite dev server proxies `/api/*` to Flask.

---

## Using it

1. **Search a paper** — type a title (e.g. *Attention Is All You Need*) and pick
   from the hits, or paste an **arXiv id / URL** to jump straight in. Papers
   you've seen on previous graphs appear **instantly from the local cache**
   (above the live arXiv results); an **instant** badge marks papers whose
   whole neighborhood is cached — those explore without touching the API at
   all, rate limits be damned.
2. **Read the map** — 🟡 gold = the seed · 🔵 blue = **references** (papers it
   cites) · 🟢 green = **citations** (papers citing it) · 🟣 purple = **similar**
   (SPECTER2 neighbors). Node size = citation count; arrows show citation
   direction; thicker links mark "influential" citations. **Click a node** for a
   detail panel — TL;DR, the paper's own **figures + captions** (pulled from
   [ar5iv](https://ar5iv.org) when available), and links to the **abstract** and
   the **PDF**.
3. **Declutter** (top-left panel):
   - **Layout** — toggle **Force** (organic force-directed) ↔ **Timeline** (x =
     publication date — year + month, so papers sit between the yearly gridlines;
     oldest left; papers spread into citation threads through time). In Timeline,
     narrowing the year slider zooms into that span.
   - **Relation filters** — toggle references / citations / similar on and off.
   - **Year range** — a dual-thumb slider to focus on an era (the seed always stays).
   - **Drag-to-pin** — drag a node to fix it in place; *Release* unpins all.
   - **Focus-on-hover** — hover a node to fade everything not connected to it.
4. **Traverse** — **double-click** any node (or use *Explore from here*) to
   re-seed the whole graph on that paper. Re-seeding works by Semantic Scholar
   id, so you can hop onto cited **journal** papers with no arXiv id and keep
   going. Every hop is cached, so backtracking is instant.
5. **Learn from the AI teacher** (right panel):
   - **"How we got here"** — a chronological lecture across the neighborhood,
     from the oldest references through the seed to the work it spawned. Beats
     stream in one at a time, and the papers each beat is about **light up** on
     the graph in sync.
   - **"This paper's intuition"** — a deep-dive on the seed paper itself (what it
     solved, the core idea, why it works), using the neighbors for contrast.
   - **Ask** — type a question and get a streamed answer **grounded in the papers
     on screen**; the papers it draws from light up. Follow-ups keep context.

   The teacher uses Claude through the same dual backend as summaries — the
   `claude` CLI (Pro/Max subscription, no API billing) or the Anthropic API. Set
   `TEACHER_BACKEND=claude_cli` to prefer the subscription path.

---

## How the graph is built

`graph.build_graph(seed)` assembles a neighborhood from the
[Semantic Scholar Academic Graph + Recommendations APIs](https://api.semanticscholar.org/api-docs/):

- **Seed details** are hydrated through `POST /paper/batch` — deliberately, not
  the single-paper GET, which is throttled hardest for unauthenticated callers.
  A spike against the live API confirmed batch returns everything we need
  (title, abstract, `tldr`, `externalIds.ArXiv`, SPECTER2 embedding) and isn't
  rate-limited the same way.
- **References** (`/paper/{id}/references`) and **citations**
  (`/paper/{id}/citations`) become the directed edges.
- **Similar papers** come from the **recommendations** endpoint
  (`forpaper?from=all-cs`) — embedding-based neighbors.
- Nodes are deduped by S2 paperId; edges are tagged `reference | citation |
  similar`. The whole snapshot is cached in `data/digest.db` (a small key→JSON
  `cache` table) with a 1-day TTL, so repeat exploration stays fast and polite.

Seed lookup accepts either an **arXiv id** (`ARXIV:1706.03762`) or a raw **S2
paperId** (how re-seeding on any node works).

---

## Project layout

```
arxiv-digest/                    # (repo name predates the "Atlas" rename)
├── OnePager.md                  # product vision, feature stack & phase roadmap
├── pyproject.toml               # uv-managed backend deps
├── .env / .env.example          # optional keys (S2, Anthropic) — .env gitignored
├── data/digest.db               # thin cache (graph snapshots); gitignored
├── backend/
│   ├── run.py                   # click CLI: serve, ingest, sources, …
│   └── arxiv_digest/
│       ├── config.py            # settings from .env (incl. Semantic Scholar)
│       ├── semantic_scholar.py  # S2 Academic Graph + Recommendations client
│       ├── graph.py             # assemble a paper's neighborhood graph
│       ├── cache.py             # tiny TTL cache for dynamic artifacts
│       ├── arxiv_client.py      # arXiv seed search (finds the paper to map)
│       ├── search.py            # seed search: live arXiv + instant local-cache
│       ├── teacher.py           # streaming AI lecture + agentic Q&A (dual backend)
│       ├── fulltext.py          # full paper text from ar5iv for the Q&A agent (cached)
│       ├── figures.py           # paper figures + captions from ar5iv (cached)
│       ├── taxonomy.py          # arXiv category taxonomy (dormant; for future use)
│       └── app.py               # Flask API (incl. /api/lecture, /api/ask) + frontend
└── frontend/                    # React + TS + Vite
    └── src/{GraphExplorer.tsx, Teacher.tsx, api.ts, atlas.css, main.tsx}
```

*Legacy note:* the earlier "daily digest" era (local paper store, hybrid FTS5 +
`sqlite-vec` search, category pulls, NotebookLM export) was **retired in v1.4.0** —
its modules, routes, and settings are gone. `taxonomy.py` is kept **dormant** for
near-term features (graph filtering, topic-bridging); see **OnePager.md**.

## Notes & next steps

- **The AI teacher** (lecture + Q&A) is **live** — Claude narrates the history
  and intuition of a field, synced to the graph, and Q&A answers are grounded
  in the papers' **actual full text** (read via a tool-use loop). Next up:
  **agentic graph traversal + topic search** (Phase 3c) so the agent can pull
  in papers beyond the visible neighborhood, plus concept mindmaps and
  Podcastfy audio lectures. See **[OnePager.md](OnePager.md)**.
- **Secrets:** `.env` is gitignored — never commit it. Keys are optional; Atlas
  runs keyless (just rate-limited on Semantic Scholar).
