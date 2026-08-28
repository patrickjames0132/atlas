# First run — scoping the options

*Written 2026-08-28, scoping the Reach & access ticket "Make first-run possible
for someone who is not a developer." Nothing here is built yet. This exists so
the build decision is made once, with numbers, instead of re-argued each time
the ticket comes up.*

Today's path to a running Atlas: install mise → it installs Python 3.14, uv,
Node and trivy → `uv sync --all-groups` → `npm install && npm run build` →
`uv run atlas serve`. Reasonable for the person who wrote it. A wall for a
student who wants to learn something.

## The finding that reframes the question

**The install is 1.0 GB, and the app uses almost none of it.** Measured on
macOS, 2026-08-28:

| Install | Size |
| --- | --- |
| Today's `.venv` (`uv sync --all-groups`) | **1.0 GB** |
| Core only — Flask, Pydantic, PydanticAI, the vendor SDKs, sqlite-vec, huggingface-hub | **83 MB** |
| Core + PyMuPDF (PDF figure mining) | 137 MB |
| Core + PyMuPDF + DuckDB (the S2 corpus) | 181 MB |

The gap is `torch` (418 MB on its own) and what it drags with it —
`transformers`, `scipy`, `sympy`, `numpy`. On **Linux** it is worse than the
table shows: the lockfile resolves 37 `nvidia-*` CUDA packages there, which is
why CI sets `ATLAS_SKIP_TORCH=1` rather than pay for them.

None of it is needed to explore a graph or hear a lecture. `torch` arrives via
`sentence-transformers`, which is imported in exactly one place —
`services/sources/embeddings.py:82`, inside `_get_model`, lazily — and serves
only **search over your own uploaded sources**. Likewise `fitz` (PyMuPDF, 58 MB,
and AGPL) is lazy in `services/pdf/floats.py`, and `duckdb` (43 MB) is imported
only by the two S2-corpus modules.

Three dependencies are worse than optional: **`scikit-learn`, `joblib` and
`numpy` are declared in `pyproject.toml` and imported nowhere in the repo.**
They are leftovers from the `ml_pipelines/`+`research/` plumbing deleted
2026-07-22. (`torch` is declared directly for a real reason — routing the
Windows build to the CUDA index — not because anything imports it.)

**So the first move is the same whichever distribution shape wins:** make the
heavy capabilities optional extras. It shrinks every option below by an order
of magnitude, and it is the only item here that is pure subtraction.

## What "not a developer" actually has to get past

Four separate walls, and they are not equally hard:

1. **A toolchain** — Python 3.14, uv, Node, mise. The one everybody thinks of.
2. **A build step** — `npm run build`, because `frontend/dist` is gitignored.
3. **Config** — *less broken than the ticket assumes.* `load_settings` already
   creates a missing default `config.json` from the tracked example
   (`config.py:865`), so a fresh **checkout** boots keyless with no config
   step. But it is anchored to `PROJECT_ROOT = parents[2]` of the package
   file, which for an installed wheel is `site-packages/` — so config
   discovery genuinely is broken for every option except "clone the repo."
4. **Credentials** — needed for the teacher, not the explorer. Since v7.14.0
   the app runs with none.

## The three options, priced

### A. Prebuilt release artifact (`pip install`, then `atlas serve`)

**Cost:** config discovery must move off `PROJECT_ROOT` to a real user path
(`~/.config/atlas/` or platformdirs), `frontend/dist` must ship as package
data, and `config.example.json` must ship with it. All three are already
written into the *Publish to PyPI* ticket, so this is that ticket's packaging
half rather than new work.

**Leaves standing:** wall 1, partly — still needs a Python and a `pip`. Nothing
else.

**Note it does *not* need PyPI.** A GitHub release asset installs with
`pip install <url>`, which sidesteps both the distribution-name question and
the PyMuPDF/AGPL blocker recorded in `docs/licensing.md` and the PyPI ticket.
Worth separating: the packaging work is useful immediately, publishing is a
separate decision.

### B. Docker image (`docker run`)

**Cost:** a Dockerfile, a base image choice, and a published image somewhere.
The torch question is the whole story — at today's dependency set a Linux
image carries the CUDA packages and lands in the multi-GB range; with the
extras split it is a ~100 MB image. **Do not attempt this before the
dependency split.**

**Leaves standing:** nothing on the toolchain side — this is the only option
that removes wall 1 entirely. Adds its own: Docker Desktop is itself an
install, data lives in a volume the user has to reason about, and `localhost`
port mapping is one more thing to explain.

### C. Guided first-run (the app writes its own config)

**Cost:** small. Most of it exists — the settings modal already writes
`config.json`, and a missing one is already created from the example. What is
missing is the *moment*: a first-launch state that says "you have no model
provider; here are four, two are free" and links to Settings, instead of the
teacher failing on first use with a message about `config.json`.

**Leaves standing:** walls 1 and 2 entirely. This does not make Atlas
installable — it makes it *usable once installed*.

## Recommendation

Sequence, not a choice — the options are not alternatives:

1. ~~**Split the dependencies into extras**~~ — **done in v7.15.0.**
   `atlas[sources]`, `atlas[pdf]`, `atlas[corpus]`; the three unused
   declarations deleted. Measured after: a core install is **83 MB** and boots,
   serves a graph, and reports each missing capability by name. CI dropped from
   1.0 GB to 304 MB. PyMuPDF is now optional, which makes the AGPL question in
   `docs/licensing.md` concrete rather than theoretical.

   Two things surfaced while doing it, both worth carrying forward.
   `corpus/source.py` imported `duckdb` at module scope and
   `integrations/semantic_scholar/__init__.py` imports `corpus`, so a
   corpus-less install could not have served a graph at all — the same shape as
   the v7.14.0 keyless crash, now guarded by a test that walks the tree. And a
   `pip install .` into a clean venv **failed on config discovery exactly as
   predicted below** (`FileNotFoundError: .../lib/python3.14/config.example.json`),
   which is the next step's first task, not a new problem.
2. **Option A's packaging half** — config discovery off `PROJECT_ROOT`,
   `frontend/dist` as package data. Ship it as a GitHub release asset. This is
   the largest reach gain per unit of work, and it is a prerequisite for B
   anyway (a Docker image wants an installable package, not a git clone).
3. **Option C**, whenever. It is small, independent, and helps under A and B
   equally.
4. **Option B** last, if at all. It removes the most friction and costs the
   most to maintain (base image, rebuilds, a registry, a data-volume story).
   Worth doing only if the ask is genuinely "people who cannot install Python."

## Open questions

- **Where should config live for an installed Atlas?** `~/.config/atlas/` is
  the obvious answer, but the `.config-location` sidecar and the "path is
  anchored to the repo root" convention in `StorageConfig` both assume a
  checkout. Settle this before the packaging work hard-codes anything — it is
  the same "settle the location first" warning the PyPI ticket already carries
  about `frontend/dist`.
- ~~**Does a torch-free install degrade honestly?**~~ **Answered in v7.15.0:
  yes.** `optional.require` raises a `MissingExtra` naming the capability and
  the command, and `optional.available` is the ask-before-doing half the
  embedder uses to log one line about falling back to lexical search instead of
  dumping a traceback. What is *not* yet verified is the full UI path — nobody
  has uploaded a PDF to a core-only install and watched what the browser shows.
- **Who is the reader?** "A student" is doing a lot of work in the ticket. A
  student with a laptop and no terminal experience needs B. A grad student who
  has used `pip` needs A. These have very different costs and the answer
  changes the sequencing above.
