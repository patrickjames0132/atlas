# `agents/orchestrators`

The agents that own an outcome. Each one decides what the work is, delegates
parts of it, and is answerable for what the user finally sees.

```
orchestrators/
  researcher/     — agentic Q&A, with or without a graph
  lecturer/       — the streaming lecture over the visible graph
  summarizer/     — one-shot paper TL;DRs
  query_analyst/  — one-shot seed-search query expansion
```

The other tier is `workers/` — one source each, one bounded question each.
The membership rule and the return-shape contract live in
[`../workers/README.md`](../workers/README.md); read that first if you're
deciding where something new belongs.

## Why the tier exists

Not every agent here delegates today — `summarizer` and `query_analyst` are
one-shot micro-agents with no sub-agents at all. They live here anyway,
because the line that matters is **who owns the result**, not who currently
has employees. A summarizer's TL;DR is shown to the reader as the app's
answer; a worker's findings never are.

The practical version of that ownership, and the reason it can't be split:
the researcher owns the **numbered paper list**. `[n]` must mean the same
paper to the prose, the citation resolver, the provenance count and the
frontend chip that builds a graph from it. That invariant holds exactly as
long as one agent assigns the indices — which is why `find_papers` receives
raw provider nodes from the paper scout and numbers them itself.

## The router that isn't here

There used to be an `orchestrator/` in this folder: one `run(intent, ...)`
entry point that every route funnelled through, dispatching on an `Intent`
enum. It was **deleted in v7.0.0**, along with the enum, because it had
stopped earning its place — it dispatched two known intents to two agents and
never grew the model half it was designed around. Every caller already knew
which workflow it wanted, so the enum was a string round-trip between a route
and the function next to it.

Routing lives in the routes now, which is where the intent already was:
`/api/lecture` calls the lecturer, `/api/ask` and `/api/ask_sources` call the
researcher. Two things the router carried had to land somewhere real, and
neither belonged to it:

- **The Done/Error termination contract** — a stream that simply stops looks
  identical to one still working, so the panel would wait forever. It is now
  `streams.terminated`, shared plumbing wrapping any workflow. A workflow is
  responsible for its events, not for how a transport learns it finished.
- **Lecture mode scoping** (`_story_nodes`, `_chronological`) — which visible
  nodes a mode may narrate, and in what order. That is lecture domain logic
  and moved into `lecturer/main.py`, which now scopes its own input: callers
  pass everything on screen rather than pre-filtering. (One visible
  consequence: a lecture's numbered list is chronological, so `[1]` is the
  oldest paper.)

## What moved here, and what it cost

All five packages moved from `agents/` in v7.0.0 with **no behavior change**
(the fifth, `orchestrator/`, was then deleted — see above).
Worth knowing if you're grepping history: `AGENT_ID` is a string constant
independent of package path, so no `config.llm.agents` entry moved and no
config churn was involved. The only mechanical cost was relative-import
depth (`from ..` became `from ...` inside each package).

## How it's verified

Each package has its own tests under
`test/atlas/agents/orchestrators/<name>/`, mirroring the source tree. The
researcher's are where the two-tier contract is actually pinned — it stubs
the workers rather than the provider calls beneath them, so the assertions
are about the seam that exists rather than the plumbing behind it.
