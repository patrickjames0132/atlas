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
  q&a       → researcher.answer(question, seed, nodes, history, source_ids)
  librarian → librarian.answer(question, history, source_ids)
  always    → Done on success | Error on failure/bad input — last, always
```

- **`main.py`** — `run`, the dispatcher (and the documented model seam).
- **`backfill.py`** — the "How we got here" walk, below.

## The backfill algorithm

The problem: a modern seed's graph almost never shows the foundational
work. Seed on a 2020 paper and the canvas holds its direct references —
2015-2019, mostly — while the ideas actually start in the 1980s. A history
lecture that opens mid-stream tells half the story. The walk's job is to
extend the graph backward to the roots *before* the lecturer speaks, so the
oldest beats have real papers to light up.

Every knob referenced below lives in `config.graph.backfill` (defaults in
parentheses; per-value rationale in `docs/configuration.md`).

**0. Setup — the ledger and the stopping line.** `known` starts as every
visible node id plus the seed: the dedup ledger that decides both "is this
paper a new discovery?" and "do both of this edge's endpoints exist on the
graph?". The `year_floor` is the seed's year minus `lookback_years` (40) —
the line where the story stops being this paper's prehistory. (Seed year
falls back to the newest visible year; the seed is almost always the most
recent paper on the graph.)

**1. Launch from the oldest visible papers — never the seed.** Expanding
the seed can only re-find its own references, which are by definition
already on screen. The oldest visible papers sit closest to the roots, so
*their* references are the first papers the graph hasn't shown. The
`frontier` (2) oldest non-seed papers become hop 1's launch points (the
seed is only the degenerate fallback for a one-node graph).

**2. Fetch.** Each hop pulls every frontier paper's references — one
day-cached S2 call each (`agents.traversal`), `fetch_limit` (8) references
per paper, so a full walk is bounded at `hops × frontier × fetch_limit`
(~48) lookups, most of them cache hits within a session. Two things
accumulate: `candidates` (papers not in `known`, first-seen wins) and
`edges` — **every** reference edge seen, even to papers that may not
survive selection, because keep-or-drop can't be decided until ranking
runs. Edge direction follows the same rule as `build_graph`: a reference
edge points citing → cited, and the frontier paper is always the citer.
An `S2Error` on one frontier paper sets a flag and skips it — the lecture
happens with or without that hop.

**3. Select — most-cited first, capped.** Candidates are ranked by
citation count and the top `per_hop` (6) become `DiscoveredNode`s. Citation
count is the proxy for *seminal*: the walk exists to surface the papers a
field's story opens with, not every stray reference. The cap keeps each
hop's canvas growth digestible (≤ `hops × per_hop` = 18 nodes per walk).
Discovered nodes carry `idx=None` — numbering is positional and happens
later, when the enriched node set reaches the lecturer.

**4. Filter edges against the ledger.** Only edges with BOTH endpoints in
`known` are emitted; a candidate that lost the ranking never became a
node, and its edges would dangle. Then the hop yields its two events:
`BackfillTrace(hop, found, oldest)` first (the "watch it work" line), then
`Discovery(nodes, edges)` (the payload the frontend merges).

**5. March backward.** The `frontier` (2) *oldest* additions become the
next hop's launch points — each hop starts from the furthest-back papers
found so far, so the walk moves monotonically toward the roots instead of
wandering sideways through contemporaries. The loop ends at whichever
comes first: the hop budget (`hops` = 3), an empty candidate set (every
reachable reference already on the graph), or the year floor (`oldest ≤
year_floor` — the story has its roots).

**6. Report an empty walk honestly.** Zero additions across all hops
yields one explicit `BackfillTrace(found=0, error=errored)` instead of
silence — and the `error` flag distinguishes "the graph already reaches
its roots" (fine) from "S2 was down and we couldn't look" (suspect). The
frontend can phrase those differently; failing silently was never an
option.

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
  promotion bar the researcher's still-staging budgets don't.
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
  intents `lecture` / `research` / `librarian`, serializing each typed event as
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
