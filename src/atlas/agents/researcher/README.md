# `agents.researcher`

Agentic Q&A over the graph — the flagship. The model reads the visible
papers, expands the graph or searches when they don't suffice, optionally
attaches real figures, then answers grounded in what it actually read, with
the user watching every step live.

## Why it exists

A lecture narrates what's already on screen; a real question often needs
more — the methods section of one paper, a reference two hops away, the
newest work on a topic. The old repo hand-rolled this as a raw Anthropic SDK
loop (`teacher/agentic.py` + 750 lines of `tools.py`): manual stream-event
handling, a `<<CITED>>` sentinel hidden by held-back tails, `discard` events
to disavow streamed preamble, and five hand-written JSON tool schemas. Here
PydanticAI owns the loop, the schemas come from signatures, and the sentinel
apparatus is replaced by one structured output.

## How it works

```
researcher.answer(question, seed, nodes, history, source_ids)      main.py
  1  deps = ResearcherDeps: numbered list, budgets (config extras),
     visited-sets, read cache, event queue                     tools.py
  2  agent.run_stream_events(...) driven one event at a time
     on a private loop (the sync bridge)
  3  tools fire: read_paper / expand_node / search_papers /
     show_figure / search_sources — each pushes Trace /
     Discovery / Figure events onto deps.queue, drained into
     the stream between run events (live "watch it work")
  4  the final Answer{text, cited} streams as output-tool args;
     partial JSON parsing turns the growing `text` into Token
     deltas mid-generation
  5  Cited = papers actually read + papers named by index
```

- **`config.py`** — `AGENT_ID`, `SKILLS` (all four — the only agent that
  loads `figures`), the strategy `SYSTEM_PROMPT`, and `BUDGETS`
  (defaults overridden by the agent entry's `extras`; unknown extras keys
  fail at import so the staging area can't silently accumulate).
- **`tools.py`** — `ResearcherDeps` (the run-state) and the five tools.
- **`main.py`** — the `Answer` model, the `Agent`, the sync event bridge.

## Design decisions worth knowing

- **Failures are tool-result text, never exceptions.** A spent budget, a
  bad index, a failed S2 call — each comes back as prose the model steers
  by ("answer now with what you've gathered"). The step budget works the
  same way: once `max_steps` tool calls are spent, every tool answers
  `STEPS_EXHAUSTED`, so the model lands the answer itself inside the same
  run. A `UsageLimits` request cap backstops pathological loops only.
- **`sequential=True` on every tool.** PydanticAI runs a turn's tool calls
  concurrently by default; these tools mutate shared deps state — budgets,
  visited-sets, and above all the numbered list, whose indices must be
  assigned in call order. (Found as an order-dependent test flake; don't
  remove.)
- **The structured `Answer` kills the sentinel.** `cited` is a typed field,
  so the `<<CITED>>` marker, its hold-back streaming, and `discard` events
  all die. Any prose the model emits *before* its final result (tool-call
  narration) is silently ignored rather than streamed-then-disavowed. The
  one surviving string protocol is `<<FIG n>>` — positional in prose, which
  structured output can't express.
- **The sync bridge lives in `agents/streams.py`** (promoted when the
  lecturer needed it too): `run_stream_events` is async-only; `answer`
  stays a sync generator (Flask SSE), iterating `streams.drive(...)` and
  draining the deps queue between events. Answer prose is decoded from the output tool's
  streamed args with `pydantic_core.from_json(..., allow_partial=
  "trailing-strings")` — tokens flow while the JSON string is still open.
- **Budgets live in `extras`** (max_steps, full/summary reads, hops +
  expand_limit, searches + search_limit, source_searches, figures,
  fulltext_max_chars) — the staging area, promoted to typed config once
  their shape settles. The old `AGENT_WALLCLOCK` was dropped, not ported:
  the step cap plus per-tool budgets already bound the run.
- **`search_sources` is registered via a `prepare` hook** only when the
  (scope-filtered) library is non-empty — no availability probe at all:
  retrieval degrades by itself, and an empty library never pays the torch
  load. The user's scope overrides the model's `source_id` pick, so the
  search can't stray outside chosen sources. (mypy note: the tool variable's
  explicit `Tool[ResearcherDeps]` annotation is load-bearing — with `prepare=`
  in play, mypy can't infer the ParamSpec on its own.)

## Who uses it, and how/why

- **`agents/orchestrator` (Phase 4d).** The `research` intent per
  `skills/workflows/research.md`: a pure delegation to `answer(...)`, relaying
  its event stream and appending `Done`/`Error`.
- **Old repo, traced (not yet ported):** `routes/teacher.py`'s
  `POST /api/ask` validates the question, pulls the graph-chat history from
  its session store, calls `teacher.answer_agentic(question, seed, nodes,
  history, source_ids)`, and serializes the tuples as SSE frames
  (`trace`/`nodes`/`figure`/`token`/`discard`/`cited`). Phase 5 rewrites it
  to call the orchestrator with intent `research`; the `discard` frame dies with
  the sentinel, and `nodes` frames become `discovery` events.

## Testing

`test_main.py` drives the real bridge end to end with scripted
`FunctionModel.stream_function` models (each test lists the tool calls per
model turn, args streamed as JSON chunks): token deltas from partial args
JSON, live trace/discovery ordering, edge directions, index assignment for
discovered papers, cited = reads + named, the library-gated tool list
(`info.function_tools`), scope override reaching retrieval, step-budget
steering, and the figure proxy/slot flow. Integration boundaries
(`traversal`, `retrieval`, `figures`, `store.list_sources`) are
monkeypatched at the tools/main module seams.
