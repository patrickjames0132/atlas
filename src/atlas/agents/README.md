# `agents`

The AI teacher, rebuilt as a crew of agents: one **orchestrator** delegating to
focused **sub-agents**, every agent defined by Pydantic objects (PydanticAI
`Agent`s wired from `config.llm.agents` entries) instead of the old repo's
hand-rolled Anthropic SDK loops.

**Status: COMPLETE.** The shared infrastructure (`events.py`,
`traversal.py`, `factory.py`, `prompts.py`, `skills/`), the
model-driven agents (`query_analyst`, `summarizer`, `librarian`,
`lecturer`, `researcher`),
and the `orchestrator` dispatcher are built and tested; the old
`teacher/` package is fully retired. What remains is wiring: routes call
`orchestrator.run(intent, ...)` in Phase 5. (`summarizer` arrived later,
v5.17.0: the detail panel's on-demand TL;DR — a micro-agent in the
query_analyst mold, called from `routes/graph.py`, never the
orchestrator.)

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
| `Token`     | researcher, librarian      | a chunk of streamed answer prose                               |
| `Trace`     | researcher, orchestrator, librarian | "watch the agent work" — one variant per action (below) |
| `Discovery` | researcher, orchestrator   | papers + edges to merge into the live graph                    |
| `Figure`    | researcher, librarian | a real figure attached to the answer — a paper's, or one mined from an uploaded PDF (`index=None`) |
| `Cited`     | researcher            | final event: the node ids the answer draws on                  |
| `Done`      | every workflow        | clean finish — always last on success                          |
| `Error`     | every workflow        | failure — always last, so the frontend never hangs             |

Design points worth knowing:

- **Two nested discriminated unions.** `Event` discriminates on `type`;
  its trace member is itself a union of six variants (`ReadTrace`,
  `ExpandTrace`, `SearchTrace`, `SourceSearchTrace`, `FigureTrace`,
  `RetrievalTrace`) discriminating on `action`. One
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

