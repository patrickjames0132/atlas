# `agents`

The AI teacher, rebuilt as a crew of agents: one **orchestrator** delegating to
focused **sub-agents**, every agent defined by Pydantic objects (PydanticAI
`Agent`s wired from `config.llm.agents` entries) instead of the old repo's
hand-rolled Anthropic SDK loops.

**Status: COMPLETE.** The shared infrastructure (`events.py`,
`traversal.py`, `factory.py`, `prompts.py`, `skills/`), the
model-driven agents (`summarizer`,
`lecturer`, `researcher`),
and the `orchestrator` dispatcher are built and tested; the old
`teacher/` package is fully retired. What remains is wiring: routes call
`orchestrator.run(intent, ...)` in Phase 5. (`summarizer` arrived later,
v5.17.0: the detail panel's on-demand TL;DR — a one-shot micro-agent
called from `routes/graph.py`, never the orchestrator. `query_analyst`
was the other agent of that shape; it was retired in v7.6.0 when the
paper scout absorbed its job.)

## `events.py` — the typed event stream

A workflow (a lecture, a Q&A turn, a library chat) doesn't return one value —
it *streams*: narration arrives beat by beat, an agent's tool steps surface as
they happen, discovered papers merge into the live graph mid-answer.
`events.py` is that stream's vocabulary, as Pydantic models: every agent
yields these, the routes layer (Phase 5) serializes each one to an SSE frame
named by its `type` tag, and the frontend switches on the same tag. One
protocol for every workflow, declared in one file.

| Event       | Emitted by            | Meaning                                                        |
| ----------- | --------------------- | -------------------------------------------------------------- |
| `Beat`      | lecturer              | one narration paragraph + heading + nodes to light up          |
| `Token`     | researcher                 | a chunk of streamed answer prose                               |
| `Trace`     | researcher, orchestrator   | "watch the agent work" — one variant per action (below) |
| `Discovery` | researcher            | papers + edges to merge into the live graph — only growth that *attaches* (see below) |
| `Figure`    | researcher | a real figure attached to the answer — a paper's, or one mined from an uploaded PDF (`index=None`) |
| `Cited`     | researcher            | the node ids the answer draws on                               |
| `SourceRefs` | researcher, lecturer | `[Sn]` marker index → library source, sent *before* the prose  |
| `PaperRefs` | researcher            | `[n]` marker index → paper (title + URL + the provider that minted the id), for when there's no graph to resolve against |
| `Provenance` | researcher           | what actually grounded the answer — observed, not claimed      |
| `Done`      | every workflow        | clean finish — always last on success                          |
| `Error`     | every workflow        | failure — always last, so the frontend never hangs             |

Design points worth knowing:

- **Two nested discriminated unions.** `Event` discriminates on `type`;
  its trace member is itself a union of five variants (`ReadTrace`,
  `ExpandTrace`, `SearchTrace`, `SourceSearchTrace`, `FigureTrace`)
  discriminating on `action`. One
  `validate_python` call resolves both levels — a raw
  `{"type": "trace", "action": "read", ...}` dict comes back as a
  `ReadTrace`. The old teacher passed loose `{"action": ..., ...}` dicts
  whose shapes you had to reverse-engineer from five `_run_*` functions.
- **`Discovery` reuses the graph's own models.** `DiscoveredNode`
  *inherits* `services.graph.Node`, adding only `discovered: Literal[True]`
  and `idx` — the number the model knows the paper by (`None` tolerated
  for saved sessions from the era when lecture backfills discovered
  un-numbered papers). Because `extra="forbid"` is inherited, an agent-found
  paper is guaranteed to have exactly the shape `build_graph` produces:
  the frontend merges both into one canvas and can't tell the difference,
  and a drifted node shape fails loudly at the event boundary instead of
  rendering a half-empty node. Edges are `services.graph.Edge`, unchanged.
- **Each workflow's legal event sequence** (its "event grammar") is spelled
  out in its `skills/workflows/` playbook — e.g. the lecture's
  `Beat+ Done | Error`.
