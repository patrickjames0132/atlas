# `arxiv_digest` (backend package root)

This README covers what lives directly at this level — currently just
`config.py`. `app.py` and `cli.py` will get sections here once they're
ported (Phase 5).

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
config.s2         — Semantic Scholar connection settings
config.graph      — how big a neighborhood one seed pulls onto the canvas
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
  and `config.s2.min_interval` per test. Consumers should read
  `config.x.y` at call time, not bind it to a module-level constant at
  import time, so those overrides are actually seen.

## Testing

`test_config.py` — 19 tests: the example template always validates,
derived paths, every "reject a bad value" case (bad literal, negative
number, blank required string, duplicate agent id, unconfigured provider,
missing config file entirely), and the chunk-overlap cross-field check.
