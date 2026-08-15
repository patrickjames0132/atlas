# `agents/workers/search`

One source each, one bounded question each. A worker is handed a *need* in
plain words, goes to its source, and comes back with findings — it never
addresses the student, never writes the answer, and never decides what the
turn is about.

```
workers/search/
  papers/     — the academic-paper source (Semantic Scholar / OpenAlex),
                searched with reformulation and recency bounding
  web/        — the open web, via Anthropic's provider-side WebSearchTool
```

Grouped under `search/` because "go look something up somewhere" is one job
with several backends: the next one (an arXiv listing, a code index, the
reader's own notes) belongs here beside them, not as another top-level
worker. A worker of a different *kind* — one that transforms rather than
retrieves — would get its own group next to this one.

The other tier is `orchestrators/`. The split is **flat and deliberately two
levels deep, no more** — see "Why not deeper" below.

## What earns worker status

> **A capability earns worker status when it needs judgment or context
> isolation. Otherwise it stays a plain function.**

That rule is the whole design, and it is written here so it isn't
re-litigated every time something new is added. Applied:

| Capability | Verdict | Why |
| --- | --- | --- |
| **Web search** | worker | Both criteria, unambiguously. It must phrase the query, judge when it has enough, and compress long low-signal pages into findings — and those pages would crowd out the researcher's own context if they landed there. |
| **Paper search** | worker | Judgment: *query reformulation and recency bounding*. A lexical, citation-weighted search answers "what's new in X" with landmarks from a decade ago; the fix is to look at what came back and ask again with a year floor. That is a loop with a decision in it, which is exactly what a function isn't. |
| `traversal.expand` | function | *Which* node to expand is the orchestrator's reasoning about a graph it can see. Delegating it would blind the agent that has the map. |
| `sources.search` (the library) | function | Passages already come back compact and `[Sn, p.N]`-tagged — there is nothing to compress and no query to reformulate. Promote it later **if measured**, not on principle. |
| `read_paper`, figure mining | function | Fetch and format. No decision inside. |

No shared-tools package was created for the functions: `agents/traversal.py`
already is that seam.

## Why not deeper

Depth beyond these two tiers was considered and rejected, on two independent
grounds. Anthropic's own Managed Agents **enforces single-level delegation** —
a roster containing a rostered agent fails validation — so the platform that
has run this pattern at scale draws the line in the same place. And current
Opus guidance is to delegate *less*, because every sub-agent re-establishes
context from nothing and then has to report back through a narrow channel;
each hop is a place for the original question to blur.

## The return-shape contract

> **A worker returns structured findings. Never prose, never indices.**

The orchestrator owns everything that has to be globally consistent: the
numbered paper list and index assignment, citation resolution, provenance,
the `Done`/`Error` stream contract, the turn kind, and the answer itself.

The papers worker makes this concrete — it returns **raw provider node
dicts**, and the researcher's `find_papers` tool is what turns them into
numbered `DiscoveredNode`s. That isn't ceremony. `[n]` has to mean the same
paper to the prose, to the citation resolver and to the frontend chip that
builds a graph from it, and that invariant survives exactly as long as one
agent owns the list. Two agents assigning indices is not a bug you find in
review; it is a bug you find when a reader clicks `[3]` and gets someone
else's paper.

The web worker returns sources with **real URLs**, which is the same rule in
its other form: a claim the reader can't check isn't a finding.

## The workers don't talk to each other — the orchestrator joins them

Worth stating, because the obvious reading of "one source each" is that the
sources stay apart. They don't: a web announcement's real value to this app
is the **paper behind it**, since only a paper can be seeded into a graph. So
the web's findings have to reach the paper search.

That join is the **researcher's** job, not a worker's, and it shows up here
as two prompt obligations rather than as a channel between the two scouts:
the web scout must *name things* (the system, chip, lab, and the paper title
where a page gives one) so the name survives the hand-back, and the paper
scout must expect a need that names a **thing** rather than a topic — where
the paper is titled after the result, not the product. Neither knows the
other exists.

Keeping the wiring out of the workers is what leaves the door open for the
alternative if prompting measures badly: a *reconciliation* worker ("given
these pages and these papers, which pair up?") is a different job from
searching, so it would earn its own group beside `search/` rather than
joining it. See the researcher's README, "The join", for the measurement
that chose prompting first (v7.1.0).

## Design decisions worth knowing

- **A failed worker costs the answer its source, never the answer.** Both
  `scout` functions catch everything and come back empty with the reason as
  their summary. A scouting run that breaks must not take the turn down with
  it — the researcher can still answer, and the provenance line will honestly
  show it had less to go on.
- **The web is a grounded source, not recall.** Worth stating because a
  reader who finds v6.8.0 cutting the "general-assistant" ambition will
  reasonably wonder. What was cut there was the model answering from its own
  weights. A web page is as real, as citable and as retrievable as a paper or
  a page of the reader's own book: this *extends* the grounding boundary
  rather than abandoning it.
- **`capabilities.WebSearch`, not `native_tools.WebSearchTool`.** The bare
  native tool is accepted by the `Agent` constructor and then silently
  dropped, leaving an agent prompted to search the web with no way to. mypy
  catches it; the runtime does not. (Confirmed against the agent's resolved
  native-tool list — see the comment at the call site.)
- **Budgets are small on purpose.** The papers scout's value is two or three
  aimed attempts, not ten: every one is a live provider call the reader is
  waiting on. The web scout's `max_uses` is enforced **provider-side**, so
  unlike every other budget here the model cannot exceed it however it's
  prompted.
- **Deduping happens against the caller's world.** `scout` takes the caller's
  `known_ids` and copies it, so the papers it reports are only what is
  genuinely new — and the caller's own set doesn't gain ids for papers it
  hasn't accepted yet.

## How it's verified

Through the researcher, which is the only consumer: `test/atlas/agents/
orchestrators/researcher/test_main.py` stubs each `scout` (the *worker* is
the dependency, not the provider call two levels below it) and asserts the
contract — the scout finds, the researcher numbers; a repeated need is a
cache hit; a zero web budget unregisters the tool. The suite forces the web
scout **off** by default in `test/atlas/conftest.py`, for the same reason the
corpus and the real embedder are forced off there: a capability configured on
the developer's machine must not silently join every test.
