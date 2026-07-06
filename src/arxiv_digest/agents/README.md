# `agents`

The AI teacher, rebuilt as a crew of agents: one **orchestrator** delegating to
focused **sub-agents**, every agent defined by Pydantic objects (PydanticAI
`Agent`s wired from `config.llm.agents` entries) instead of the old repo's
hand-rolled Anthropic SDK loops.

**Status: shared infrastructure built** (`events.py`, `traversal.py`,
`factory.py`, `prompts.py`, the `skills/` drafts) **plus three agents:
`query_analyst`, `librarian`, and `lecturer`**; tutor and orchestrator land
next.

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
| `Token`     | tutor, librarian      | a chunk of streamed answer prose                               |
| `Trace`     | tutor, orchestrator, librarian | "watch the agent work" — one variant per action (below) |
| `Discovery` | tutor, orchestrator   | papers + edges to merge into the live graph                    |
| `Figure`    | tutor                 | a real paper figure attached to the answer                     |
| `Cited`     | tutor                 | final event: the node ids the answer draws on                  |
| `Done`      | every workflow        | clean finish — always last on success                          |
| `Error`     | every workflow        | failure — always last, so the frontend never hangs             |

Design points worth knowing:

- **Two nested discriminated unions.** `Event` discriminates on `type`;
  its trace member is itself a union of seven variants (`ReadTrace`,
  `ExpandTrace`, `SearchTrace`, `SourceSearchTrace`, `FigureTrace`,
  `BackfillTrace`, `RetrievalTrace`) discriminating on `action`. One
  `validate_python` call resolves both levels — a raw
  `{"type": "trace", "action": "read", ...}` dict comes back as a
  `ReadTrace`. The old teacher passed loose `{"action": ..., ...}` dicts
  whose shapes you had to reverse-engineer from five `_run_*` functions.
- **`Discovery` reuses the graph's own models.** `DiscoveredNode`
  *inherits* `services.graph.Node`, adding only `discovered: Literal[True]`
  and `idx` — the number the model knows the paper by (`None` when the
  history backfill found it, since backfill runs before the lecturer
  numbers anything). Because `extra="forbid"` is inherited, an agent-found
  paper is guaranteed to have exactly the shape `build_graph` produces:
  the frontend merges both into one canvas and can't tell the difference,
  and a drifted node shape fails loudly at the event boundary instead of
  rendering a half-empty node. Edges are `services.graph.Edge`, unchanged.
- **Each workflow's legal event sequence** (its "event grammar") is spelled
  out in its `skills/workflows/` playbook — e.g. the lecture's
  `[Trace* Discovery*] Beat+ Done | Error`.
- **Two wire renames from the old protocol** (frontend adapts in Phase 6):
  the old `nodes` SSE event is now `discovery` (a `Discovery` model
  emitting an event called "nodes" read wrong), and `Error` carries
  `message` (the old event named "error" with a field named "error"
  stuttered).

## `traversal.py` — day-cached S2 hops and search

The shared plumbing under every "bring in a paper that isn't on screen"
move: `neighbors(paper_id, relation, limit)` pulls one hop of
references / citations / similar work, `search(query, limit, year_from,
year_to)` runs a free-text S2 search, and both cache their results for
`config.graph.cache_ttl` (the same day-long TTL as a graph snapshot —
citation data changes slowly).

Two consumers, using it differently:

- **The orchestrator's `history_backfill`** loops over
  `neighbors(..., "references", ...)` raw, hop after hop, walking toward a
  field's roots before a history lecture.
- **The tutor's `expand_node` / `search_papers` tools** wrap `neighbors` /
  `search` with everything agentic: budgets, visited-sets, numbering the
  finds, building `Discovery` events.

Design points worth knowing:

- **The cache is the point.** Both consumers re-hit the same hops
  constantly within a session (the agent re-expands, the user re-lectures),
  and the rate-limited S2 API must not pay for each repeat. This is the
  *cached, agent-tuned* layer over `integrations.semantic_scholar.traversal`
  — the deliberate name-cousin that talks to the live API and caches
  nothing.
- **Limits are explicit arguments, and part of the cache key.** The old
  `AGENT_*_LIMIT` globals died in the Phase-1 config purge; each caller's
  own config supplies its limit, and a hop cached at one limit is never
  reused for another.
- **`Relation` is a `Literal`** (`"references" | "citations" | "similar"`)
  and `REL_TAG` maps it to the `Edge.type` tag — so when the tutor builds
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
an agent reads its own `extras` knobs.

## `prompts.py` — app data → model input

