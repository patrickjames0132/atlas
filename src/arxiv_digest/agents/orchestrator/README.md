# `agents.orchestrator`

The front door of the teacher: one entry point, `run(intent, ...)`, that
dispatches to the right workflow and guarantees the event stream always
terminates with exactly one `Done` or `Error`.

## Why it exists

Routes shouldn't know how workflows are wired — which sub-agent handles
what, that a history lecture needs graph enrichment first, or how failures
must end a stream. The orchestrator owns the *workflow scripts* (the
playbooks in `skills/workflows/`, implemented here as deterministic code)
while each sub-agent owns a single competence.

## How it works

```
orchestrator.run(intent, **payload)                    main.py
  lecture   → [history mode: backfill.history_backfill —
               Trace/Discovery stream out AND the discovered
               ancestors join the node set]
              → lecturer.lecture(seed, enriched_nodes, mode, target)
  q&a       → tutor.answer(question, seed, nodes, history, source_ids)
  librarian → librarian.answer(question, history, source_ids)
  always    → Done on success | Error on failure/bad input — last, always
```

- **`main.py`** — `run`, the dispatcher (and the documented model seam).
- **`backfill.py`** — the "How we got here" walk: launch from the oldest
  visible papers (never the seed — its references are already on screen),
  each hop pull the frontier's references (day-cached via
  `agents.traversal`), keep the most-cited new ancestors, carry the oldest
  additions into the next hop; stop at the hop budget, an empty frontier,
  or `lookback_years` before the seed. Knobs in `config.graph.backfill`.

## Design decisions worth knowing

- **No model here yet — deliberately.** The locked Phase 4 design is
  *hybrid* orchestration: deterministic dispatch for known intents, the
  orchestrator's own model only for ambiguous or multi-step asks. But every
  current entry point passes a known intent, so there is no code path that
  would ever engage a model — building the `Agent` + `llm.agents` entry now
  would be speculative plumbing (the same call as Phase 3's query-expansion
  seam, which waited for its agent). When a free-form entry point exists,
  the model half lands in `main.py`.
- **`history_backfill` is the orchestrator's, not the lecturer's.** Three
  reasons, settled explicitly: (1) "tools" in this package means
  *model-callable*, and backfill is the one thing no model may ever invoke;
  (2) unlike the librarian's retrieval (its grounding, needed on every
  call), backfill is conditional (history mode only) and *edits the
  lecturer's input* rather than grounding it — and its `Discovery` events
  serve the live graph canvas regardless of what the lecture says; (3) the
  split keeps roles honest — sub-agents own one competence, the
  orchestrator owns workflow scripts (`workflows/lecture.md` literally
  reads "backfill, then delegate").
- **Backfill knobs are typed config** (`config.graph.backfill`: `hops`,
  `per_hop`, `frontier`, `lookback_years`, `fetch_limit`), not `llm.agents`
  extras — no LLM touches the walk, so an agent entry would be a category
  error; and the shape is settled (a years-old stable feature), meeting the
  promotion bar the tutor's still-staging budgets don't.
- **Backfill failures are never fatal.** S2 errors on a hop are noted and
  skipped inside the walk; an entirely-empty walk reports once, with
  `error=True` distinguishing "we couldn't look" from "we found nothing".
  A *lecturer* failure, by contrast, ends the stream with `Error`.
- **Discovered ancestors carry `idx=None`** — the walk runs before the
  lecturer numbers anything (`events.DiscoveredNode` gave `idx` a None case
  for exactly this). The frontend merges them by id; the lecturer numbers
  the enriched set by position like any other node list.
- **Bad input is an `Error` event, not an exception** — unknown intent or
  missing required payload ends the stream properly; routes add their own
  validation in Phase 5, but the stream contract holds even if they don't.

## Who uses it, and how/why

- **The routes layer (Phase 5, traced from the old repo, not yet ported).**
  Old `routes/teacher.py` calls the dead teacher functions directly —
  `POST /api/lecture` → `lecture_beats` (after running the backfill
  inline), `POST /api/ask` → `answer_agentic`, `POST /api/ask_sources` →
  `answer_from_sources`. All three become `orchestrator.run(...)` with
  intents `lecture` / `q&a` / `librarian`, serializing each typed event as
  an SSE frame named by its `type` tag. Session history stays in routes
  (locked decision — agents receive history, never store it).
- **Nothing else.** Sub-agents never call the orchestrator (no cycles), and
  `query_analyst` deliberately bypasses it (search infrastructure, not a
  teacher workflow).

## Testing

`test_backfill.py` fakes `traversal.neighbors`: launch-from-oldest,
citation ranking + per-hop cap, dangling-edge filtering, the year-floor
stop, and the found-nothing/couldn't-look distinction. `test_main.py` fakes
the three sub-agents at the module seam: relay + `Done` appending, full
kwargs passthrough, backfill enrichment reaching the lecturer, backfill
skipped outside history mode, mid-stream failure → `Error` (and no `Done`),
and bad input → `Error`. Config knobs are overridden per-test on the
mutable `config` object, as everywhere in this suite.
