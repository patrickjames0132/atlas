# arXiv Digest

Turn the latest arXiv papers in the subjects you follow into an AI-summarized
daily dashboard.

It pulls recent papers straight from the **official arXiv API**, filtered to the
subject categories you choose, generates a short plain-English summary for each
with Claude, and shows them in a React dashboard — with one-click export of a
Markdown digest for **NotebookLM**.

```
┌──────────┐  arXiv API   ┌─────────┐   store   ┌──────────┐   Claude    ┌───────────┐
│  arXiv   │ ───────────▶ │ backend │ ────────▶ │  SQLite  │ ──────────▶ │ summaries │
│ (cs.LG…) │   (cat: …)   │ (Flask) │           │ digest.db│             │  cached   │
└──────────┘              └────┬────┘           └──────────┘             └───────────┘
                               │ /api
                               ▼
                       ┌───────────────┐
                       │ React + Vite  │  ← the dashboard you open in a browser
                       └───────────────┘
```

**Stack:** Python/Flask + uv · React + TypeScript + Vite · Claude (via the
`claude` CLI **or** the Anthropic API) · the
[`arxiv`](https://pypi.org/project/arxiv/) package · SQLite (+ FTS5 &
`sqlite-vec`) · local `sentence-transformers` embeddings for semantic search.
Runs locally on your Mac.

No Gmail, no Google Cloud, no OAuth. By default summaries run through the
**Anthropic API** (cheap Haiku 4.5) and **automatically fall back to the `claude`
CLI** under your Claude Pro/Max subscription if your API credits run out.

---

## Setup

`uv`, `Node.js`, and `Python 3.11+` are already installed on this machine.

### 1. Configure

```bash
cd ~/arxiv-digest
cp .env.example .env
```

Edit `.env`:

- **`SUMMARY_BACKEND`** / **`SUMMARY_FALLBACK_BACKEND`** — summaries try the
  primary backend, then switch to the fallback for the rest of the run if it
  fails (e.g. API credits run out). Defaults: `api` primary, `claude_cli`
  fallback.
  - `api` — Anthropic API, pay-as-you-go (~$0.0015/paper with Haiku 4.5). Set
    `ANTHROPIC_API_KEY` from <https://console.anthropic.com>. Deployable anywhere.
  - `claude_cli` — the `claude` CLI under your **Claude Pro/Max subscription**
    (no API billing; local-only; needs Claude Code installed + signed in via
    `claude` then `/login`). Uses Haiku via `CLAUDE_CLI_MODEL=haiku`.
- **`ARXIV_CATEGORIES`** — the *initial* subjects to follow, comma-separated
  (default `cs.LG,cs.AI,cs.CL,cs.CV`). This is only a seed: once the app is
  running you manage the set from the dashboard's **Categories** button, and the
  choice is saved in the database. Full list:
  <https://arxiv.org/category_taxonomy>.

There is no cap on how many papers a refresh pulls — the entire matching batch
is fetched. A wide date range across many categories can therefore be large and
slow (arXiv paginates ~100 results at a time).

### 2. Fetch papers

```bash
uv run python backend/run.py refresh                          # papers submitted today
uv run python backend/run.py refresh --start 2026-06-25       # a single day
uv run python backend/run.py refresh --start 2026-06-20 --end 2026-06-25   # a range
```

Pulls papers **submitted in the given date range** (default: today; `--end`
defaults to `--start`) in your categories, stores each under its own submission
day, and **embeds new papers for semantic search** (add `--no-embed` to skip).
Add `--no-summary` to skip summaries (the default in the dashboard, where you
summarize each paper on demand via its **Get summary** button); without it the
CLI also summarizes the batch, handy for a daily cron.