- **The researcher's `expand_node` / `search_papers` tools** wrap `neighbors` /
  `search` with everything agentic: budgets, visited-sets, numbering the
  finds, building `Discovery` events. The provider comes from the graph the
  question is grounded in — threaded `route → orchestrator.run → researcher.answer
  → ResearcherDeps.provider → the tools`. (The lecture backfill walks that
  also used to loop over `neighbors` are gone — lectures never expand the
  graph.)

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
  argument to graph edge.
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
an agent reads its own `extras` knobs. The factory also sets
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
researcher). `refs_from_text(nodes, text)` is the clickable-citation
counterpart: it scans finished prose for the `[n]` markers actually *used* and
resolves each against the same numbered list, returning a `{"n": node_id}` map
the frontend turns into clickable chips. A combined marker (`[14, 29]`, which
the model sometimes writes despite the prompt asking for separate `[14][29]`)
contributes each of its indices, so every number stays clickable — the same
split the frontend's `remarkCite` and `resolveRefs` apply. The **lecturer** resolves this
server-side and ships it on each beat's `refs` field — a lecture numbers the
mode-filtered `_story_nodes`, which the frontend never sees, so it *can't*
resolve them itself. The **researcher** is the mirror case: it gets the full,
unfiltered node list, so the frontend resolves its answer's `[n]` markers
directly (grounding order + idx-tagged discoveries) and no backend `refs` is
emitted. `format_passages(hits)` renders retrieved library
passages tagged `[Title, p.N]` (shared by the librarian's grounding context
and, later, the researcher's `search_sources` tool result), and `history(turns)`
converts the routes layer's `[{role, content}]` turns into PydanticAI
message history.

One house rule lives here: **agents are built with `instructions=`, never
`system_prompt=`** — PydanticAI silently drops a `system_prompt` whenever
`message_history` is passed, which would cost an agent its persona on every
follow-up turn.

## Decisions log (locked before design)

1. **Hybrid orchestration with intent hints.** Routes always call the
   orchestrator, passing the UI's intent (`lecture` / `research` / `librarian`).
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
  library_figures.py ← shared: the show_source_figure core (researcher + librarian)
  skills/            ← shared: skills.md files any sub-agent's config may load
    numbered-papers.md      the index-not-id grounding protocol
    teaching-voice.md       the "sharp, friendly teacher" persona rules
    citation-discipline.md  ground only in provided/read material; never invent
    figures.md              real figures only; <<FIG n>> marker placement
    workflows/              ← the orchestrator's playbooks, one per intent
      lecture.md              the lecturer (narrates the visible graph as-is)
      research.md                  the researcher Q&A
      librarian.md            the librarian RAG chat
  orchestrator/      ← an agent: main.py, tools.py, config.py, README.md
  lecturer/          ← an agent:    "        "         "          "
  researcher/             ← an agent:    "        "         "          "
  librarian/         ← an agent:    "        "         "          "
  query_analyst/     ← an agent:    "        "         "          "
  summarizer/        ← an agent: main.py, config.py, README.md (no tools)
```

### Layout rules

- **The package root *is* the shared directory.** Anything sitting directly
  at the root (`events.py`, `traversal.py`, `skills/`) is shared
  infrastructure available to every agent. Every sub-package *is* an agent.
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
- **Config:** the five mode-intent paragraphs; `extras` knobs for the
  frontier narration window (`frontier_window_months`, default 60 — now frames
  the FRONTIER wording only, no longer a node filter) and the beat-count bounds
  (`min_beats`/`max_beats`, default 7–12 — widened as a full-span lever).

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
  - `expand_node` — one hop of references / citations / similar for a
    numbered paper; new papers get numbered and streamed to the graph.
  - `search_papers` — free-text S2 search with a year window; hits get
    numbered and added (nodes only, no edges — a topic search links to no
    specific paper).
  - `show_figure` — attach a real ar5iv figure; the model places a
    `<<FIG n>>` marker in its prose where the image belongs.
  - `search_sources` — semantic search over the user's library; registered
    only when a library exists (checked before the embedding model loads).
- **Budgets:** total steps, wall clock, full/summary reads, hops, searches,
  source searches, figures — from its agents entry. Visited-sets, the read
  cache, and remaining budgets live in the run's deps.
- **Output:** streamed answer prose, with `cited` (the papers it read plus
  any it named) as a structured field of the final result.
- **Events:** `Trace` (each tool step), `Discovery` (nodes/edges to merge
  into the live graph), `Figure`, `Token`, `Cited`.
- **Skills:** `numbered-papers`, `teaching-voice`, `citation-discipline`,
  `figures`.

### `librarian` — offline library chat *(built)*

Graph-free RAG over the user's own uploaded sources. See its own README.

- **Input:** question, conversation history, optional scope. Retrieval
  (`services.sources.search` — RRF over FTS5 + vectors) runs *before* the
  agent, deterministically; the passages go in as context.
- **Tools:** none.
- **Output:** streamed prose citing inline by title and page, e.g.
  "(Deep Learning, p.243)". A `RetrievalTrace` names the retrieved sources
  first; empty retrieval yields a friendly "nothing found" answer without
  engaging the model.
- **Skills:** `teaching-voice`, `citation-discipline`.
- **Note:** the whole `workflows/librarian.md` playbook lives in
  `librarian.answer(...)` — the orchestrator's `librarian` intent just
  calls it.

### `query_analyst` — seed-search query expansion *(built)*

A one-shot micro-agent, new in this rewrite (the old repo left a seam for
it). See its own README for the full story.

- **Input:** the raw search query from the seed-search box.
- **Output:** structured `Expansion.expanded_query` — acronyms and jargon
  expanded ("DQN" → "DQN deep Q-network deep Q-learning") so S2's lexical
  search can find seminal papers that never spell the acronym out.
- **Tools:** none. **Skills:** none.
- **Note:** invoked from `services/search`'s `_analyze` seam, *not*
  through the orchestrator — it's infrastructure for search, not a teacher
  workflow. It degrades to a passthrough on any failure: search can never
  break because the LLM hiccuped.

## Who uses it, and how/why

Callers *into* the package (each sub-agent's own README traces its callers
in detail):

- **`services/search/discovery.py`** (ported, live now) — `live_search`
  routes every query through its `_analyze` seam, a one-line delegation
  to `query_analyst.analyze` (expansion + confidently recalled titles,
  verified via S2 title match). The only agent consumed outside the
  teacher workflows: it's infrastructure for search, wired directly, never
  through the orchestrator.
- **The routes layer (Phase 5, traced from the old repo, not yet ported).**
  Old `routes/teacher.py` calls the teacher functions directly —
  `lecture_beats` behind `POST /api/teacher` (lecture), `answer_agentic`
  behind the Q&A path, `answer_from_sources` behind `POST /api/ask_sources` —
  and serializes their `("kind", data)` tuples as SSE frames. The rewrite
  replaces all of that with one entry point: routes call the
  **orchestrator** with an intent hint (`lecture` / `research` / `librarian`),
  serialize the typed `Event` stream by its `type` tag, and keep session
  history persistence for themselves (a locked decision — agents receive
  history, they never store it).

Inside the package, the shared root modules exist for the sub-agents:
every agent builds its model via `factory.build_model` and its instruction
parts via `prompts.skill`; the librarian (and next the researcher) converts route
turns with `prompts.history`; the lecturer (and next the researcher) numbers
papers with `prompts.node_lines` / `idx_to_id`; every workflow yields
`events` models; `traversal.py` serves the researcher's expand/search tools.

## Testing

Agent loops are tested with PydanticAI's `TestModel` / `FunctionModel`
(scripted model behavior, no network) — replacing the old `fake_claude`
fixture built from raw Anthropic SDK events. Deterministic pieces
(`traversal.py`, skill loading, event models) get plain unit tests. As
everywhere in this repo: no live API calls, ever.
