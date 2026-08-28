# `atlas` (backend package root)

This README covers what lives directly at this level — `config.py` and
`optional.py`. `app.py` and `cli.py` will get sections here once they're
ported (Phase 5).

## `optional.py` — importing what only some installs have

Three capabilities are **optional extras** (`pyproject.toml`): `sources`
(sentence-transformers + torch, searching your own uploads), `pdf` (PyMuPDF,
mining figures), and `corpus` (DuckDB, the offline S2 citations corpus).
Together they are the difference between a **1.0 GB** install and an **83 MB**
one, and a reader who only wants the graph and the teacher needs none of them.
`docs/first-run.md` has the measurements and why this split came before any
packaging work.

Every import of one goes through `require(module, extra)`, and two rules follow:

- **Never at module scope.** An eager import turns a missing extra into a
  failure to *start* rather than a failure to use one feature — the same shape
  as the keyless-startup crash fixed in v7.14.0. `corpus/source.py` really did
  have it: it imported `duckdb` at module level, and
  `integrations/semantic_scholar/__init__.py` imports `corpus`, so an install
  without that extra could not have served a graph. Enforced by
  `test_no_module_imports_an_optional_package_at_module_scope`, which walks the
  tree — verified to fail on the pre-split code.
- **The error names the fix.** `MissingExtra` says which capability was wanted
  and gives the exact command, because `No module named 'fitz'` tells someone
  who just installed Atlas nothing.

`available(extra)` is the *ask before doing* half, for code that would rather
degrade quietly than raise — the embedder calls it and logs one line about
falling back to lexical search, instead of dumping a traceback for what is a
supported way to install Atlas. Same pattern as the web scout asking
`supports_web_search` before prompting a model to search.

Type annotations are exempt: every module here uses
`from __future__ import annotations`, so a `TYPE_CHECKING` import costs nothing
at runtime and the real types survive.

## `config.py` — central configuration

## Why it exists

Every tunable the app has — paths, API keys, model names, agent
definitions — needs one home, loaded once, validated at startup, with zero
ambiguity about where a given setting comes from.

## How it's structured

`config.json` (repo root, gitignored — holds real API keys) is parsed by
Pydantic v2 models into one `config` object, grouped by the part of the
app that consumes it:

```
config.storage    — the three SQLite database paths
config.providers.s2         — Semantic Scholar connection settings
config.graph      — the graph's provider default and snapshot-cache TTL
config.sources    — bring-your-own sources: embedding, chunking, retrieval
config.server     — Flask host/port/debug
config.llm        — providers (backend credentials) + agents (behavior)
```

A committed `config.example.json` is the template (copy it to start); the
real `config.json` is gitignored. See
[`docs/configuration.md`](../../docs/configuration.md) for the *why* behind
individual example values (rate-limit numbers, chunk sizes, etc.) — this
README only covers the shape and the big decisions.

## Design decisions worth knowing

- **No defaults, anywhere.** Every field must be present in `config.json`
  or the app fails to start, with a message telling you to copy
  `config.example.json`. An unknown key, a negative limit, or a misspelled
  literal fails loudly at import time — nothing silently falls back to a
  guessed value.
- **JSON, not `.env`/dotenv.** A deliberate choice over the app's original
  environment-variable config: explicit types, real validation
  (`Literal["api", "claude_cli"]`-style enums, `PositiveInt`, cross-field
  checks), and no risk of "empty string vs. unset" ambiguity.
- **`llm` unifies what used to be three separate concerns.** Early drafts
  had `teacher` (narration), `agent` (tool-use budgets), and `lecture`
  (history-walk settings) as three top-level groups. They collapsed into
  one `llm` group because there's only one Claude agent in the app doing
  all three jobs — splitting the config by *feature* when it's all the
  same underlying agent was a distinction without a difference.