The other half of agent assembly: `skill(name)` loads one skill's markdown
from `skills/` (a typo'd skill name fails at import, not by silently
weakening the prompt) — agents pass their parts straight to PydanticAI,
`instructions=[SYSTEM_PROMPT, *(skill(n) for n in SKILLS)]`, which joins a
sequence with blank lines natively. `node_lines(nodes)` renders graph nodes
as the numbered list of the `numbered-papers` protocol (a paper's number is
its list position + 1) and `idx_to_id` maps the model's indices back to node
ids, ignoring hallucinated ones (shared by the lecturer and, later, the
tutor). `format_passages(hits)` renders retrieved library
passages tagged `[Title, p.N]` (shared by the librarian's grounding context
and, later, the tutor's `search_sources` tool result), and `history(turns)`
converts the routes layer's `[{role, content}]` turns into PydanticAI
message history.

One house rule lives here: **agents are built with `instructions=`, never
`system_prompt=`** — PydanticAI silently drops a `system_prompt` whenever
`message_history` is passed, which would cost an agent its persona on every
follow-up turn.

## Decisions log (locked before design)

1. **Hybrid orchestration with intent hints.** Routes always call the
   orchestrator, passing the UI's intent (`lecture` / `q&a` / `librarian`).
   Known intents dispatch straight to the matching sub-agent per its
   `skills/workflows/` playbook — no routing LLM call. The orchestrator's
   own model engages only when intent is ambiguous or a workflow needs
   multi-step coordination.
2. **API-only.** The claude-CLI backend (subscription streaming) is gone —
   it existed to power tool-free fallbacks, and PydanticAI can't drive it.
   `backends.py` and the before-first-token fallback dance die with it.
3. **The non-agentic grounded Q&A is deleted, not ported.** It was the CLI
   backend's consolation prize. One tutor, always with tools; easy questions
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
  prompts.py         ← shared: skills -> instructions, passages/history -> model input
  skills/            ← shared: skills.md files any sub-agent's config may load
    numbered-papers.md      the index-not-id grounding protocol
    teaching-voice.md       the "sharp, friendly teacher" persona rules
    citation-discipline.md  ground only in provided/read material; never invent
    figures.md              real figures only; <<FIG n>> marker placement
    workflows/              ← the orchestrator's playbooks, one per intent
      lecture.md              backfill → lecturer
      q&a.md                  the tutor Q&A
      librarian.md            the librarian RAG chat
  orchestrator/      ← an agent: main.py, tools.py, config.py, README.md
  lecturer/          ← an agent:    "        "         "          "
  tutor/             ← an agent:    "        "         "          "
  librarian/         ← an agent:    "        "         "          "
  query_analyst/     ← an agent:    "        "         "          "
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

### `orchestrator`

The front door. Input: an intent hint + the request payload. For the three
known intents it runs the matching workflow skill deterministically; its
model engages only for ambiguous or multi-step requests. Its `tools.py`
holds the sub-agent delegations plus **`history_backfill`** — the
deterministic reference-walk ported from the old `lecture.py`: launch from
the oldest visible papers, hop backward through day-cached references, add
the most-cited new ancestors per hop, stop at a year floor or the hop
budget, emit `Trace`/`Discovery` events per productive hop. Not an agent —
no LLM ever touches it.

### `lecturer` — the streamed graph lecture *(built)*

- **Input:** seed, visible nodes (numbered), mode
  (`history` / `intuition` / `bridge`), target paper (bridge only). History
  mode receives the backfill-enriched node set from the orchestrator.
- **Tools:** none.
- **Output:** a streamed sequence of typed `Beat` objects
  (`heading`, `text`, `node_indices` → mapped back to node ids) so the
  frontend reveals the story beat-by-beat and lights up graph nodes in sync.
  Structured output replaces the old NDJSON protocol and its fence-stripping
  parser.
- **Skills:** `numbered-papers`, `teaching-voice`, `citation-discipline`.
- **Config:** the three mode-intent paragraphs; beat count bounds (5–9).

### `tutor` — agentic Q&A over the graph

The flagship. Reads, expands, and searches via tool use, then answers
grounded in what it actually read.

- **Input:** question, seed, visible nodes, conversation history, optional
  library scope (`source_ids`: `None` = whole library, present list =
  pinned to exactly those, empty list = source search disabled).
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
- **Note:** invoked from `services/search`'s `_expand_query` seam, *not*
  through the orchestrator — it's infrastructure for search, not a teacher
  workflow. It degrades to a passthrough on any failure: search can never
  break because the LLM hiccuped.

## Testing

Agent loops are tested with PydanticAI's `TestModel` / `FunctionModel`
(scripted model behavior, no network) — replacing the old `fake_claude`
fixture built from raw Anthropic SDK events. Deterministic pieces
(`traversal.py`, `history_backfill`, skill loading, event models) get plain
unit tests. As everywhere in this repo: no live API calls, ever.
