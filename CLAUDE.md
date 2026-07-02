# CLAUDE.md — working agreement for this repo

Instructions for Claude Code when working in `~/arxiv-digest`. Read this first;
it captures how we collaborate so you don't have to re-derive it each session.

## What this project is

**arXiv Atlas** — a Connected-Papers-style interactive citation/similarity graph
with (on the roadmap) an AI teacher that narrates the history and intuition of a
field. It connects to **Semantic Scholar** dynamically instead of storing a paper
corpus locally. The repo is still named `arxiv-digest` (it began as a daily
digest app; that era is being retired).

- **Vision, feature stack, and phase roadmap live in [OnePager.md](OnePager.md).**
  Keep it current. Read it to understand where we are and what's next.
- Backend: Python/Flask + uv (`backend/arxiv_digest/`). Frontend: React + TS +
  Vite (`frontend/`). Graph rendering via `react-force-graph-2d`.

## How we work together — the loop

For each feature, follow this cycle:

1. **Build** the feature. Run `npm run build --prefix frontend` to typecheck the
   frontend; verify backend changes with a quick script or the Flask test client.
2. **Hand off for testing** — Patrick tests it **in the browser himself** first.
   Give him specific things to check. **Do NOT commit until he approves.**
3. On approval, **update the docs**: `README.md` and `OnePager.md` (tick roadmap
   boxes, note what shipped).
4. **Commit, tag, and push** (details below).

Don't skip ahead: no committing before the browser test, no starting the next
phase without a green light. Patrick is hands-on and likes to eyeball UX before
it's locked in.

## Release mechanics

- **Versioning:** SemVer. **`v1.0.0`** is the arXiv Atlas pivot (the graph
  explorer replacing the old digest). From here: new feature = **minor**
  (`1.0.0` → `1.1.0`), bug fix = **patch**, breaking change = **major**. Bump
  `version` in `pyproject.toml`, then run `uv lock`. (History: the `0.x` line was
  the earlier "daily digest" era, ending at `v0.11.0`.)
- **Commit:** stage files **explicitly** (see the config.py caveat below). End
  the message with:

  ```
  Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
  ```
- **Tag in lockstep:** create an **annotated** tag `vX.Y.Z` matching the
  `pyproject.toml` version.
- **Push:** `git push origin main --follow-tags`.

The repo is **private** (`github.com/patrickjames0132/arxiv-digest`), default
branch `main`.

## Caveats — read before committing

- **`backend/arxiv_digest/config.py` has an intentional LOCAL change** that must
  **never** be committed: `FLASK_PORT` is hardcoded to `8000` for Patrick's local
  setup (the committed value is `int(os.getenv("FLASK_PORT", "5000"))`). It shows
  as `M config.py` in every `git status`. When a real config change *does* need
  committing (e.g. new settings), temporarily restore the committed `FLASK_PORT`
  line, commit, then re-apply the local `= 8000` override. Otherwise just leave
  config.py out of the commit.
- **Secrets:** `.env` is gitignored — never commit it. `.env.example` holds only
  placeholders. All API keys (`S2_API_KEY`, `ANTHROPIC_API_KEY`, etc.) are
  optional; the app runs keyless (just rate-limited on Semantic Scholar).
- **Don't commit** `data/` (the SQLite cache) or `frontend/dist/` — both
  gitignored.

## Technical notes

- **Semantic Scholar rate limits are real.** The single-paper GET (`/paper/{id}`)
  429s almost immediately unauthenticated — hydrate details through
  `POST /paper/batch` instead. Recommendations need `from=all-cs` (the default
  "recent" pool returns nothing for older seeds). Graph snapshots are cached in
  `data/digest.db` (`cache` table, 1-day TTL). Encourage setting `S2_API_KEY`.
- **Run backend:** `uv run python backend/run.py serve` (Python 3.14 in `.venv`).
- **Quick backend checks:** `uv run python -c "import sys; sys.path.insert(0,'backend'); from arxiv_digest.app import app; ..."`
  and Flask's `app.test_client()` — avoid hammering the live S2 API in tests.
- Don't re-hit the live API repeatedly while iterating; it throttles the IP
  (shared with the browser).