- **`llm.agents` is a list, not a single object** — this app is migrating
  onto [PydanticAI](https://ai.pydantic.dev), which supports many LLM
  vendors, and more agents beyond today's one entry (the teaching
  assistant) are planned. Each agent's `model` field is PydanticAI's own
  `"<provider>:<model_name>"` shorthand (e.g. `"anthropic:claude-sonnet-4-6"`),
  validated against `llm.providers` at load time — an agent naming an
  unconfigured vendor fails immediately, not on its first request.
  Credentials live in `llm.providers`, not on individual agents, since a
  key belongs to an (account × vendor) pair, not to any one agent.
- **`llm.agents[].extras` is a deliberate escape hatch, not a junk
  drawer.** An earlier version of this config had a dozen first-class
  fields for per-tool-call budgets (max steps, read limits, search limits,
  etc.). All of that was cut rather than carried forward as dead weight —
  as the teacher/agentic code is actually rebuilt (Phase 4), a setting
  either proves it's still needed (goes into `extras` first, promoted to a
  real typed field once its shape settles) or it doesn't come back at all.
- **`sources`, not `library`.** The bring-your-own-sources feature is
  called "Sources" everywhere else in the app (the Sources drawer,
  `/api/sources`) — "library" invited confusion with Python packages.
- **Mutable on purpose.** The config groups aren't frozen — the test
  suite's autouse `_isolate` fixture overrides `config.storage.data_dir`
  and `config.providers.s2.min_interval` per test. Consumers should read
  `config.x.y` at call time, not bind it to a module-level constant at
  import time, so those overrides are actually seen.

## Who uses it, and how/why

Nearly every backend module reads `config` — it's the app's one source of
truth, not a per-feature dependency. By subsystem:

- **Storage** (`storage/cache.py`, `storage/sessions.py`, `storage/utils.py`)
  read `config.storage.*` for where each SQLite file lives, and call
  `ensure_dirs()` before first use so a fresh checkout needs no setup step.
- **Semantic Scholar client** (`integrations/semantic_scholar/`) reads
  `config.providers.s2.*` (api key, URLs, timeout, throttle interval) to build every
  HTTP request and self-throttle. Its `corpus/` sub-package reads
  `config.storage.s2_corpus` — the offline citations corpus's root (outside
  the repo); unset means the corpus is off and the live citer path is used.
- **Graph assembly** (`services/graph/`) reads `config.graph.cache_ttl` to
  decide how long to trust a cached snapshot. Neighborhood size is **not**
  config: the app sizes every relation itself (the adaptive rules in
  `services/graph/budget.py`, ceilinged by the `UNBOUNDED_LANDMARK_CAP`
  payload guard in `integrations/caps.py`).
- **Bring-your-own sources** (`library/embeddings.py`, `library/sources.py`
  — not yet ported) will read `config.sources.*` for the embedding model,
  chunk size/overlap, and the hybrid-retrieval toggle.
- **The AI teacher** (`teacher/*`, `routes/teacher.py` — not yet ported)
  will read `config.llm.*` for the Anthropic key and model.
- **App wiring** (`app.py`, `cli.py` — not yet ported) will read
  `config.server.*` to start Flask, plus `PROJECT_ROOT` to locate the built
  frontend.

**Every not-yet-ported file above still references the *old* flat names**
(`config.AGENT_MAX_STEPS`, `config.EMBED_DIM`, `config.TEACHER_MODEL`,
`config.SOURCES_DB_PATH`, ...) — none of those exist anymore post-rewrite.
Each will need its config references re-mapped to the new nested groups
(and, per the `llm.agents[].extras` decision above, several of the old
per-tool-call budget fields won't come back as first-class fields at all)
when its phase comes up.

## Testing

`test_config.py` — 19 tests: the example template always validates,
derived paths, every "reject a bad value" case (bad literal, negative
number, blank required string, duplicate agent id, unconfigured provider,
missing config file entirely), and the chunk-overlap cross-field check.