- **Two wire renames from the old protocol** (frontend adapts in Phase 6):
  the old `nodes` SSE event is now `discovery` (a `Discovery` model
  emitting an event called "nodes" read wrong), and `Error` carries
  `message` (the old event named "error" with a field named "error"
  stuttered).

## `traversal.py` — day-cached, provider-aware hops and search

The shared plumbing under every "bring in a paper that isn't on screen"
move: `neighbors(paper_id, relation, limit, provider)` pulls one hop of
references / citations / similar work, `search(query, limit, year_from,
year_to, provider)` runs a free-text search, and both cache their results for
`config.graph.cache_ttl` (the same day-long TTL as a graph snapshot —
citation data changes slowly).

**Both follow the selected graph provider** (v5.2.0), so an OpenAlex graph
expands/searches OpenAlex — keeping the pulled-in nodes in the same id space as
the graph. Under S2 a `similar` hop is SPECTER2 recommendations; under OpenAlex
it's `related_works` (concept/citation overlap — weaker, but the closest
analogue, since OpenAlex has no embeddings). The OpenAlex hop first resolves the
node id (a `DOI:`/`ARXIV:`/`W…` id) to a work, then hits `cited_by:` /
`cites:` / `related_works`. Provider is part of the cache key.

One consumer today:

- **The researcher's `expand_node`** wraps `neighbors`, and **the paper
  scout's `search` / `more_like`** wrap `search` and the `similar` hop of
  `neighbors` — adding everything agentic on top: budgets, visited-sets,
  numbering the finds, building `Discovery` events. Note the two callers of
  the *same* `similar` hop, doing different things with it: the researcher
  draws it on the graph, the scout treats it as a second way to search and
  hands back plain papers. The provider comes from the graph the question is
  grounded in — threaded `route → researcher.answer → ResearcherDeps.provider
  → the tools → papers.scout`. (The lecture backfill walks that also used to
  loop over `neighbors` are gone — lectures never expand the graph.)

Design points worth knowing:

- **The cache is the point.** The researcher re-hits the same hops
  constantly within a session (re-expansions across follow-up questions),
  and the rate-limited APIs must not pay for each repeat. This is the
  *cached, agent-tuned* layer over the `integrations` traversal clients —
  the deliberate name-cousins that talk to the live API and cache nothing.
- **Limits are explicit arguments, and part of the cache key.** The old
  `AGENT_*_LIMIT` globals died in the Phase-1 config purge; each caller's
  own config supplies its limit, and a hop cached at one limit is never
  reused for another.
- **`Relation` is a `Literal`** (`"references" | "citations" | "similar"`)
  and `REL_TAG` maps it to the `Edge.type` tag — so when the researcher builds
  `Edge(type=REL_TAG[relation])`, mypy verifies the whole chain from tool
  argument to graph edge. **`CitationHop` is the narrower one** (`"references"
  | "citations"`) that `expand_node` takes, and that narrowing IS the v7.5.0
  rule: a similar-hop expansion isn't refused at runtime, it can't be asked
  for, because the tool schema the model sees offers two values. `similar`
  stays in `Relation` for the paper scout, which hops the same data as a
  second way to search.
- **Plumbing, not tools.** No model ever calls these directly (see the
  layout rules below), and `S2Error` propagates uncaught — deciding what a
  failed hop means (skip the ancestor, tell the model, spend no budget) is
  the callers' job, not the plumbing's.

## `factory.py` — config entries → live model objects

Each sub-agent's `main.py` calls `factory.build_model(<its AGENT_ID>)` to
get the model its `config.llm.agents` entry names, and hands it to its
`pydantic_ai.Agent`. This is the one place credentials meet PydanticAI —
and it's deliberate that the entry's `"provider:model"` string is only ever
*parsed* here, never passed to PydanticAI whole: the bare string shorthand
would pull the API key from environment variables, and this app's config
rule is no env vars — the key comes from `config.llm.providers`, passed
explicitly to the provider. `agent_entry(id)` (the lookup half) is also how
an agent reads its own `extras` knobs — which arrive **already validated**
against that agent's model in `config.AGENT_EXTRAS`, complete with defaults
filled in, so a package indexes them (`extras["min_beats"]`) instead of
range-checking or `.get`-defaulting them. The factory also sets
`anthropic_eager_input_streaming` on every model — see `streams.py` below
for why nothing streams without it.

