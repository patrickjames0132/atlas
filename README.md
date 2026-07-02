# arXiv Atlas

**Explore how research papers connect — and (soon) have an AI teacher narrate
the story of how a field got here.**

Drop in a paper and Atlas renders a **Connected-Papers-style interactive graph**
of how it links to the literature — the papers it cites (its intellectual
ancestors), the papers that cite it (its descendants), and its nearest neighbors
by meaning. Then wander: double-click any node to re-center the graph on it and
keep exploring.

It connects to the academic-graph ecosystem **dynamically** — there's no local
corpus of papers to store (millions of papers are many TB; we leave that to the
people who already host it). The only thing kept on disk is a tiny cache of the
graphs you've already looked at.

> **Status:** v1.0 — the graph explorer is live. The AI teacher, Q&A, concept
> mindmaps, and audio lectures are on the roadmap — see
> **[OnePager.md](OnePager.md)** for the full vision and phase plan.

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
the `claude` CLI **or** the Anthropic API) for the upcoming AI-teacher features.
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
- **`ANTHROPIC_API_KEY`** / **`SUMMARY_BACKEND`** — used by the AI-teacher
  features (roadmap). Summaries can run through the Anthropic API (cheap Haiku
  4.5) or the `claude` CLI under a Claude Pro/Max subscription.

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
   from the arXiv hits, or paste an **arXiv id / URL** to jump straight in.
2. **Read the map** — 🟡 gold = the seed · 🔵 blue = **references** (papers it
   cites) · 🟢 green = **citations** (papers citing it) · 🟣 purple = **similar**
   (SPECTER2 neighbors). Node size = citation count; arrows show citation
   direction; thicker links mark "influential" citations.
3. **Declutter** (top-left panel):
   - **Relation filters** — toggle references / citations / similar on and off.
   - **Year range** — a dual slider to focus on an era (the seed always stays).
   - **Drag-to-pin** — drag a node to fix it in place; *Release* unpins all.
   - **Focus-on-hover** — hover a node to fade everything not connected to it.
4. **Traverse** — **double-click** any node (or use *Explore from here*) to
   re-seed the whole graph on that paper. Re-seeding works by Semantic Scholar
   id, so you can hop onto cited **journal** papers with no arXiv id and keep
   going. Every hop is cached, so backtracking is instant.

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
│   ├── run.py                   # CLI: serve | refresh | embed
│   └── arxiv_digest/
│       ├── config.py            # settings from .env (incl. Semantic Scholar)
│       ├── semantic_scholar.py  # S2 Academic Graph + Recommendations client
│       ├── graph.py             # assemble a paper's neighborhood graph
│       ├── cache.py             # tiny TTL cache for dynamic artifacts
│       ├── arxiv_client.py      # arXiv search (finds the seed paper)
│       ├── app.py               # Flask API + serves the built frontend
│       └── … (summarizer, taxonomy, and legacy digest modules)
└── frontend/                    # React + TS + Vite
    └── src/{GraphExplorer.tsx, api.ts, atlas.css, main.tsx}
```

*Legacy note:* the earlier "daily digest" era (local paper store, hybrid FTS5 +
`sqlite-vec` search, category pulls, NotebookLM export) still exists in the
backend — its modules currently power the arXiv seed search and are otherwise
dormant. They'll be retired as the v1.0 rewrite proceeds; see **OnePager.md**.

## Notes & next steps

- **The AI teacher** is the headline of the roadmap: Claude narrating the
  history and intuition of a field, synced to the graph, with follow-up Q&A —
  plus concept mindmaps and Podcastfy audio lectures. See **[OnePager.md](OnePager.md)**.
- **Secrets:** `.env` is gitignored — never commit it. Keys are optional; Atlas
  runs keyless (just rate-limited on Semantic Scholar).
