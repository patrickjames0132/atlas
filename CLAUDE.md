# CLAUDE.md — working agreement for this repo

Instructions for Claude Code when working in `~/PyCharmProjects/atlas`. Read this first;
it captures how we collaborate so you don't have to re-derive it each session.

## What this project is

**arXiv Atlas** — a Connected-Papers-style interactive citation/similarity graph
with (on the roadmap) an AI teacher that narrates the history and intuition of a
field. It connects to **Semantic Scholar** dynamically instead of storing a paper
corpus locally. The repo is named `atlas` on GitHub (renamed 2026-07-17 from
`arxiv-digest`, its daily-digest-era name; old remote URLs redirect).

- **Vision, feature stack, and the open Backlog live in [OnePager.md](OnePager.md).**
  Keep it current. Read it to understand where we are and what's next. The
  shipped record (every shipped item's full story + version tag) lives in
  **[docs/history.md](docs/history.md)**; the notable-bugs log in
  **[docs/bugs.md](docs/bugs.md)** — split out 2026-07-16 so the OnePager stays
  a working document.
- Backend: Python/Flask + uv (`src/atlas/`, standard src-layout,
  installed editable). Frontend: React + TS +
  Vite (`frontend/`). Graph rendering via `react-force-graph-2d`.

## Session start — bootstrap first

**Before anything else, `git pull`.** Sessions may start on a stale checkout
(work happens from more than one machine), and running setup or the config
drift check against yesterday's tree defeats the point — pull first so the
steps below see the current `main`.

**Then run the setup script**: `bin\setup.bat` on
Windows, `bin/setup.sh` on macOS/Linux. It installs the toolchain pinned in
`.tool-versions` via **mise** (python, uv, nodejs, trivy — mise reads the
asdf-format file but, unlike asdf, works on Windows too), then
`uv sync --all-groups`s the backend (all dependency groups, so the notebook
`research` group survives the sync) and `npm install` + `npm run build`s the frontend. It's cheap when
everything is already current, and it prevents a whole class of stale-env
surprises (missing node modules, an out-of-date lockfile, nox silently
skipping the Trivy scan).

**Then check `config.json` against `config.example.json`.** `config.json` is the
real settings file and is **gitignored**, so it drifts from the tracked template
whenever a new setting lands. At session start, diff the two — any key present in
`config.example.json` but missing from `config.json` (or a shape that no longer
matches) means the local file is stale: flag it and fill in the gap (carrying
over the example's default) before doing anything that depends on config. Don't
touch `config.example.json` to match `config.json` — the template leads, the
local file follows.

## How we work together — the loop

For each feature, follow this cycle:

0. **Branch off `main` for a major feature** — before starting a substantial
   feature/ticket, cut a fresh branch from an up-to-date `main`
   (`git switch -c <short-feature-name> main`). All the work below happens on
   that branch, keeping `main` clean and tidy. **Skip the branch for lightweight,
   doc-only changes** — updating READMEs, other markdown, `CLAUDE.md`,
   `OnePager.md`, or `docs/` (e.g. filing `todos.md`, moving a shipped item to
   `docs/history.md`) — those commit straight to `main`.
1. **Build** the feature. Run `npm run build --prefix frontend` to typecheck the
   frontend; verify backend changes with a quick script or the Flask test client.
   Run the whole quality gate — backend *and* frontend — with **`uv run nox`**
   (see below) before handing off.
2. **Hand off for testing** — Patrick tests it **in the browser himself** first.
   Give him specific things to check. **Do NOT commit until he approves.**
3. On approval, **update the docs**: `README.md`, plus the OnePager/history
   split — **move the shipped item's entry out of `OnePager.md`'s Backlog and
   into `docs/history.md`'s matching theme section**, ticked `[x]` and keeping
   its full story + version tag (history entries stay verbatim; the Backlog
   only ever holds open work). If a **notable bug** was found & fixed along the
   way — non-obvious root cause, surprising repro, a lesson worth keeping — add
   an entry to **`docs/bugs.md`** (newest-first; see its
   header for the format). It has two halves: **Ours** (we wrote it, we fixed
   it) and **Upstream** (a provider's data/service is wrong — we can only work
   around it, so the entry justifies code that looks paranoid and stops a later
   cleanup deleting the guard). File by *where the root cause lives*, not who
   noticed it.
   Small, obvious fixes don't need one — the commit message is enough.
4. **Commit on the branch, merge into `main`, tag, and push** (details below) —
   commit the approved work on the feature branch, merge it back into `main`,
   then tag and push in lockstep. The feature branch can be deleted once merged.

Don't skip ahead: no committing before the browser test, no starting the next
phase without a green light. Patrick is hands-on and likes to eyeball UX before
it's locked in.

## The `todos.md` inbox

Patrick brainstorms on the fly while I'm building, so `todos.md` at the repo root
is a scratch **inbox** — not a durable list. When he points me at it (or brings
it up at the start of a session), I:

1. **File** each item into `OnePager.md`'s Backlog — into the theme section
   where it fits ("Enhancements & tech debt", "UI & rendering polish", …) so
   the OnePager stays the single source of truth for open work.
2. **Clear** each item out of `todos.md` as I file it, leaving it an empty inbox
   (just the `TODOs:` header) for the next round.

OnePager wins — its Backlog items move to `docs/history.md` as we ship.
`todos.md` is gitignored scratch; never treat leftover items there as
authoritative.

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
- **Merge into `main`:** the approved work is built on a feature branch (see the
  loop's step 0); merge it back into `main` before tagging so the tag lands on
  `main`. Delete the feature branch once merged.
- **Tag in lockstep:** create an **annotated** tag `vX.Y.Z` matching the
  `pyproject.toml` version, on the merge commit.
- **Push:** `git push origin main --follow-tags`.

The repo is **private** (`github.com/patrickjames0132/atlas`), default
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
  of them once — keep it that way, don't reintroduce them. **Machine-enforced
  since v5.3.0**: a pre-commit hook (`bin/check_identifiers.py`, an AST walker)
  fails the gate on any single-letter *binding* in `.py` files and `.ipynb`
  code cells alike (`_` as a pure discard is the one allowed single character;
  attribute reads are out of scope).
- **The in-app help tracks the UI.** The frontend teaches itself in three
  places: the guided tour's step text (`frontend/src/tour/steps.ts`), the
  one-line gesture/hint lines inside components (e.g. GraphControls'
  `select-hint` and `ctrl-hint`), and control tooltips (`title=`). When a
  change alters what a component *does* — a new gesture, a button's behavior,
  a control appearing/disappearing — **update every help surface that
  describes it in the same change**, or the tour confidently teaches the old
  UI. (Rule born 2026-07-17: the Esc clear-all shipped while the tour still
  taught alt-click-empty as the only clear.)
- **Every package has a README, kept current.** A new package — backend or
  frontend, nested sub-packages included (e.g. `graph/canvas/`,
  `teacher/transcript/`) — ships **with its own `README.md`** telling that
  package's full story (what it is, design decisions worth knowing, who uses
  it, how it's verified — match the established README voice). And when a
  code change alters a package's behavior, structure, or contracts,
  **refactor its README in the same change** — including any *other* README
  that names the moved/changed thing (`src/README.md`'s render-tree map,
  cross-references like `notation/README.md`). `frontend/src/README.md`'s
  claim that "every folder has its own README" must stay true.

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

## Quality gate — `uv run nox` (backend + frontend)

**`uv run nox`** runs the whole repo's gate in one shot — five sessions defined
in `noxfile.py`, all reusing the uv env (no per-session installs):

- **`precommit`** — every pre-commit hook (`.pre-commit-config.yaml`): file
  hygiene + **ruff** lint (config in `pyproject.toml`; includes the
  **pydocstyle `D` rules, Google convention** — every module/class/function
  must carry a docstring; D205 deliberately off, the house style opens with
  flowing paragraphs) + **pydoclint** (docstring *completeness*: Args match
  the signature, Returns where a value comes back — config in
  `[tool.pydoclint]`; its raises-checks are off because the house style
  documents *propagated* exceptions too) + the repo-local
  **no-single-letter-identifiers** hook (`bin/check_identifiers.py` — see
  "Code conventions" above; covers `.py` and `.ipynb`, ruff has no
  min-name-length rule) + the **frontend's format & lint** —
  prettier (config in `frontend/.prettierrc.json`, scoped to
  `src/**/*.{ts,tsx,css}` + `test/` + `vite.config.ts`; READMEs and the JSONC
  tsconfigs stay hand-formatted) and oxlint (now incl. **jsdoc completeness
  rules**: a documented function's `@param`/`@returns` must be complete —
  presence isn't machine-checkable in oxlint, so JSDoc-on-every-function
  stays a convention, swept once 2026-07-10), as local hooks running the
  frontend's own npm scripts (they need `frontend/node_modules` — the
  session-start `bin/setup` installs it). Prettier fixes in place like ruff
  `--fix`: a reformat fails the run so the changes get restaged.
- **`mypy`** — type-checks `src/atlas`, **strict since v1.21.1**: no
  `disable_error_code` entries and `check_untyped_defs = true`. Keep it that way —
  new code must type-check clean; don't reintroduce disabled codes. At SDK
  boundaries prefer isinstance narrowing on real types (see `teacher/agentic.py`)
  over `getattr` duck-typing, and use `flask.typing.ResponseReturnValue` for
  views that return `(body, status)` tuples.
- **`tests`** — `pytest` over `test/`, which **mirrors `src/atlas/`**
  (491 offline tests; no live arXiv/S2/Anthropic calls, ever). Shared fixtures
  in `test/conftest.py`: autouse temp-DB isolation (tests can't touch real
  `data/`), `fake_claude` (a scripted Anthropic client built from **real SDK
  event objects** — use it for anything agentic), and `stub_embeddings`
  (deterministic hash embedder, no torch). Put new tests in the folder matching
  the module under test; pass args through with `uv run nox -s tests -- -k foo`.
- **`vitest`** — the frontend suite: **Vitest** (+ RTL/jsdom) over
  `frontend/test/`, which **mirrors `frontend/src/`**; fully offline, node
  environment by default with per-file `// @vitest-environment jsdom` opt-in,
  no test globals (import from `vitest` explicitly). Skips cleanly without
  npm. See `frontend/test/README.md`; pass args through with
  `uv run nox -s vitest -- -t name`.
- **`security`** — **Trivy** filesystem scan; **skips cleanly when `trivy`
  isn't on PATH**, so the gate stays green locally without it. Trivy is pinned
  in `.tool-versions`, so the session-start `bin/setup` script installs it via
  mise — after bootstrap the scan should actually run, not skip.

Run a single session with `uv run nox -s <name>` (e.g. `-s mypy`).