## `streams.py` — consuming a run synchronously, event by event

`drive(agent, ...)` runs `run_stream_events` (async-only) on **one shared,
long-lived event loop** (a daemon thread; request threads reach it via
`run_coroutine_threadsafe`) and yields each event as it arrives, so workflows
stay plain sync generators. It used to open a *fresh* loop per call and close
it at the end — fine sequentially, but the agents (and their one shared
Anthropic client) are singletons, so several streams at once (concurrent
lectures) each ran on their own loop over the one httpx pool, and the first
loop to close surfaced `Event loop is closed` in the others. One persistent
loop fixes it: httpx multiplexes concurrent requests on a single loop safely.
Three hard-won lessons live around it, the streaming two frame-timestamped
against the live API: the sync convenience wrapper
(`run_stream_sync().stream_output()`) delivers structured output in one
burst at the end — drive the raw events instead; and Anthropic buffers a
tool call's input JSON server-side unless the factory sets
`anthropic_eager_input_streaming` — and every structured output IS a tool
call, so without that flag nothing "streams" no matter how you consume it.

## `prompts.py` — app data → model input

The other half of agent assembly: `skill(name)` loads one skill's markdown
from `skills/` (a typo'd skill name fails at import, not by silently
weakening the prompt) — agents pass their parts straight to PydanticAI,
`instructions=[SYSTEM_PROMPT, *(skill(n) for n in SKILLS)]`, which joins a
sequence with blank lines natively. `node_lines(nodes)` renders graph nodes
as the numbered list of the `numbered-papers` protocol (a paper's number is
its list position + 1) and `idx_to_id` maps the model's indices back to node
ids, ignoring hallucinated ones (shared by the lecturer and, later, the
researcher). `graph_refs_from_text(nodes, text)` is the clickable-citation
counterpart: it scans finished prose for the `[n]` markers actually *used* and
resolves each against the same numbered list, returning a `{"n": node_id}` map
the frontend turns into clickable chips. A combined marker (`[14, 29]`, which
the model sometimes writes despite the prompt asking for separate `[14][29]`)
contributes each of its indices, so every number stays clickable — the same
split the frontend's `remarkCite` and `resolveRefs` apply. The **lecturer** resolves this
server-side and ships it on each beat's `graph_refs` field — a lecture numbers the
mode-filtered `_story_nodes`, which the frontend never sees, so it *can't*
resolve them itself. The **researcher** is the mirror case: it gets the full,
unfiltered node list, so the frontend resolves its answer's `[n]` markers
directly (grounding order + idx-tagged discoveries) and no backend `graph_refs` is
emitted.

`paper_refs(nodes, text, provider)` is the graph-free sibling — same scan,
same numbering, but it carries title, URL, and **the provider that issued
each id**. That last field is the load-bearing one: a paper id is only
resolvable in the backend that minted it, and the frontend's click *builds a
graph* from it, so a reference that travelled (a dropdown switched
mid-conversation, a session restored under the other backend) needs to say
where it came from or the build looks up an id in a namespace it was never
in. See `frontend/src/teacher/transcript/README.md` for what the click does
with it.

