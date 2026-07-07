# CLAUDE.md — working agreement for this repo

Instructions for Claude Code when working in `~/PyCharmProjects/atlas`. Read this first;
it captures how we collaborate so you don't have to re-derive it each session.

## What this project is

**arXiv Atlas** — a Connected-Papers-style interactive citation/similarity graph
with (on the roadmap) an AI teacher that narrates the history and intuition of a
field. It connects to **Semantic Scholar** dynamically instead of storing a paper
corpus locally. The repo is still named `arxiv-digest` (it began as a daily
digest app; that era is being retired).

- **Vision, feature stack, and phase roadmap live in [OnePager.md](OnePager.md).**
  Keep it current. Read it to understand where we are and what's next.
- Backend: Python/Flask + uv (`src/atlas/`, standard src-layout,
  installed editable). Frontend: React + TS +
  Vite (`frontend/`). Graph rendering via `react-force-graph-2d`.

## How we work together — the loop

For each feature, follow this cycle:

1. **Build** the feature. Run `npm run build --prefix frontend` to typecheck the
   frontend; verify backend changes with a quick script or the Flask test client.
   Run the whole backend quality gate with **`uv run nox`** (see below) before
   handing off.
2. **Hand off for testing** — Patrick tests it **in the browser himself** first.
   Give him specific things to check. **Do NOT commit until he approves.**
3. On approval, **update the docs**: `README.md` and `OnePager.md` (tick roadmap
   boxes, note what shipped).
4. **Commit, tag, and push** (details below).

Don't skip ahead: no committing before the browser test, no starting the next
phase without a green light. Patrick is hands-on and likes to eyeball UX before
it's locked in.

## The `todos.md` inbox

Patrick brainstorms on the fly while I'm building, so `todos.md` at the repo root
is a scratch **inbox** — not a durable list. When he points me at it (or brings
it up at the start of a session), I:

1. **File** each item into `OnePager.md` — feature ideas into the roadmap
   ("Enhancements & tech debt", or a new phase where it fits) so OnePager stays
   the single source of truth.
2. **Clear** each item out of `todos.md` as I file it, leaving it an empty inbox
   (just the `TODOs:` header) for the next round.

OnePager wins — its roadmap boxes get ticked as we ship. `todos.md` is gitignored
scratch; never treat leftover items there as authoritative.

## Release mechanics

- **Versioning:** SemVer. **`v1.0.0`** is the arXiv Atlas pivot (the graph
  explorer replacing the old digest). From here: new feature = **minor**
  (`1.0.0` → `1.1.0`), bug fix = **patch**, breaking change = **major**. Bump
  `version` in `pyproject.toml`, then run `uv lock`. (History: the `0.x` line was
  the earlier "daily digest" era, ending at `v0.11.0`.)
- **Commit:** stage files **explicitly**. End
  the message with a `Co-Authored-By` trailer naming **the Claude model actually
  writing the commit** (don't copy an old commit's trailer verbatim), e.g.:

  ```
  Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
  ```
- **Tag in lockstep:** create an **annotated** tag `vX.Y.Z` matching the
  `pyproject.toml` version.
- **Push:** `git push origin main --follow-tags`.

The repo is **private** (`github.com/patrickjames0132/arxiv-digest`), default
branch `main`.

## Code conventions

- **No single-letter identifiers.** Name every variable, parameter, loop target,
  and generic type parameter for what it *holds*, in both the backend and the
  frontend — `node` not `n`, `event` not `e`, `query` not `q`, `top_k` not `k`,
  `Item` not `T`. This applies to tight scopes too (`.map((node) => …)`,
  `catch (error)`, `(prev) => …` in a `setState` updater). The exceptions are
  external property names we don't own (e.g. react-force-graph's `node.x`/`.y`,
  a paper's `_s`/`_t` endpoint fields) and canvas coordinates where a longer
  name reads worse — but a *local* coordinate still gets a real name (`lineX`,
  not `x`). Established two- to three-letter shorthands already in the code
  (`ctx`, `fg`, `lo`/`hi`, `aid`, `err`, `msg`, `buf`, `frac`) are fine; the
  rule is specifically about single letters. The whole codebase was swept clean
  of them once — keep it that way, don't reintroduce them.

## Caveats — read before committing

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
- **Run backend:** `uv run atlas serve` (Python 3.14 in `.venv`; the
  console script comes from the editable src-layout install — `cli.py`).
- **Logs:** `create_app()` logs to the console *and* a rotating file,
  `data/atlas.log` (5MB × 3 backups, gitignored with the rest of `data/`).
  Useful for after-the-fact debugging of agent runs (e.g. an S2 429 or search
  failure the UI only shows as a failed trace chip) — `grep` it for `WARNING`/
  `ERROR` after reproducing.
- **Quick backend checks:** `uv run python -c "from atlas.app import app; ..."`
  (no path shims needed — the package is installed) and Flask's
  `app.test_client()` — avoid hammering the live S2 API in tests.
- Don't re-hit the live API repeatedly while iterating; it throttles the IP
  (shared with the browser).

## Quality gate — `uv run nox`

**`uv run nox`** runs the whole backend gate in one shot — four sessions defined
in `noxfile.py`, all reusing the uv env (no per-session installs):

- **`precommit`** — every pre-commit hook (`.pre-commit-config.yaml`): file
  hygiene + **ruff** lint (config in `pyproject.toml`).
- **`mypy`** — type-checks `src/atlas`, **strict since v1.21.1**: no
  `disable_error_code` entries and `check_untyped_defs = true`. Keep it that way —
  new code must type-check clean; don't reintroduce disabled codes. At SDK
  boundaries prefer isinstance narrowing on real types (see `teacher/agentic.py`)
  over `getattr` duck-typing, and use `flask.typing.ResponseReturnValue` for
  views that return `(body, status)` tuples.
- **`tests`** — `pytest` over `test/`, which **mirrors `src/atlas/`**
  (105 offline tests; no live arXiv/S2/Anthropic calls, ever). Shared fixtures
  in `test/conftest.py`: autouse temp-DB isolation (tests can't touch real
  `data/`), `fake_claude` (a scripted Anthropic client built from **real SDK
  event objects** — use it for anything agentic), and `stub_embeddings`
  (deterministic hash embedder, no torch). Put new tests in the folder matching
  the module under test; pass args through with `uv run nox -s tests -- -k foo`.
- **`security`** — **Trivy** filesystem scan; **skips cleanly when `trivy`
  isn't on PATH**, so the gate stays green locally without it (install Trivy to
  enable).

Run a single session with `uv run nox -s <name>` (e.g. `-s mypy`).
