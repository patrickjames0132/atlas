# `agents.orchestrator`

The front door of the teacher: one entry point, `run(intent, ...)`, that
dispatches to the right workflow and guarantees the event stream always
terminates with exactly one `Done` or `Error`.

## Why it exists

Routes shouldn't know how workflows are wired — which sub-agent handles
what, or how failures must end a stream. The orchestrator owns the
*workflow scripts* (the playbooks in `skills/workflows/`, implemented here
as deterministic code) while each sub-agent owns a single competence.

## How it works

```
orchestrator.run(intent, **payload)                    main.py
  lecture   → lecturer.lecture(seed, nodes, mode, target)
  q&a       → researcher.answer(question, seed, nodes, history, source_ids)
  librarian → librarian.answer(question, history, source_ids)
  always    → Done on success | Error on failure/bad input — last, always
```

- **`main.py`** — `run`, the dispatcher (and the documented model seam).

**Lectures never expand the graph.** Every lecture mode — history,
intuition, evolution, frontier, bridge — narrates only nodes the user can see. Only
the **researcher** (explicit Q&A) may pull new papers onto the canvas, via
its `expand_node`/`search_papers` tools. (The deterministic "backfill"
walks that used to enrich history/evolution lectures were removed for
exactly this reason — a lecture should tell the story of the graph you
built, not silently grow it.)

**Modes are scoped by `_story_nodes`:** history's story ends AT the seed, so
the lecturer only receives the seed plus papers published in or before its year;
evolution starts from the seed (in or after); frontier keeps the seed plus only
papers from the last ~12 months (the leading edge, any relation — recent
citations and recent similar work). Undated papers are dropped from the
year-clamped directional modes — they can't be placed in a chronological story.
Intuition
and bridge see the whole visible set; an undated seed disables the clamp.

## Design decisions worth knowing

- **No model here yet — deliberately.** The locked Phase 4 design is
  *hybrid* orchestration: deterministic dispatch for known intents, the
  orchestrator's own model only for ambiguous or multi-step asks. But every
  current entry point passes a known intent, so there is no code path that
  would ever engage a model — building the `Agent` + `llm.agents` entry now
  would be speculative plumbing (the same call as Phase 3's query-expansion
  seam, which waited for its agent). When a free-form entry point exists,
  the model half lands in `main.py`.
- **Lectures are read-only over the graph.** The orchestrator once ran
  deterministic "backfill" walks before history/evolution lectures,
  expanding the graph toward the roots/frontier. That's gone (see git
  history): a lecture narrates the graph the user built; only the
  researcher — on an explicit question — may expand it. If a lecture feels
  thin, the fix is a richer initial graph (e.g. the even-by-year citation
  spread), not silent lecture-time growth.
- **Bad input is an `Error` event, not an exception** — unknown intent or
  missing required payload ends the stream properly; routes add their own
  validation in Phase 5, but the stream contract holds even if they don't.

## Who uses it, and how/why

- **The routes layer (Phase 5, traced from the old repo, not yet ported).**
  Old `routes/teacher.py` calls the dead teacher functions directly —
  `POST /api/lecture` → `lecture_beats`, `POST /api/ask` →
  `answer_agentic`, `POST /api/ask_sources` → `answer_from_sources`. All
  three become `orchestrator.run(...)` with intents `lecture` / `research`
  / `librarian`, serializing each typed event as an SSE frame named by its
  `type` tag. Session history stays in routes (locked decision — agents
  receive history, never store it).
- **Nothing else.** Sub-agents never call the orchestrator (no cycles), and
  `query_analyst` deliberately bypasses it (search infrastructure, not a
  teacher workflow).

## Testing

`test_main.py` fakes the three sub-agents at the module seam: relay +
`Done` appending, full kwargs passthrough, the per-mode lecture scoping
(history ancestors-only, evolution descendants-only, frontier last-~12-months
any-relation, intuition everything, undated seed → no clamp; no trace/discovery
frames ever precede a lecture), mid-stream failure → `Error` (and no `Done`),
and bad input → `Error`.