**Library citations work the other way round.** `source_lines(sources)`
numbers the user's uploaded sources (`[S1] "Title"`), `format_passages(hits,
sources)` tags each retrieved passage with the marker to copy (`[S1, p.243]`,
or `[S1]` for a page-less web source), and `source_refs(sources, text)`
resolves those markers back to real ids. Unlike `[n]` paper markers, these
*must* be resolved server-side and streamed (as a `SourceRefs` event): only
the backend knows which of the user's sources a turn retrieved. The map is
keyed by index alone and carries no page — the page is already in the marker
— which is what lets it be emitted *before* the prose, so a marker renders as
a real title the moment it streams instead of showing raw until the answer
lands. Both agents that show library passages use this: the researcher
(`search_sources`) and the lecturer (intuition mode). `history(turns)`
converts the routes layer's `[{role, content}]` turns into PydanticAI
message history.

**Provenance is observed, never asked for.** `Provenance` carries what the
server watched happen during a turn — whether a library was in scope, how many
library searches and paper searches ran, how many passages came back, and how
many sources and papers the *finished prose* cites. It does not ask the model
where its knowledge came from, because a model has no reliable access to which
of its sentences came from a retrieved passage and which from its own weights;
the answer would be a confident label with nothing behind it. The one
self-reported field on it is `kind`, and it rides there precisely so the claim
can be checked against the counts beside it. The frontend turns the counts into
one line (`teacher/transcript/provenance.ts`) — deliberately, so the wording is
presentation and can change without touching the agent. Library and paper
searches are counted **separately**: "went to Semantic Scholar and cited none
of it" and "wrote this from memory" are different things to tell a student, and
a single counter made them indistinguishable (see `docs/history.md`, v6.8.0).

One house rule lives here: **agents are built with `instructions=`, never
`system_prompt=`** — PydanticAI silently drops a `system_prompt` whenever
`message_history` is passed, which would cost an agent its persona on every
follow-up turn.

## Decisions log (locked before design)

1. **Hybrid orchestration with intent hints.** Routes always call the
   orchestrator, passing the UI's intent (`lecture` / `research`).
   Known intents dispatch straight to the matching sub-agent per its
   `skills/workflows/` playbook — no routing LLM call. The orchestrator's
   own model engages only when intent is ambiguous or a workflow needs
   multi-step coordination.
2. **API-only.** The claude-CLI backend (subscription streaming) is gone —
   it existed to power tool-free fallbacks, and PydanticAI can't drive it.
   `backends.py` and the before-first-token fallback dance die with it.
3. **The non-agentic grounded Q&A is deleted, not ported.** It was the CLI
   backend's consolation prize. One researcher, always with tools; easy questions
   simply won't trigger tool calls.
4. **Structured outputs everywhere.** Lecture beats stream as typed objects
   (no newline-delimited-JSON parsing); cited papers are a field of the
   answer (no `<<CITED>>` sentinel, no hold-back streaming, no `discard`
   events). The one string protocol that survives is `<<FIG n>>` — a figure
   marker is *positional within prose*, which structured output can't
   express.

## Architecture

```
agents/
  README.md          ← this document
  events.py          ← shared: the typed event stream every workflow emits
  traversal.py       ← shared: day-cached S2 hops + free-text search (plumbing)
  factory.py         ← shared: config.llm entry -> live PydanticAI model
  streams.py         ← shared: the sync event bridge (drive a run, yield events)
  prompts.py         ← shared: skills -> instructions, passages/history -> model input
  library_figures.py ← the show_source_figure core (resolve/dedupe/slot)
  skills/            ← shared: skills.md files any sub-agent's config may load
    numbered-papers.md      the index-not-id grounding protocol
    teaching-voice.md       the "sharp, friendly teacher" persona rules
    citation-discipline.md  ground only in provided/read material; never invent
    figures.md              real figures only; <<FIG n>> marker placement
    workflows/              ← the orchestrator's playbooks, one per intent
      lecture.md              the lecturer (narrates the visible graph as-is)
      research.md             the researcher Q&A (with a graph, or without)
  orchestrators/     ← tier 1: agents that own an outcome (README.md)
    lecturer/          ← an agent: main.py, config.py, README.md
    researcher/        ← an agent: main.py, tools.py, config.py, README.md
    summarizer/        ← an agent: main.py, config.py, README.md
  workers/           ← tier 2: one source each, one question each
    search/            ← workers that go and look something up (README.md)
      papers/            ← an agent: main.py, config.py (the provider search)
      web/               ← an agent: main.py, config.py (the open web)
