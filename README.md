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
[`arxiv`](https://pypi.org/project/arxiv/) package · SQLite. Runs locally on
your Mac.

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
- **`ARXIV_CATEGORIES`** — your subject "subscription", comma-separated.
  Defaults to `cs.LG,cs.AI,cs.CL,cs.CV`. Full list:
  <https://arxiv.org/category_taxonomy>.
- **`ARXIV_LOOKBACK_DAYS`** (default `2`) — how far back "the latest batch"
  reaches. Bump it if a run comes back empty (e.g. over a weekend).

### 2. Fetch papers

```bash
uv run python backend/run.py refresh
```

Fetches the latest papers in your categories, stores them, and summarizes all of
them (handy for a daily cron). Add `--no-summary` to fetch only — in the
dashboard you instead summarize each paper on demand via its **Get summary**
button.

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

Open <http://127.0.0.1:5000>. In the dashboard: **Refresh papers** requeries
arXiv for new papers, **Get summary** on any row summarizes that one paper on
demand, and the category chips filter the day's batch.

---

## NotebookLM

NotebookLM has no public API, so this can't auto-push into it. Click **Export
for NotebookLM** in the dashboard (or hit `/api/export/notebooklm`) to download a
clean Markdown digest plus a list of PDF links. In NotebookLM: **New notebook →
Add source → paste the Markdown** (or add the PDF links as website sources).

---

## Project layout

```
arxiv-digest/
├── pyproject.toml            # uv-managed backend deps
├── .env / .env.example       # config + Anthropic key (gitignored)
├── data/digest.db            # SQLite store (auto-created; gitignored)
├── backend/
│   ├── run.py                # CLI: serve | refresh
│   └── arxiv_digest/
│       ├── config.py         # all settings, from .env
│       ├── arxiv_client.py   # fetch recent papers from the arXiv API
│       ├── summarizer.py     # Claude summaries (cached by arXiv id)
│       ├── store.py          # SQLite persistence
│       ├── pipeline.py       # fetch → store → summarize
│       └── app.py            # Flask API + serves the built dashboard
└── frontend/                 # React + TS + Vite dashboard
    └── src/{App.tsx, api.ts, App.css}
```

## How fetching works

`arxiv_client.fetch_recent_papers()` builds a query like
`cat:cs.LG OR cat:cs.AI OR …`, asks arXiv for the newest submissions, and keeps
everything from the last `ARXIV_LOOKBACK_DAYS`. Papers are keyed by arXiv id, so
re-running never duplicates a paper or re-pays to summarize one.

## Notes & next steps

- **Automate the daily run:** add a `cron`/`launchd` job that runs
  `uv run python backend/run.py refresh` each morning.
- **Learn Node later:** the backend is Python today; porting it to Node is a
  great, well-scoped exercise once everything works.
- **Secrets:** `.env` is gitignored — never commit it.
