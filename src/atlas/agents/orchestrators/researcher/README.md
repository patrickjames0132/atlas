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
  3  tools fire: read_paper / expand_node / find_papers / search_web /
     show_figure / search_sources / show_source_figure —
     each pushes Trace /
     Discovery / Figure events onto deps.queue, drained into
     the stream between run events (live "watch it work")
  4  the final Answer{text, cited} streams as output-tool args;
     partial JSON parsing turns the growing `text` into Token
     deltas mid-generation
  5  Cited = papers actually read + papers named by index
```

## The two scouts (v7.0.0)

`find_papers` and `search_web` don't do the searching — they hand a **need**,
in the researcher's own words, to a worker under
[`agents/workers/`](../../workers/README.md), and number or format whatever
comes back. Three things about that seam are load-bearing:

- **The scout finds; the researcher numbers.** The paper scout returns raw
  provider node dicts and `find_papers` assigns every index. `[n]` has to
  mean the same paper to the prose, the citation resolver and the frontend
  chip that builds a graph from it, and that only holds while one agent owns
  the list.
- **A tool call spends one of *this* agent's budgets and then runs a whole
  scout**, which has budgets of its own. So `searches: 3` is three scouting
  runs, not three queries — each may issue several.
- **Dedupe keys on the need, not the query.** The researcher no longer writes
  query strings, so the visited-set holds lower-cased needs; asking for the
  same thing twice is a cache hit and never re-runs the scout.

Web pages are cited as **inline markdown links**, never `[n]` — that marker
belongs to papers, and the numbered list is what makes it resolvable. This
also means web grounding is *counted* in provenance (`web_searches`,
`web_pages`) rather than counted off the finished prose the way `[Sn]` and
`[n]` citations are: there is no marker to count.

## The join: the web feeds the literature (v7.1.0)

Two scouts that each answer their own question leave the reader with a link
to an announcement *and*, separately, some papers — and nothing between them.
The paper behind the announcement is what they actually want, because it is
the only one of the two that can be seeded into a graph. So the researcher is
asked to run `find_papers` **again** on whatever specific thing the web named.

The measurement that shaped it is worth keeping, because it says the join
isn't a nicety the model does anyway. Grepping `data/atlas.log` across a
week of real runs, every paper search restated the user's question at topic
level (`quantum computing advances 2024`, `quantum physics breakthroughs
2023 2024 2025`) — not one carried a name the web had just supplied. Three
things in the code explained it: the prompt said "each source is one call",
nothing ordered the web before the papers, and the web tool's result told the
model what to do with the pages for the *prose* and nothing about the graph.

The fix is prompt-only, in four places, and deliberately so — a
reconciliation *worker* was the alternative, and the rule against speculative
agents is the one that killed the orchestrator. Each place earns its keep:

1. **`config.SYSTEM_PROMPT`** — states the join and the ordering rule (web
   first when the question is about what's new, so the paper search has names
   to work with rather than the topic words it started from).
2. **`tools._WEB_HANDOFF`**, appended to the web tool's *result* — the same
   instruction at the moment the decision is made, with the pages in front of
   the model, where a rule read a thousand tokens earlier competes with
   everything else in the prompt. Withheld when `searches_left` is 0: an
   instruction the model can't follow burns a step being refused.
3. **The web scout** is asked to *name things* — the system, chip or lab as
   the page spells it, and the paper's own title where a page gives one. It
   can't join what it never carried across.
4. **The paper scout** is told a need may name a thing rather than a topic,
   and that the paper is titled after the *result*, not the product
   ("Quantum error correction below the surface code threshold", not
   "Willow") — so the name is one attempt, and the claim is the next.

`find_papers` and `search_web` log their `need` at INFO for exactly this
reason: the trace shows the reader one query, while "did the web's names
reach the paper search?" is answered by the need, after the fact, on a run
nobody was watching. Two log lines in sequence are the measurement.

- **`config.py`** — `AGENT_ID`, `SKILLS` (all four — the only agent that
  loads `figures`), the strategy `SYSTEM_PROMPT`, and `BUDGETS`
  (defaults overridden by the agent entry's `extras`; unknown extras keys
  fail at import so the staging area can't silently accumulate).
- **`tools.py`** — `ResearcherDeps` (the run-state) and the six tools.
- **`main.py`** — the `Answer` model, the `Agent`, the sync event bridge.

## Design decisions worth knowing

- **Failures are tool-result text, never exceptions.** A spent budget, a
  bad index, a failed S2 call — each comes back as prose the model steers
  by ("answer now with what you've gathered"). The step budget works the
  same way: once `max_steps` tool calls are spent, every tool answers
  `STEPS_EXHAUSTED`, so the model lands the answer itself inside the same
  run. A `UsageLimits` request cap backstops pathological loops only.
- **The coverage guard demands only what's *reachable*.** `_must_have_looked`
  bounces a substantive answer that skipped an available source — but
  "available" has to mean *the model can still go get it*, not just *the
  operator left it switched on*. A run that spends its step budget before the
  sweep finishes would otherwise deadlock: the guard says "call search_web",
  the tool refuses (no steps), the model answers, the guard bounces it again,
  and the `UsageLimits` backstop ends the run with the reader getting nothing
  — strictly worse than the ungrounded answer being prevented, which
  provenance reports honestly anyway. So `_unconsulted` checks the step budget
  and each source's own remaining budget (v7.1.0; see
  [`docs/bugs.md`](../../../../../docs/bugs.md)). `_doomed` shares that
  function rather than restating it, so what streams and what passes can't
  drift apart.
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
- **Full reads and figures fall back to the paper's open-access PDF**
  (`services/pdf`) when there's no ar5iv render — so journal papers (and
  arXiv papers ar5iv couldn't convert) get read in full and can show
  figures too. `_node_figures` is the single source for the figure list:
  the full read prints it and `show_figure` indexes into it, so numbering
  can't drift between the two; for PDF-mined papers the list includes
  tables and algorithm boxes, and image URLs point at
  `/api/pdf_figure/<token>/<n>` instead of the ar5iv proxy.
- **`show_source_figure` is the library twin of `show_figure`** —
  page-addressed as well as list-addressed: passages cite `[Sn, p.N]`,
  so the tool takes `(source, page, figure)` — `source` being the `[Sn]`
  number, resolved to a real id by `deps.source_id` — and picks from the figure
  manifest mined off the source's stored PDF (`services/sources/figures.py`);
  the attached image serves from `/api/sources/<id>/figure/<n>` and its
  `Figure` event carries `index=None` (no numbered paper). It shares the
  `figures` budget and the library `prepare` gate below, and everything past
  the step charge lives in the shared `agents/library_figures.py` — the
  core was shared with the librarian's twin until that agent was retired in
  v6.7.0; the seam is kept, since it is the natural home for the resolve /
  dedupe / slot logic.
- **`search_sources` is registered via a `prepare` hook** only when the
  (scope-filtered) library is non-empty — no availability probe at all:
  retrieval degrades by itself, and an empty library never pays the torch
  load. The user's scope overrides the model's `source` pick, so the
  search can't stray outside chosen sources; an out-of-range `[Sn]` comes
  back as tool text, never a raise. (mypy note: the tool variable's
  explicit `Tool[ResearcherDeps]` annotation is load-bearing — with `prepare=`
  in play, mypy can't infer the ParamSpec on its own.)

## Who uses it, and how/why

- **`routes/agents.py`** — both chat surfaces call `answer(...)` directly,
  per `skills/workflows/research.md`: `POST /api/ask` with a graph open (seed
  + visible nodes + provider), `POST /api/ask_sources` without one. Each
  wraps the stream in `streams.terminated` for the `Done`/`Error` contract
  and serializes it as SSE. There is no router in between — the `orchestrator`
  that used to own that dispatch was deleted in v7.0.0 (see
  [`../README.md`](../README.md)).

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