```

### Layout rules

- **The package root *is* the shared directory.** Anything sitting directly
  at the root (`events.py`, `traversal.py`, `skills/`) is shared
  infrastructure available to every agent.
- **Agents sit in two tiers, flat, and no deeper** (v7.0.0).
  `orchestrators/` own an outcome and may delegate; `workers/` each own one
  source and answer a bounded question about it. Which tier something belongs
  in is decided by one rule, kept in
  [`workers/README.md`](workers/README.md) so it isn't re-argued: **a
  capability earns worker status when it needs judgment or context
  isolation — otherwise it stays a plain function.** That file also holds the
  return-shape contract (structured findings, never prose, never indices) and
  why depth beyond two tiers was rejected. Workers are grouped by *kind*
  (`search/` today), so the grouping folder — not the worker — is what sits
  under `workers/`.
- **No router.** Routes call the agent they mean. The `orchestrator`
  package and the `Intent` enum were deleted in v7.0.0; see
  [`orchestrators/README.md`](orchestrators/README.md) for what happened to
  the two things it carried.
- **`tools.py` appears only inside an agent** and only ever means "this
  agent's model-callable tool surface" — functions registered on the
  PydanticAI agent whose signatures become schemas the LLM sees. Shared
  *plumbing* (code tools call into, which no model ever sees) lives at the
  root as ordinary modules; it is never called "tools."
- **Every sub-agent package carries its own `README.md`** documenting its
  workflow, tools, budgets, and events.

### The sub-agent contract

Each sub-agent package is exactly:

- **`main.py`** — the PydanticAI `Agent`: its deps type, output type, and
  construction from the agent's `config.llm.agents` entry (looked up by id).
- **`tools.py`** — tools only *this* agent exposes to its model. Absent when
  the agent has none.
- **`config.py`** — the agent's system prompt, the list of skills it loads
  from `agents/skills/`, and its budget knobs. The central
  `config.llm.agents` entry supplies the model string and tunables; the
  package's `config.py` supplies the words.
- **`README.md`** — the agent's own documentation.

### Skills

A skill is a markdown file in `agents/skills/` holding prompt-ready
instructions. Each sub-agent's `config.py` names the skills it loads; a
shared loader reads them and appends their content to the agent's system
prompt. Two kinds live side by side:

- **Behavior skills** (the files at the `skills/` root: `numbered-papers`,
  `teaching-voice`, `citation-discipline`, `figures`) — reusable
  instruction blocks shared by whichever agents opt in.
- **Workflow skills** (`skills/workflows/`) — the orchestrator's playbooks:
  one per intent, defining inputs, steps, delegation, and the event stream.
  For a known intent the dispatch is deterministic code that *implements*
  the skill; when the orchestrator's model engages, the skills are its
  instructions.

## The workflows

### `orchestrator` *(built)*

The front door. `run(intent, ...)` takes the UI's intent hint + the request
payload, dispatches the matching workflow deterministically, and is the one
place the termination contract is enforced: every stream ends with exactly
one `Done` or `Error`. Lectures are pure delegation — **a lecture never
expands the graph**; every mode narrates the visible node set as-is (the
old backfill walks are gone; only the researcher grows the graph). **No
model lives in the orchestrator yet, deliberately:** every current entry
point passes a known intent, so the hybrid design's model half
(ambiguous/multi-step requests) is a documented seam in `main.py`, not
speculative plumbing — same call as the query-expansion seam in Phase 3.
See its own README.

### `lecturer` — the streamed graph lecture *(built)*

- **Input:** seed, visible nodes (numbered), mode
  (`history` / `intuition` / `evolution` / `frontier` / `bridge`), target paper
  (bridge only). Lectures never expand the graph, and the orchestrator scopes
  each mode to one graph relation (history = references ending at the seed;
  evolution = landmark citers onward; frontier = the Latest Publications;
  intuition = the seed alone, read from its full text).
- **Tools:** none.
- **Output:** a streamed sequence of typed `Beat` objects
  (`heading`, `text`, `node_indices` → mapped back to node ids) so the
  frontend reveals the story beat-by-beat and lights up graph nodes in sync.
  Structured output replaces the old NDJSON protocol and its fence-stripping
  parser.
- **Skills:** `numbered-papers`, `teaching-voice`, `citation-discipline`.
- **Config:** the five mode-intent paragraphs; `extras` knobs (typed as
  `config.LecturerExtras`) for the frontier narration window
  (`frontier_window_months`, default 60 — now frames the FRONTIER wording only,
  no longer a node filter) and the beat-count bounds (`min_beats`/`max_beats`,
  default 7–12 — widened as a full-span lever; the model enforces min ≤ max).

### `researcher` — agentic Q&A over the graph *(built)*

The flagship. Reads, expands, and searches via tool use, then answers
grounded in what it actually read.

- **Input:** question, seed, visible nodes, conversation history, optional
  library scope (`source_ids`: `None` = whole library, present list =
  pinned to exactly those, empty list = source search disabled), and optional
  **played lectures** (`lectures`: the `PlayedLecture` beats the lecturer already
  delivered this session, from the frontend's transcript cache) — folded into the
  prompt (budgeted by `_LECTURES_MAX_CHARS`) as context to build on, so a Q&A
  answer doesn't re-derive a story the student just watched.
- **Tools** (its `tools.py`):
  - `read_paper` — summary (abstract + TL;DR, hydrated from S2 on demand)
    or full text via ar5iv; a full read also lists the paper's figures.
  - `expand_node` — one hop of references or citations for a numbered
    paper; new papers get numbered, and streamed to the graph when they
    attach to a paper already drawn (see "What reaches the canvas"). Citation
    hops only, since v7.5.0 — a citation map is made of citations, and
    embedding-similar work reaches the answer through the paper scout
    instead.
  - `find_papers` — hands a *need* in plain words to the **paper scout**
    (`workers/papers`), which writes and re-writes the queries itself and
    reports back; the researcher numbers whatever it found. Numbered, not
    drawn — the reader promotes a found paper by clicking its citation.
    Replaced the one-shot `search_papers` in v7.0.0: a single query against
    a lexical, citation-weighted search answers "what's new in X" with
    landmarks from a decade ago, and reformulating is a loop with a decision
    in it. It **replaced** rather than joined it — two paths to one source is
    the bug, not the feature.
  - `search_web` — the same shape for the **web scout** (`workers/web`):
    announcements, releases, documentation, benchmarks — where the news
    breaks before the paper does. Registered only when its budget is
    non-zero, which is also the web's off switch.
  - `show_figure` — attach a real ar5iv figure; the model places a
    `<<FIG n>>` marker in its prose where the image belongs.
  - `search_sources` — semantic search over the user's library; registered
    only when a library exists (checked before the embedding model loads).
- **Budgets:** total steps, wall clock, full/summary reads, hops, searches,
  web searches, source searches, figures — from its agents entry. A
  `find_papers`/`search_web` call spends one of *these* and then runs a whole
  scout, which has budgets of its own. Visited-sets, the read
  cache, and remaining budgets live in the run's deps.
- **Output:** streamed answer prose, with `cited` (the papers it read plus
  any it named) as a structured field of the final result.
- **What reaches the canvas** *(v7.3.0)* — **the graph grows only where a new
  paper attaches to a paper already on it.** `find_papers` numbers its hits and
  draws none of them: a topic search links to no specific paper, so they used
  to arrive as edgeless dots floating beside the graph, which was the only way
  to surface them back when a chat citation couldn't hand a paper back. It can
  now (v6.11.0, provider-stamped in v6.14.0), so the reader promotes a found
  paper deliberately by clicking `[n]`. The same rule covers the case that
  makes it *one* rule rather than a quirk of one tool: expanding a paper that
  isn't itself drawn produces edges pointing at a node the frontend hasn't got,
  and a link with a missing endpoint makes d3-force raise and takes the graph
  down — so that expansion numbers its neighbours and draws nothing either.
  Run in the other direction, an expansion that turns up an already-numbered
  but undrawn paper **promotes** it: the edge it was missing now exists.
  `ResearcherDeps.on_canvas` is the bookkeeping; `tools._canvas_growth` is the
  rule. **v7.5.0 finished the thought**: `expand_node` takes a `CitationHop`,
  so the graph grows only along citations — and the two relations that could
  no longer arrive, `search` and `similar`, were removed outright rather than
  kept for old saves (there were none). `primaryRel` is total instead, drawing
  any relation this build has no meaning for as grey `unknown`.
- **Events:** `Trace` (each tool step, including `search_web`), `Discovery`
  (nodes/edges to merge into the live graph), `Figure`, `Token`, `Cited`,
  `Provenance` (which now counts web searches and pages separately from
  paper searches — "went to the literature" and "went to the web" are
  different claims about an answer's footing).
- **Skills:** `numbered-papers`, `teaching-voice`, `citation-discipline`,
  `figures`.

> **Retired in v6.7.0: `librarian`.** It was a graph-free RAG agent that
> retrieved *before* the model ran, which meant it searched the student's
> books to answer "hi" — no prompt could fix that, because the model never
> got a say. It was also a strict subset of the researcher (same retrieval,
> same figure tool, same event bridge, same structured output); the only
> real difference was *when* retrieval fired. Making retrieval a tool left
> nothing behind, so the package went and the researcher took both chats.
> See `docs/history.md`.

### `query_analyst` — *(retired v7.6.0)*

> A one-shot micro-agent that expanded a seed-search query ("DQN" → "DQN deep
> Q-network deep Q-learning") and named papers it confidently recalled, which
> `live_search` then verified by title match. Both halves outlived it in a
> better form: the **paper scout** reformulates across several attempts rather
> than expanding once (it can see what came back), and its `match_title` tool
> resolves a recalled title directly. Keeping the analyst would have left two
> implementations of "search papers" — the duplication the worker split exists
> to prevent. See `docs/history.md`.

## Who uses it, and how/why

Callers *into* the package (each sub-agent's own README traces its callers
in detail):

- **`routes/search.py`** — calls the **paper scout** directly (v7.6.0), with
  no orchestrator and no researcher above it: direct search is the same
  worker the researcher sends out, run alone. The only agent consumed outside
  a teacher workflow, and it reaches `services/search` rather than the other
  way round — the scout reads the snapshot cache from inside its own `search`
  tool.
- **The routes layer (Phase 5, traced from the old repo, not yet ported).**
  Old `routes/teacher.py` calls the teacher functions directly —
  `lecture_beats` behind `POST /api/teacher` (lecture), `answer_agentic`
  behind the Q&A path, `answer_from_sources` behind `POST /api/ask_sources` —
  and serializes their `("kind", data)` tuples as SSE frames. The rewrite
  replaces all of that with one entry point: routes call the
  **orchestrator** with an intent hint (`lecture` / `research`),
  serialize the typed `Event` stream by its `type` tag, and keep session
  history persistence for themselves (a locked decision — agents receive
  history, they never store it).

Inside the package, the shared root modules exist for the sub-agents:
every agent builds its model via `factory.build_model` and its instruction
parts via `prompts.skill`; the researcher converts route
turns with `prompts.history`; the lecturer (and next the researcher) numbers
papers with `prompts.node_lines` / `idx_to_id`; every workflow yields
`events` models; `traversal.py` serves the researcher's expand/search tools.

## Testing

Agent loops are tested with PydanticAI's `TestModel` / `FunctionModel`
(scripted model behavior, no network) — replacing the old `fake_claude`
fixture built from raw Anthropic SDK events. Deterministic pieces
(`traversal.py`, skill loading, event models) get plain unit tests. As
everywhere in this repo: no live API calls, ever.