The first time you run with semantic search enabled, backfill embeddings for
papers already in your database with `uv run python backend/run.py embed` (see
[How search works](#how-search-works)).

### 3. Open the dashboard

**Development** (two terminals, hot-reloading frontend):

```bash
# Terminal 1 — API
uv run python backend/run.py serve            # http://127.0.0.1:5000

# Terminal 2 — dashboard
cd frontend && npm run dev                     # http://localhost:5173
```

Open <http://localhost:5173>. The Vite dev server proxies `/api/*` to Flask.

**Single-server** (after building the frontend once):

```bash
cd frontend && npm run build && cd ..
uv run python backend/run.py serve             # serves dashboard + API at :5000
```

Open <http://127.0.0.1:5000>. In the dashboard: the **Categories** button opens
a searchable picker for the full arXiv taxonomy — the subjects you choose are
the ones pulled from arXiv *and* offered as filters. Pick a **From / To** date
range to view its papers (if none have been pulled yet, you'll see a prompt to
fetch them), the **↻** button pulls the selected range's submissions in your
followed categories, **Get summary** on any row summarizes that one paper on
demand, the category chips filter the loaded batch, and long ranges are
paginated. The **search bar** does a **hybrid keyword + semantic** search over the
papers you've already pulled, scoped to the current date range — so you can search
by meaning ("teaching machines to see") or exact terms alike; see
[How search works](#how-search-works) below.

---

## NotebookLM

NotebookLM has no public API, so this can't auto-push into it. Click **Export
for NotebookLM** in the dashboard (or hit `/api/export/notebooklm`) to download a
clean Markdown digest plus a list of PDF links. In NotebookLM: **New notebook →
Add source → paste the Markdown** (or add the PDF links as website sources).

**Search-aware:** with a search active the button becomes **Export results** and
the digest contains only that search's hits (`/api/export/notebooklm?q=…`, hybrid
lexical + semantic, scoped to the date range) — capped at the same 100 results
the dashboard shows, which conveniently keeps a NotebookLM notebook focused.
Clear the search to export the whole date range again.

---

## Project layout

```
arxiv-digest/
├── pyproject.toml            # uv-managed backend deps
├── .env / .env.example       # config + Anthropic key (gitignored)
├── data/digest.db            # SQLite store (auto-created; gitignored)
├── backend/
│   ├── run.py                # CLI: serve | refresh | embed
│   └── arxiv_digest/
│       ├── config.py         # all settings, from .env
│       ├── arxiv_client.py   # fetch papers for a date range from the arXiv API
│       ├── taxonomy.py       # full arXiv category taxonomy (+ taxonomy.json)
│       ├── summarizer.py     # Claude summaries (cached by arXiv id)
│       ├── embeddings.py     # local sentence-transformers embeddings
│       ├── search.py         # hybrid lexical + semantic search (RRF fusion)
│       ├── store.py          # SQLite persistence (papers, settings, FTS5, vectors)
│       ├── pipeline.py       # fetch → store → embed → summarize
│       └── app.py            # Flask API + serves the built dashboard
└── frontend/                 # React + TS + Vite dashboard
    └── src/{App.tsx, CategoryPicker.tsx, api.ts, App.css}
```

## How fetching works

`arxiv_client.fetch_papers_in_range()` builds a query like
`(cat:cs.LG OR cat:cs.AI OR …) AND submittedDate:[YYYYMMDD0000 TO YYYYMMDD2359]`
— i.e. papers **submitted in that date range** (GMT) in your categories — and
stores each under its own submission day. There is no result cap; the whole
matching batch is fetched. Papers are keyed by arXiv id, so re-pulling never
duplicates a paper or re-pays to summarize one.

## How search works

The search bar (and `GET /api/search?q=&start=&end=`) is **hybrid** — it runs a
keyword search and a semantic search over the papers already in `digest.db`, then
blends the two ranked lists. So `automobile` still surfaces a paper that only says
"car", *and* an exact term like a method name or author still lands a direct hit.
Search is scoped to the selected **From / To** range; widen the range to search
more of your library.

**1. Lexical (keyword) — FTS5 + BM25.** SQLite's built-in full-text search. A
`papers_fts` virtual table holds an **inverted index** (word → the papers
containing it), kept in sync with `papers` by triggers. Text is lowercased,
tokenized (`unicode61`) and **stemmed** (`porter`) so variants collide
(`learning`/`learned` → `learn`); with a `*` prefix on each term, typing
`transform` also finds "transformer". Matches are ranked by **BM25**, a relevance
score from word statistics only — term frequency, how rare each term is, document
length. (A plain `LIKE` substring scan is the fallback if a SQLite build lacks
FTS5.)

**2. Semantic (meaning) — sentence-transformers + sqlite-vec.** Each paper's
title + abstract is embedded into a 384-dim **vector** with the local
[`all-MiniLM-L6-v2`](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2)
model — no API, no key, nothing leaves your machine. Vectors live in a
[`sqlite-vec`](https://github.com/asg017/sqlite-vec) virtual table (`papers_vec`)
inside the same `digest.db`. A query is embedded the same way, and sqlite-vec
returns its nearest neighbours by **cosine distance** — so conceptually-similar
papers match even with no shared words.

**3. Fusion — Reciprocal Rank Fusion (RRF).** The two lists are merged by
`score = Σ 1/(k + rank)` across each list a paper appears in (`k` = `ARXIV_RRF_K`,
default 60). RRF needs only each result's *rank*, not comparable scores, so it
fairly blends BM25 with cosine distance; a paper ranked highly by *both* rises to
the top. The dashboard tags each row `lexical`, `semantic`, or both, and shows
whether a search ran `hybrid` or fell back to `keyword`-only.

Embeddings are generated when papers are pulled. After first enabling this
feature (or changing the model) backfill the existing library once:

```bash
uv run python backend/run.py embed              # embed anything not yet indexed
uv run python backend/run.py embed --rebuild    # wipe + re-embed (e.g. new model)
```

Semantic search degrades gracefully: set `ARXIV_SEMANTIC=0` (or if the model /
`sqlite-vec` can't load) and search stays keyword-only with no other changes.

**Next: retrieval-augmented generation (RAG).** With embeddings in place, the
natural follow-on is answering questions *over* your library — retrieve the most
relevant papers for a question and have Claude synthesize an answer with
citations.

## Notes & next steps

- **Automate the daily run:** add a `cron`/`launchd` job that runs
  `uv run python backend/run.py refresh` each morning.
- **Learn Node later:** the backend is Python today; porting it to Node is a
  great, well-scoped exercise once everything works.
- **Secrets:** `.env` is gitignored — never commit it.
